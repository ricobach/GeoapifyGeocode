"""GPS-based movement tracking for GeoapifyGeocode."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
import time

from homeassistant.components.recorder import get_instance, history
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_GPS_ACCURACY, ATTR_LATITUDE, ATTR_LONGITUDE
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util
from homeassistant.util import location as location_util

from .const import (
    CONF_MOVEMENT_COMPARISON_AGE,
    CONF_MOVEMENT_DEFAULT_ACCURACY,
    CONF_MOVEMENT_HISTORY_WINDOW,
    CONF_MOVEMENT_MIN_DISTANCE_M,
    CONF_MOVEMENT_MIN_REFERENCE_AGE,
    CONF_MOVEMENT_STATIONARY_TIMEOUT,
    CONF_TARGETS,
    DEFAULT_MOVEMENT_COMPARISON_AGE,
    DEFAULT_MOVEMENT_DEFAULT_ACCURACY,
    DEFAULT_MOVEMENT_HISTORY_WINDOW,
    DEFAULT_MOVEMENT_MIN_DISTANCE_M,
    DEFAULT_MOVEMENT_MIN_REFERENCE_AGE,
    DEFAULT_MOVEMENT_STATIONARY_TIMEOUT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

MIN_SAMPLE_SPACING_SECONDS = 5
MAX_HISTORY_SAMPLES = 240
ENTITY_REFRESH_INTERVAL = 60


@dataclass(slots=True, frozen=True)
class GPSSample:
    """One GPS observation."""

    timestamp: datetime
    latitude: float
    longitude: float
    accuracy: float | None


@dataclass(slots=True, frozen=True)
class MovementEvaluation:
    """Calculated movement state for one tracked entity."""

    is_moving: bool | None
    current: GPSSample | None
    reference: GPSSample | None
    reference_age: float | None
    displacement_m: float | None
    effective_threshold_m: float | None
    sample_count: int
    last_meaningful_movement: datetime | None


class GPSHistory:
    """Small rolling GPS history for a single entity."""

    def __init__(
        self,
        history_window: int,
        comparison_age: int,
        min_reference_age: int,
        min_distance_m: float,
        default_accuracy: float,
        stationary_timeout: int,
    ) -> None:
        self.history_window = history_window
        self.comparison_age = min(comparison_age, history_window)
        self.min_reference_age = min(min_reference_age, self.comparison_age)
        self.min_distance_m = min_distance_m
        self.default_accuracy = default_accuracy
        self.stationary_timeout = stationary_timeout
        self.samples: deque[GPSSample] = deque(maxlen=MAX_HISTORY_SAMPLES)
        self.last_meaningful_movement: datetime | None = None

    def add_sample(self, sample: GPSSample) -> None:
        """Add a sample while limiting very high-frequency updates."""
        if self.samples and sample.timestamp < self.samples[-1].timestamp:
            self._insert_historical_sample(sample)
            return

        if self.samples:
            spacing = (sample.timestamp - self.samples[-1].timestamp).total_seconds()
            if spacing < MIN_SAMPLE_SPACING_SECONDS:
                self.samples[-1] = sample
            else:
                self.samples.append(sample)
        else:
            self.samples.append(sample)

        self.prune(sample.timestamp)

    def _insert_historical_sample(self, sample: GPSSample) -> None:
        """Insert an out-of-order sample while rebuilding Recorder history."""
        combined = list(self.samples)
        combined.append(sample)
        combined.sort(key=lambda item: item.timestamp)
        self.samples = deque(combined[-MAX_HISTORY_SAMPLES:], maxlen=MAX_HISTORY_SAMPLES)
        self.prune(combined[-1].timestamp)

    def prune(self, now: datetime) -> None:
        """Discard samples outside the rolling history window."""
        cutoff = now - timedelta(seconds=self.history_window)
        while self.samples and self.samples[0].timestamp < cutoff:
            self.samples.popleft()

    def evaluate(self, *, now: datetime | None = None) -> MovementEvaluation:
        """Evaluate movement using a suitably old historical position."""
        if not self.samples:
            return MovementEvaluation(None, None, None, None, None, None, 0, None)

        current = self.samples[-1]
        now = now or current.timestamp
        self.prune(now)

        if not self.samples:
            return MovementEvaluation(None, None, None, None, None, None, 0, None)

        current = self.samples[-1]
        candidates: list[tuple[float, GPSSample]] = []
        for sample in self.samples:
            if sample is current:
                continue
            age = (current.timestamp - sample.timestamp).total_seconds()
            if self.min_reference_age <= age <= self.history_window:
                candidates.append((age, sample))

        if not candidates:
            return MovementEvaluation(
                None,
                current,
                None,
                None,
                None,
                None,
                len(self.samples),
                self.last_meaningful_movement,
            )

        reference_age, reference = min(
            candidates,
            key=lambda item: abs(item[0] - self.comparison_age),
        )

        displacement_m = float(
            location_util.distance(
                current.latitude,
                current.longitude,
                reference.latitude,
                reference.longitude,
            )
        )

        current_accuracy = (
            current.accuracy if current.accuracy is not None else self.default_accuracy
        )
        reference_accuracy = (
            reference.accuracy
            if reference.accuracy is not None
            else self.default_accuracy
        )

        # Treat the reported accuracies as uncertainty radii. Requiring movement
        # beyond their sum is deliberately conservative and suppresses GPS drift.
        effective_threshold_m = max(
            self.min_distance_m,
            current_accuracy + reference_accuracy,
        )

        meaningful = displacement_m > effective_threshold_m
        if meaningful:
            self.last_meaningful_movement = current.timestamp

        is_moving = meaningful
        if (
            not meaningful
            and self.last_meaningful_movement is not None
            and (current.timestamp - self.last_meaningful_movement).total_seconds()
            <= self.stationary_timeout
        ):
            is_moving = True

        return MovementEvaluation(
            is_moving,
            current,
            reference,
            reference_age,
            displacement_m,
            effective_threshold_m,
            len(self.samples),
            self.last_meaningful_movement,
        )


def sample_from_state(state: State) -> GPSSample | None:
    """Build a validated GPS sample from a Home Assistant state."""
    latitude = state.attributes.get(ATTR_LATITUDE)
    longitude = state.attributes.get(ATTR_LONGITUDE)
    if latitude is None or longitude is None:
        return None

    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError):
        return None

    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        return None

    raw_accuracy = state.attributes.get(ATTR_GPS_ACCURACY)
    accuracy: float | None = None
    if raw_accuracy is not None:
        try:
            parsed_accuracy = float(raw_accuracy)
        except (TypeError, ValueError):
            pass
        else:
            if parsed_accuracy >= 0:
                accuracy = parsed_accuracy

    return GPSSample(
        timestamp=state.last_updated,
        latitude=lat,
        longitude=lon,
        accuracy=accuracy,
    )


class MovementCoordinator(DataUpdateCoordinator[dict[str, MovementEvaluation]]):
    """Maintain live GPS histories and expose movement evaluations."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self.targets: list[str] = entry.options.get(
            CONF_TARGETS, entry.data.get(CONF_TARGETS, [])
        )

        options = entry.options
        history_window = int(
            options.get(CONF_MOVEMENT_HISTORY_WINDOW, DEFAULT_MOVEMENT_HISTORY_WINDOW)
        )
        comparison_age = int(
            options.get(CONF_MOVEMENT_COMPARISON_AGE, DEFAULT_MOVEMENT_COMPARISON_AGE)
        )
        min_reference_age = int(
            options.get(
                CONF_MOVEMENT_MIN_REFERENCE_AGE,
                DEFAULT_MOVEMENT_MIN_REFERENCE_AGE,
            )
        )
        min_distance_m = float(
            options.get(
                CONF_MOVEMENT_MIN_DISTANCE_M,
                DEFAULT_MOVEMENT_MIN_DISTANCE_M,
            )
        )
        default_accuracy = float(
            options.get(
                CONF_MOVEMENT_DEFAULT_ACCURACY,
                DEFAULT_MOVEMENT_DEFAULT_ACCURACY,
            )
        )
        stationary_timeout = int(
            options.get(
                CONF_MOVEMENT_STATIONARY_TIMEOUT,
                DEFAULT_MOVEMENT_STATIONARY_TIMEOUT,
            )
        )

        self.histories = {
            entity_id: GPSHistory(
                history_window,
                comparison_age,
                min_reference_age,
                min_distance_m,
                default_accuracy,
                stationary_timeout,
            )
            for entity_id in self.targets
        }
        self._history_window = history_window
        self._last_publish = 0.0

        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_movement",
        )

    async def async_start(self) -> None:
        """Restore recent Recorder history, then start listening for live updates."""
        await self._async_restore_history()

        for entity_id in self.targets:
            state = self.hass.states.get(entity_id)
            if state is not None:
                self._add_state(entity_id, state)

        self._publish(force=True)

        if self.targets:
            self.entry.async_on_unload(
                async_track_state_change_event(
                    self.hass,
                    self.targets,
                    self._async_state_changed,
                )
            )
            self.entry.async_on_unload(
                async_track_time_interval(
                    self.hass,
                    self._async_periodic_refresh,
                    timedelta(seconds=ENTITY_REFRESH_INTERVAL),
                )
            )

    async def _async_restore_history(self) -> None:
        """Query Recorder once to rebuild the recent in-memory GPS history."""
        if not self.targets:
            return

        try:
            recorder = get_instance(self.hass)
        except (KeyError, RuntimeError):
            _LOGGER.debug("Recorder is not available; starting movement history empty")
            return

        try:
            recorder_ready = await recorder.async_db_ready
        except (RuntimeError, KeyError):
            _LOGGER.debug("Recorder did not become ready; starting movement history empty")
            return

        if not recorder_ready:
            _LOGGER.debug("Recorder is unavailable; starting movement history empty")
            return

        end_time = dt_util.utcnow()
        start_time = end_time - timedelta(seconds=self._history_window)

        try:
            states_by_entity = await recorder.async_add_executor_job(
                history.get_significant_states,
                self.hass,
                start_time,
                end_time,
                self.targets,
                None,
                False,
                False,
                False,
                False,
                False,
            )
        except Exception:
            _LOGGER.exception("Unable to restore recent GPS history from Recorder")
            return

        for entity_id, states in states_by_entity.items():
            if entity_id not in self.histories:
                continue
            for state in states:
                if isinstance(state, State):
                    self._add_state(entity_id, state)

    @callback
    def _async_state_changed(self, event: Event[EventStateChangedData]) -> None:
        """Process a live source-entity state or attribute update."""
        entity_id = event.data["entity_id"]
        new_state = event.data["new_state"]
        if new_state is None or entity_id not in self.histories:
            return

        self._add_state(entity_id, new_state)
        self._publish()

    @callback
    def _async_periodic_refresh(self, now: datetime) -> None:
        """Re-evaluate stale data and refresh diagnostics at a low frequency."""
        self._publish(now=now)

    @callback
    def _add_state(self, entity_id: str, state: State) -> None:
        """Add valid coordinates from one state to the target history."""
        sample = sample_from_state(state)
        if sample is not None:
            self.histories[entity_id].add_sample(sample)

    @callback
    def _evaluate_all(self, now: datetime | None = None) -> dict[str, MovementEvaluation]:
        """Return current movement evaluations for all configured targets."""
        now = now or dt_util.utcnow()
        return {
            entity_id: gps_history.evaluate(now=now)
            for entity_id, gps_history in self.histories.items()
        }

    @callback
    def _publish(self, *, force: bool = False, now: datetime | None = None) -> None:
        """Publish immediately on state transitions, otherwise at most once a minute."""
        evaluations = self._evaluate_all(now)
        previous = self.data or {}
        state_changed = any(
            previous.get(entity_id) is None
            or previous[entity_id].is_moving != evaluation.is_moving
            for entity_id, evaluation in evaluations.items()
        )

        monotonic_now = time.monotonic()
        if (
            force
            or state_changed
            or monotonic_now - self._last_publish >= ENTITY_REFRESH_INTERVAL
        ):
            self._last_publish = monotonic_now
            self.async_set_updated_data(evaluations)

    async def _async_update_data(self) -> dict[str, MovementEvaluation]:
        """Return current in-memory evaluations for an explicit refresh."""
        return self._evaluate_all()
