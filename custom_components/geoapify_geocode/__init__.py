"""The GeoapifyGeocode integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import (
    CONF_API_KEY,
    CONF_MAX_AGE,
    CONF_MIN_DISTANCE_M,
    CONF_MOVEMENT_COMPARISON_AGE,
    CONF_MOVEMENT_DEFAULT_ACCURACY,
    CONF_MOVEMENT_HISTORY_WINDOW,
    CONF_MOVEMENT_MIN_DISTANCE_M,
    CONF_MOVEMENT_MIN_REFERENCE_AGE,
    CONF_MOVEMENT_STATIONARY_TIMEOUT,
    CONF_SCAN_INTERVAL,
    CONF_SOURCE_ENTITY,
    CONF_TARGETS,
    DEFAULT_MAX_AGE,
    DEFAULT_MIN_DISTANCE_M,
    DEFAULT_MOVEMENT_COMPARISON_AGE,
    DEFAULT_MOVEMENT_DEFAULT_ACCURACY,
    DEFAULT_MOVEMENT_HISTORY_WINDOW,
    DEFAULT_MOVEMENT_MIN_DISTANCE_M,
    DEFAULT_MOVEMENT_MIN_REFERENCE_AGE,
    DEFAULT_MOVEMENT_STATIONARY_TIMEOUT,
    DEFAULT_SCAN_INTERVAL,
    SUBENTRY_TYPE_TRACKED_ENTITY,
)
from .coordinator import GeoapifyClient, GeoapifyCoordinator
from .movement import MovementCoordinator

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]


@dataclass(slots=True)
class GeoapifyRuntimeData:
    """Runtime data for a GeoapifyGeocode config entry."""

    client: GeoapifyClient
    coordinator: GeoapifyCoordinator
    movement_coordinator: MovementCoordinator


type GeoapifyConfigEntry = ConfigEntry[GeoapifyRuntimeData]


async def _async_reload_entry(
    hass: HomeAssistant, entry: GeoapifyConfigEntry
) -> None:
    """Reload when configuration or subentries change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(
    hass: HomeAssistant, entry: GeoapifyConfigEntry
) -> bool:
    """Migrate legacy target-list configuration to one subentry per target."""
    if entry.version >= 2:
        return True

    options = dict(entry.options)
    targets = options.get(CONF_TARGETS, entry.data.get(CONF_TARGETS, []))
    existing_unique_ids = {subentry.unique_id for subentry in entry.subentries.values()}

    for source_entity in targets:
        if source_entity in existing_unique_ids:
            continue

        state = hass.states.get(source_entity)
        title = (
            state.attributes.get("friendly_name", source_entity)
            if state is not None
            else source_entity
        )
        data = {
            CONF_SOURCE_ENTITY: source_entity,
            CONF_SCAN_INTERVAL: int(
                options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
            CONF_MIN_DISTANCE_M: int(
                options.get(CONF_MIN_DISTANCE_M, DEFAULT_MIN_DISTANCE_M)
            ),
            CONF_MAX_AGE: int(options.get(CONF_MAX_AGE, DEFAULT_MAX_AGE)),
            CONF_MOVEMENT_HISTORY_WINDOW: int(
                options.get(
                    CONF_MOVEMENT_HISTORY_WINDOW,
                    DEFAULT_MOVEMENT_HISTORY_WINDOW,
                )
            ),
            CONF_MOVEMENT_COMPARISON_AGE: int(
                options.get(
                    CONF_MOVEMENT_COMPARISON_AGE,
                    DEFAULT_MOVEMENT_COMPARISON_AGE,
                )
            ),
            CONF_MOVEMENT_MIN_REFERENCE_AGE: int(
                options.get(
                    CONF_MOVEMENT_MIN_REFERENCE_AGE,
                    DEFAULT_MOVEMENT_MIN_REFERENCE_AGE,
                )
            ),
            CONF_MOVEMENT_MIN_DISTANCE_M: int(
                options.get(
                    CONF_MOVEMENT_MIN_DISTANCE_M,
                    DEFAULT_MOVEMENT_MIN_DISTANCE_M,
                )
            ),
            CONF_MOVEMENT_DEFAULT_ACCURACY: int(
                options.get(
                    CONF_MOVEMENT_DEFAULT_ACCURACY,
                    DEFAULT_MOVEMENT_DEFAULT_ACCURACY,
                )
            ),
            CONF_MOVEMENT_STATIONARY_TIMEOUT: int(
                options.get(
                    CONF_MOVEMENT_STATIONARY_TIMEOUT,
                    DEFAULT_MOVEMENT_STATIONARY_TIMEOUT,
                )
            ),
        }
        hass.config_entries.async_add_subentry(
            entry,
            ConfigSubentry(
                subentry_type=SUBENTRY_TYPE_TRACKED_ENTITY,
                title=title,
                unique_id=source_entity,
                data=data,  # type: ignore[arg-type]
            ),
        )

    hass.config_entries.async_update_entry(
        entry,
        data={CONF_API_KEY: entry.data[CONF_API_KEY]},
        options={},
        version=2,
        minor_version=0,
    )
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: GeoapifyConfigEntry
) -> bool:
    """Set up GeoapifyGeocode from a config entry."""
    client = GeoapifyClient(hass, entry.data[CONF_API_KEY])
    coordinator = GeoapifyCoordinator(hass, entry, client)
    movement_coordinator = MovementCoordinator(hass, entry)

    await coordinator.async_config_entry_first_refresh()
    await movement_coordinator.async_start()

    entry.runtime_data = GeoapifyRuntimeData(
        client=client,
        coordinator=coordinator,
        movement_coordinator=movement_coordinator,
    )
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: GeoapifyConfigEntry
) -> bool:
    """Unload a GeoapifyGeocode config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
