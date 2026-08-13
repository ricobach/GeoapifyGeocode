"""Sensor platform for GeoapifyGeocode."""

from __future__ import annotations

import hashlib
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import GeoapifyConfigEntry
from .const import (
    ATTR_CITY,
    ATTR_COUNTRY,
    ATTR_COUNTRY_CODE,
    ATTR_COUNTY,
    ATTR_DISTANCE,
    ATTR_HOUSENUMBER,
    ATTR_LAT,
    ATTR_LON,
    ATTR_POSTCODE,
    ATTR_RESULT_TYPE,
    ATTR_SOURCE_ENTITY,
    ATTR_STATE,
    ATTR_STREET,
    ATTR_TIMEZONE,
    ATTR_TIMEZONE_NAME,
    CONF_TARGETS,
)
from .coordinator import GeoapifyCoordinator, GeoapifyResult


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GeoapifyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up GeoapifyGeocode sensors."""
    coordinator = entry.runtime_data.coordinator
    targets = entry.options.get(CONF_TARGETS, entry.data.get(CONF_TARGETS, []))

    async_add_entities(
        GeoapifyGeocodeSensor(
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


class GeoapifyGeocodeSensor(CoordinatorEntity[GeoapifyCoordinator], SensorEntity):
    """Reverse-geocoded address for one Home Assistant location entity."""

    _attr_has_entity_name = True
    _attr_translation_key = "geocode"

    def __init__(
        self,
        coordinator: GeoapifyCoordinator,
        entry: GeoapifyConfigEntry,
        source_entity: str,
        friendly_name: str,
    ) -> None:
        super().__init__(coordinator, context=source_entity)
        self._source = source_entity
        self._fallback_friendly_name = friendly_name

        # Keep the v1.0 unique-ID algorithm so upgrades retain entity registry entries.
        raw = f"{entry.entry_id}:{source_entity}".encode()
        uid = hashlib.sha1(raw).hexdigest()
        self._attr_unique_id = f"{entry.entry_id}_{uid}"
        self._attr_translation_placeholders = {"source": friendly_name}

    @property
    def available(self) -> bool:
        """Return whether this specific source has a usable result."""
        return super().available and self._result is not None

    @property
    def _result(self) -> GeoapifyResult | None:
        data = self.coordinator.data or {}
        return data.get(self._source)

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
    def native_value(self) -> str | None:
        """Return the formatted reverse-geocoded address."""
        result = self._result
        return result.formatted if result else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return selected, recorder-friendly Geoapify attributes."""
        result = self._result
        state = self.hass.states.get(self._source) if self.hass else None
        friendly = (
            state.attributes.get("friendly_name", self._fallback_friendly_name)
            if state
            else self._fallback_friendly_name
        )

        attrs: dict[str, Any] = {
            ATTR_SOURCE_ENTITY: self._source,
            "source_friendly_name": friendly,
        }

        if result is None:
            return attrs

        properties = result.properties
        attrs.update(
            {
                ATTR_COUNTRY: result.country,
                ATTR_COUNTRY_CODE: properties.get("country_code"),
                ATTR_STATE: properties.get("state"),
                ATTR_COUNTY: properties.get("county"),
                ATTR_CITY: properties.get("city"),
                ATTR_POSTCODE: properties.get("postcode"),
                ATTR_STREET: properties.get("street"),
                ATTR_HOUSENUMBER: properties.get("housenumber"),
                ATTR_RESULT_TYPE: properties.get("result_type"),
                ATTR_DISTANCE: properties.get("distance"),
                ATTR_TIMEZONE: result.timezone,
                ATTR_TIMEZONE_NAME: (result.timezone or {}).get("name"),
                ATTR_LAT: result.lat,
                ATTR_LON: result.lon,
            }
        )
        return {key: value for key, value in attrs.items() if value is not None}
