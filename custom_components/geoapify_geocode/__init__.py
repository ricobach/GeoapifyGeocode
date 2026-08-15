"""The GeoapifyGeocode integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_API_KEY
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
    """Reload when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(
    hass: HomeAssistant, entry: GeoapifyConfigEntry
) -> bool:
    """Set up GeoapifyGeocode from a config entry."""
    client = GeoapifyClient(hass, entry.data[CONF_API_KEY])
    coordinator = GeoapifyCoordinator(hass, entry, client)
    movement_coordinator = MovementCoordinator(hass, entry)

    await coordinator.async_config_entry_first_refresh()
    await movement_coordinator.async_initialize()

    entry.runtime_data = GeoapifyRuntimeData(
        client=client,
        coordinator=coordinator,
        movement_coordinator=movement_coordinator,
    )
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    entry.async_on_unload(movement_coordinator.async_start())

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: GeoapifyConfigEntry
) -> bool:
    """Unload a GeoapifyGeocode config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
