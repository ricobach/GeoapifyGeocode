"""
GeoapifyGeocode - sensor platform

Creates one sensor per selected target entity (person/device_tracker).

Sensor state: Geoapify "formatted" address
Attributes: country, timezone (full dict), timezone_name, source_entity, source_friendly_name, lat, lon, raw_properties, display_name
"""

from __future__ import annotations

import hashlib
import logging
from datetime import timedelta

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_API_KEY,
    CONF_TARGETS,
    DEFAULT_MIN_DISTANCE_M,
    DEFAULT_SCAN_INTERVAL,
    ATTR_COUNTRY,
    ATTR_TIMEZONE,
    ATTR_TIMEZONE_NAME,
    ATTR_SOURCE_ENTITY,
    ATTR_LAT,
    ATTR_LON,
    ATTR_RAW_PROPERTIES,
)

from .coordinator import GeoapifyReverseClient, TargetStateCache, ReverseResult

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Geoapify reverse geocode sensors from a config entry."""
    api_key = entry.data[CONF_API_KEY]

    # Targets can be configured in initial config entry data or overridden in options
    targets = entry.options.get(CONF_TARGETS, entry.data.get(CONF_TARGETS, []))

    scan_interval = int(entry.options.get("scan_interval", DEFAULT_SCAN_INTERVAL))
    min_distance_m = int(entry.options.get("min_distance_m", DEFAULT_MIN_DISTANCE_M))

    client = GeoapifyReverseClient(hass, api_key)
    cache = TargetStateCache()

    async def _async_update_data() -> dict[str, ReverseResult]:
        """
        Update data for all targets.

        Calls Geoapify only if the target moved >= min_distance_m since last successful call.
        Otherwise serves cached results.
        """
        results: dict[str, ReverseResult] = {}

        for entity_id in targets:
            st = hass.states.get(entity_id)
            if not st:
                _LOGGER.debug("Target entity missing: %s", entity_id)
                continue

            lat = st.attributes.get("latitude")
            lon = st.attributes.get("longitude")
            if lat is None or lon is None:
                _LOGGER.debug("Target %s missing lat/lon attributes", entity_id)
                continue

            try:
                lat_f = float(lat)
                lon_f = float(lon)
            except (TypeError, ValueError):
                _LOGGER.debug("Target %s lat/lon not numeric: lat=%s lon=%s", entity_id, lat, lon)
                continue

            # Only call Geoapify if moved enough; else use cache if present
            if cache.should_update(entity_id, lat_f, lon_f, min_distance_m):
                try:
                    result = await client.reverse(lat_f, lon_f)
                    cache.set(entity_id, result)
                    results[entity_id] = result
                except Exception as e:
                    # If we have cached data, keep it; otherwise fail the update
                    if entity_id in cache.last_result:
                        _LOGGER.warning("Geoapify update failed for %s, using cached. Error: %s", entity_id, e)
                        results[entity_id] = cache.last_result[entity_id]
                    else:
                        raise UpdateFailed(str(e)) from e
            else:
                if entity_id in cache.last_result:
                    results[entity_id] = cache.last_result[entity_id]

        return results

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="GeoapifyGeocode",
        update_method=_async_update_data,
        update_interval=timedelta(seconds=scan_interval),
    )

    await coordinator.async_config_entry_first_refresh()

    entities: list[GeoapifyGeocodeSensor] = []
    for entity_id in targets:
        st = hass.states.get(entity_id)
        friendly = st.attributes.get("friendly_name") if st else entity_id
        entities.append(GeoapifyGeocodeSensor(coordinator, entry, entity_id, friendly))

    async_add_entities(entities)


class GeoapifyGeocodeSensor(SensorEntity):
    """Sensor representing reverse geocode result for a target entity."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        entry: ConfigEntry,
        source_entity: str,
        friendly_name: str,
    ) -> None:
        self.coordinator = coordinator
        self._entry = entry
        self._source = source_entity
        self._friendly = friendly_name

        # Stable unique_id per (config entry, source entity)
        raw = f"{entry.entry_id}:{source_entity}".encode("utf-8")
        uid = hashlib.sha1(raw).hexdigest()
        self._attr_unique_id = f"{entry.entry_id}_{uid}"

        # Visible name in HA
        # (If the person/device tracker friendly_name changes later, this name won't auto-update.)
        self._attr_name = f"{self._friendly} Geocode"

    @property
    def available(self) -> bool:
        """Return True if the entity is available."""
        return self.coordinator.last_update_success

    @property
    def native_value(self):
        """Return the sensor state (formatted address)."""
        data = self.coordinator.data or {}
        result: ReverseResult | None = data.get(self._source)
        if not result:
            return None
        return result.formatted

    @property
    def extra_state_attributes(self):
        """Return extra attributes."""
        data = self.coordinator.data or {}
        result: ReverseResult | None = data.get(self._source)

        st = self.hass.states.get(self._source) if self.hass else None
        friendly = st.attributes.get("friendly_name") if st else self._friendly

        attrs = {
            ATTR_SOURCE_ENTITY: self._source,
            "source_friendly_name": friendly,
            "display_name": f"{friendly} Geocode",
        }

        if not result:
            return attrs

        attrs[ATTR_COUNTRY] = result.country
        attrs[ATTR_TIMEZONE] = result.timezone
        attrs[ATTR_TIMEZONE_NAME] = (result.timezone or {}).get("name")
        attrs[ATTR_LAT] = result.lat
        attrs[ATTR_LON] = result.lon
        attrs[ATTR_RAW_PROPERTIES] = result.properties

        return attrs

    async def async_update(self) -> None:
        """Manually trigger an update."""
        await self.coordinator.async_request_refresh()

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass, register coordinator listener."""
        self.async_on_remove(self.coordinator.async_add_listener(self.async_write_ha_state))

