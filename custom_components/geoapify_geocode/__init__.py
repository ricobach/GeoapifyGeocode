"""The GeoapifyGeocode integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_API_KEY
from .coordinator import GeoapifyClient, GeoapifyCoordinator

PLATFORMS = [Platform.SENSOR]


@dataclass(slots=True)
class GeoapifyRuntimeData:
    """Runtime data for a GeoapifyGeocode config entry."""

    client: GeoapifyClient
    coordinator: GeoapifyCoordinator


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

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = GeoapifyRuntimeData(
        client=client,
        coordinator=coordinator,
    )
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: GeoapifyConfigEntry
) -> bool:
    """Unload a GeoapifyGeocode config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
