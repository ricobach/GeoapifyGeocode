"""Movement binary sensors for GeoapifyGeocode."""

from __future__ import annotations

import hashlib
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import ATTR_ENTITY_PICTURE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import GeoapifyConfigEntry
from .const import (
    ATTR_CURRENT_GPS_ACCURACY,
    ATTR_CURRENT_LATITUDE,
    ATTR_CURRENT_LONGITUDE,
    ATTR_DISPLACEMENT,
    ATTR_EFFECTIVE_MOVEMENT_THRESHOLD,
    ATTR_GPS_SAMPLE_COUNT,
    ATTR_LAST_MEANINGFUL_MOVEMENT,
    ATTR_REFERENCE_AGE,
    ATTR_REFERENCE_GPS_ACCURACY,
    ATTR_REFERENCE_LATITUDE,
    ATTR_REFERENCE_LONGITUDE,
    ATTR_SOURCE_ENTITY,
    CONF_TARGETS,
)
from .movement import MovementCoordinator, MovementEvaluation


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GeoapifyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up GPS movement binary sensors."""
    coordinator = entry.runtime_data.movement_coordinator
    targets = entry.options.get(CONF_TARGETS, entry.data.get(CONF_TARGETS, []))

    async_add_entities(
        GeoapifyMovementBinarySensor(
            coordinator,
            entry,
            entity_id,
            _friendly_name(hass, entity_id),
        )
        for entity_id in targets
    )


def _friendly_name(hass: HomeAssistant, entity_id: str) -> str:
    """Return the source entity friendly name."""
    state = hass.states.get(entity_id)
    return state.attributes.get("friendly_name", entity_id) if state else entity_id


class GeoapifyMovementBinarySensor(
    CoordinatorEntity[MovementCoordinator], BinarySensorEntity
):
    """GPS movement state for one tracked Home Assistant entity."""

    _attr_device_class = BinarySensorDeviceClass.MOVING
    _attr_has_entity_name = True
    _attr_translation_key = "moving"

    def __init__(
        self,
        coordinator: MovementCoordinator,
        entry: GeoapifyConfigEntry,
        source_entity: str,
        friendly_name: str,
    ) -> None:
        super().__init__(coordinator, context=source_entity)
        self._source = source_entity

        raw = f"{entry.entry_id}:{source_entity}".encode()
        uid = hashlib.sha1(raw).hexdigest()
        self._attr_unique_id = f"{entry.entry_id}_{uid}_moving"
        self._attr_translation_placeholders = {"source": friendly_name}

    @property
    def _evaluation(self) -> MovementEvaluation | None:
        return (self.coordinator.data or {}).get(self._source)

    @property
    def is_on(self) -> bool | None:
        """Return movement state or unknown when history is insufficient."""
        evaluation = self._evaluation
        return evaluation.is_moving if evaluation else None

    @property
    def entity_picture(self) -> str | None:
        """Copy the source picture when this entity updates."""
        if not self.hass:
            return None
        state = self.hass.states.get(self._source)
        return state.attributes.get(ATTR_ENTITY_PICTURE) if state else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose movement diagnostics without exposing the rolling history."""
        evaluation = self._evaluation
        attrs: dict[str, Any] = {ATTR_SOURCE_ENTITY: self._source}
        if evaluation is None:
            return attrs

        current = evaluation.current
        reference = evaluation.reference
        attrs.update(
            {
                ATTR_CURRENT_LATITUDE: current.latitude if current else None,
                ATTR_CURRENT_LONGITUDE: current.longitude if current else None,
                ATTR_REFERENCE_LATITUDE: reference.latitude if reference else None,
                ATTR_REFERENCE_LONGITUDE: reference.longitude if reference else None,
                ATTR_REFERENCE_AGE: round(evaluation.reference_age, 1)
                if evaluation.reference_age is not None
                else None,
                ATTR_DISPLACEMENT: round(evaluation.displacement_m, 1)
                if evaluation.displacement_m is not None
                else None,
                ATTR_CURRENT_GPS_ACCURACY: current.accuracy if current else None,
                ATTR_REFERENCE_GPS_ACCURACY: reference.accuracy if reference else None,
                ATTR_EFFECTIVE_MOVEMENT_THRESHOLD: round(
                    evaluation.effective_threshold_m, 1
                )
                if evaluation.effective_threshold_m is not None
                else None,
                ATTR_GPS_SAMPLE_COUNT: evaluation.sample_count,
                ATTR_LAST_MEANINGFUL_MOVEMENT: dt_util.utc_from_timestamp(
                    evaluation.last_meaningful_movement
                )
                if evaluation.last_meaningful_movement is not None
                else None,
            }
        )
        return {key: value for key, value in attrs.items() if value is not None}
