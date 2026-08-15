"""GPS movement detection and restart recovery for GeoapifyGeocode."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import timedelta
from functools import partial
import logging
from typing import Any

from homeassistant.components.recorder import get_instance, history as recorder_history
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_GPS_ACCURACY, ATTR_LATITUDE, ATTR_LONGITUDE
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util
from homeassistant.util.location import vincenty

from .const import (
    CONF_MOVEMENT_COMPARISON_AGE,
    CONF_MOVEMENT_DEFAULT_ACCURACY_M,
    CONF_MOVEMENT_HISTORY_WINDOW,
    CONF_MOVEMENT_MIN_DISTANCE_M,
    CONF_MOVEMENT_MIN_REFERENCE_AGE,
    CONF_MOVEMENT_STATIONARY_TIMEOUT,
    CONF_TARGETS,
    DEFAULT_MOVEMENT_COMPARISON_AGE,
    DEFAULT_MOVEMENT_DEFAULT_ACCURACY_M,
    DEFAULT_MOVEMENT_HISTORY_WINDOW,
    DEFAULT_MOVEMENT_MIN_DISTANCE_M,
    DEFAULT_MOVEMENT_MIN_REFERENCE_AGE,
    DEFAULT_MOVEMENT_STATIONARY_TIMEOUT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)
MAX_SAMPLES_PER_TARGET = 512


@dataclass(frozen=True, slots=True)
class GPSSample:
    """One GPS observation."""

    timestamp: float
    latitude: float
    longitude: float
    accuracy: float | None


@dataclass(frozen=True, slots=True)
class MovementEvaluation:
    """Calculated movement state and diagnostics for one tracked entity."""

    is_moving: bool | None
    current: GPSSample | None
    reference: GPSSample | None
    reference_age: float | None
    displacement_m: float | None
    effective_threshold_m: float | None
    sample_count: int
    last_meaningful_movement: float | None


def _coerce_coordinate(value: Any, minimum: float, maximum: float) -> float | None:
    """Convert and validate a coordinate."""
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not minimum <= result <= maximum:
        return None
    return result


def _coerce_accuracy(value: Any) -> float | None:
    """Convert GPS accuracy to a non-negative number when possible."""
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


def sample_from_state(state: State | None) -> GPSSample | None:
    """Create a GPS sample from a Home Assistant state."""
    if state is None:
        return None

    latitude = _coerce_coordinate(state.attributes.get(ATTR_LATITUDE), -90.0, 90.0)
    longitude = _coerce_coordinate(state.attributes.get(ATTR_LONGITUDE), -180.0, 180.0)
    if latitude is None or longitude is None:
        return None

    return GPSSample(
        timestamp=state.last_updated_timestamp,
        latitude=latitude,
        longitude=longitude,
        accuracy=_coerce_accuracy(state.attributes.get(ATTR_GPS_ACCURACY)),
    )


def distance_m(first: GPSSample, second: GPSSample) -> float | None:
    """Return distance between GPS samples in metres using Home Assistant utilities."""
    distance_km = vincenty(
        (first.latitude, first.longitude),
        (second.latitude, second.longitude),
        miles=False,
    )
    return None if distance_km is None else distance_km * 1000.0


class MovementHistory:
    """Rolling GPS history and movement calculation for one source entity."""

    def __init__(
        self,
        *,
        history_window: int = DEFAULT_MOVEMENT_HISTORY_WINDOW,
        comparison_age: int = DEFAULT_MOVEMENT_COMPARISON_AGE,
        min_reference_age: int = DEFAULT_MOVEMENT_MIN_REFERENCE_AGE,
        min_distance_m: float = DEFAULT_MOVEMENT_MIN_DISTANCE_M,
        default_accuracy_m: float = DEFAULT_MOVEMENT_DEFAULT_ACCURACY_M,
        stationary_timeout: int = DEFAULT_MOVEMENT_STATIONARY_TIMEOUT,
    ) -> None:
        self.history_window = history_window
        self.comparison_age = comparison_age
        self.min_reference_age = min_reference_age
        self.min_distance_m = float(min_distance_m)
        self.default_accuracy_m = float(default_accuracy_m)
        self.stationary_timeout = stationary_timeout
        self.samples: deque[GPSSample] = deque(maxlen=MAX_SAMPLES_PER_TARGET)
        self.last_meaningful_movement: float | None = None

    def add(self, sample: GPSSample) -> None:
        """Add a sample while tolerating duplicate and out-of-order records."""
        if self.samples and sample.timestamp < self.samples[-1].timestamp:
            merged = sorted((*self.samples, sample), key=lambda item: item.timestamp)
            self.samples = deque(
                merged[-MAX_SAMPLES_PER_TARGET:], maxlen=MAX_SAMPLES_PER_TARGET
            )
            return
        self.samples.append(sample)

    def prune(self, now: float) -> None:
        """Drop samples older than the configured rolling window."""
        cutoff = now - self.history_window
        while self.samples and self.samples[0].timestamp < cutoff:
            self.samples.popleft()

    def _reference_for(self, current: GPSSample) -> GPSSample | None:
        """Pick the suitable sample closest to the configured comparison age."""
        candidates = [
            sample
            for sample in self.samples
            if self.min_reference_age
            <= current.timestamp - sample.timestamp
            <= self.history_window
        ]
        if not candidates:
            return None

        return min(
            candidates,
            key=lambda sample: abs(
                (current.timestamp - sample.timestamp) - self.comparison_age
            ),
        )

    def evaluate(self, *, now: float | None = None) -> MovementEvaluation:
        """Evaluate whether the target is moving."""
        now = dt_util.utcnow().timestamp() if now is None else now
        self.prune(now)

        if not self.samples:
            return MovementEvaluation(
                None, None, None, None, None, None, 0, self.last_meaningful_movement
            )

        current = self.samples[-1]
        reference = self._reference_for(current)
        if reference is None:
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

        displacement = distance_m(reference, current)
        if displacement is None:
            return MovementEvaluation(
                None,
                current,
                reference,
                current.timestamp - reference.timestamp,
                None,
                None,
                len(self.samples),
                self.last_meaningful_movement,
            )

        current_accuracy = current.accuracy if current.accuracy is not None else self.default_accuracy_m
        reference_accuracy = reference.accuracy if reference.accuracy is not None else self.default_accuracy_m
        effective_threshold = max(
            self.min_distance_m,
            current_accuracy + reference_accuracy,
        )

        meaningful = displacement > effective_threshold
        if meaningful:
            self.last_meaningful_movement = current.timestamp
            is_moving = True
        elif (
            self.last_meaningful_movement is not None
            and self.stationary_timeout > 0
            and now - self.last_meaningful_movement < self.stationary_timeout
        ):
            is_moving = True
        else:
            is_moving = False

        return MovementEvaluation(
            is_moving,
            current,
            reference,
            current.timestamp - reference.timestamp,
            displacement,
            effective_threshold,
            len(self.samples),
            self.last_meaningful_movement,
        )


class MovementCoordinator(DataUpdateCoordinator[dict[str, MovementEvaluation]]):
    """Maintain live in-memory GPS histories for configured targets."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self.targets: list[str] = list(
            entry.options.get(CONF_TARGETS, entry.data.get(CONF_TARGETS, []))
        )

        options = entry.options
        self.history_window = int(
            options.get(CONF_MOVEMENT_HISTORY_WINDOW, DEFAULT_MOVEMENT_HISTORY_WINDOW)
        )
        self.comparison_age = int(
            options.get(CONF_MOVEMENT_COMPARISON_AGE, DEFAULT_MOVEMENT_COMPARISON_AGE)
        )
        self.min_reference_age = int(
            options.get(
                CONF_MOVEMENT_MIN_REFERENCE_AGE,
                DEFAULT_MOVEMENT_MIN_REFERENCE_AGE,
            )
        )
        self.min_distance_m = float(
            options.get(CONF_MOVEMENT_MIN_DISTANCE_M, DEFAULT_MOVEMENT_MIN_DISTANCE_M)
        )
        self.default_accuracy_m = float(
            options.get(
                CONF_MOVEMENT_DEFAULT_ACCURACY_M,
                DEFAULT_MOVEMENT_DEFAULT_ACCURACY_M,
            )
        )
        self.stationary_timeout = int(
            options.get(
                CONF_MOVEMENT_STATIONARY_TIMEOUT,
                DEFAULT_MOVEMENT_STATIONARY_TIMEOUT,
            )
        )

        self.histories = {entity_id: self._new_history() for entity_id in self.targets}

        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_movement",
        )

    def _new_history(self) -> MovementHistory:
        return MovementHistory(
            history_window=self.history_window,
            comparison_age=self.comparison_age,
            min_reference_age=self.min_reference_age,
            min_distance_m=self.min_distance_m,
            default_accuracy_m=self.default_accuracy_m,
            stationary_timeout=self.stationary_timeout,
        )

    async def async_initialize(self) -> None:
        """Restore recent GPS samples once from Recorder, then add current states."""
        await self._async_restore_from_recorder()

        for entity_id in self.targets:
            sample = sample_from_state(self.hass.states.get(entity_id))
            if sample is not None:
                self.histories[entity_id].add(sample)

        self.async_set_updated_data(self._evaluate_all())

    async def _async_restore_from_recorder(self) -> None:
        """Load recent state history once for restart recovery."""
        if not self.targets:
            return

        end_time = dt_util.utcnow()
        start_time = end_time - timedelta(seconds=self.history_window)
        query = partial(
            recorder_history.get_significant_states,
            self.hass,
            start_time,
            end_time,
            entity_ids=self.targets,
            include_start_time_state=False,
            significant_changes_only=False,
            minimal_response=False,
            no_attributes=False,
        )

        try:
            states_by_entity = await get_instance(self.hass).async_add_executor_job(query)
        except Exception:
            _LOGGER.warning(
                "Unable to restore recent GPS history from Recorder; movement history will rebuild from live updates",
                exc_info=True,
            )
            return

        for entity_id in self.targets:
            history = self.histories[entity_id]
            for state in states_by_entity.get(entity_id, []):
                sample = sample_from_state(state)
                if sample is not None:
                    history.add(sample)

    @callback
    def async_start(self) -> CALLBACK_TYPE:
        """Start listening to live target state and attribute updates."""
        if not self.targets:
            return lambda: None
        return async_track_state_change_event(
            self.hass,
            self.targets,
            self._async_state_changed,
        )

    @callback
    def _async_state_changed(self, event: Event[EventStateChangedData]) -> None:
        """Add a live GPS sample whenever a tracked entity updates."""
        new_state = event.data["new_state"]
        if new_state is None:
            return

        entity_id = new_state.entity_id
        history = self.histories.get(entity_id)
        if history is None:
            return

        sample = sample_from_state(new_state)
        if sample is None:
            self.async_set_updated_data(self._evaluate_all())
            return

        history.add(sample)
        self.async_set_updated_data(self._evaluate_all(now=sample.timestamp))

    def _evaluate_all(self, *, now: float | None = None) -> dict[str, MovementEvaluation]:
        """Evaluate movement for every target."""
        now = dt_util.utcnow().timestamp() if now is None else now
        return {
            entity_id: history.evaluate(now=now)
            for entity_id, history in self.histories.items()
        }
