from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

PLATFORMS = ["sensor"]


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when options change so entities are recreated without HA restart."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up GeoapifyGeocode from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Listen for option changes (targets, scan_interval, min_distance_m)
    remove_listener = entry.add_update_listener(_async_reload_entry)
    hass.data[DOMAIN][entry.entry_id] = {"remove_listener": remove_listener}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Remove listener
    data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if data and "remove_listener" in data:
        data["remove_listener"]()

    return unload_ok
