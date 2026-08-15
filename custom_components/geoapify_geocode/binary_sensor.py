"""Binary sensor platform for GeoapifyGeocode GPS movement detection."""

from __future__ import annotations

import hashlib
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import GeoapifyConfigEntry
from .const import CONF_TARGETS
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
    """Return the source entity's current friendly name."""
    state = hass.states.get(entity_id)
    if state is None:
        return entity_id
    return state.attributes.get("friendly_name", entity_id)


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
        data = self.coordinator.data or {}
        return data.get(self._source)

    @property
    def is_on(self) -> bool | None:
        """Return whether meaningful GPS movement is detected."""
        evaluation = self._evaluation
        return evaluation.is_moving if evaluation else None

    @property
    def entity_picture(self) -> str | None:
        """Return the current picture from the tracked source entity."""
        if not self.hass:
            return None
        state = self.hass.states.get(self._source)
        if state is None:
            return None
        return state.attributes.get("entity_picture")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return movement diagnostics without exposing the rolling history."""
        evaluation = self._evaluation
        attrs: dict[str, Any] = {"source_entity": self._source}

        if evaluation is None:
            return attrs

        attrs["gps_samples"] = evaluation.sample_count

        if evaluation.current is not None:
            attrs.update(
                {
                    "current_latitude": evaluation.current.latitude,
                    "current_longitude": evaluation.current.longitude,
                    "current_gps_accuracy": evaluation.current.accuracy,
                }
            )

        if evaluation.reference is not None:
            attrs.update(
                {
                    "reference_latitude": evaluation.reference.latitude,
                    "reference_longitude": evaluation.reference.longitude,
                    "reference_gps_accuracy": evaluation.reference.accuracy,
                }
            )

        attrs.update(
            {
                "reference_age_seconds": evaluation.reference_age,
                "displacement_m": evaluation.displacement_m,
                "effective_movement_threshold_m": evaluation.effective_threshold_m,
                "last_meaningful_movement": (
                    evaluation.last_meaningful_movement.isoformat()
                    if evaluation.last_meaningful_movement
                    else None
                ),
            }
        )

        return {key: value for key, value in attrs.items() if value is not None}
