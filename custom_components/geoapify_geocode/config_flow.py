from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_API_KEY,
    CONF_TARGETS,
    DEFAULT_MIN_DISTANCE_M,
    DEFAULT_SCAN_INTERVAL,
)


class GeoapifyReverseConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        # Single instance so you only enter API key once
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            return self.async_create_entry(
                title="GeoapifyGeocode",
                data={
                    CONF_API_KEY: user_input[CONF_API_KEY],
                    CONF_TARGETS: user_input[CONF_TARGETS],
                },
                options={
                    "scan_interval": DEFAULT_SCAN_INTERVAL,
                    "min_distance_m": DEFAULT_MIN_DISTANCE_M,
                    # also store targets in options so reconfigure works cleanly
                    CONF_TARGETS: user_input[CONF_TARGETS],
                },
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY): str,
                # Keep selector broad for compatibility; you can pick person/device_tracker manually
                vol.Required(CONF_TARGETS): selector.EntitySelector(
                    selector.EntitySelectorConfig(multiple=True)
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return GeoapifyReverseOptionsFlowHandler(config_entry)


class GeoapifyReverseOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        # IMPORTANT: don't assign to self.config_entry (read-only in newer HA)
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_targets = self._config_entry.options.get(
            CONF_TARGETS,
            self._config_entry.data.get(CONF_TARGETS, []),
        )

        schema = vol.Schema(
            {
                vol.Optional(
                    "scan_interval",
                    default=int(self._config_entry.options.get("scan_interval", DEFAULT_SCAN_INTERVAL)),
                ): vol.All(int, vol.Range(min=30, max=3600)),
                vol.Optional(
                    "min_distance_m",
                    default=int(self._config_entry.options.get("min_distance_m", DEFAULT_MIN_DISTANCE_M)),
                ): vol.All(int, vol.Range(min=0, max=50000)),
                vol.Optional(
                    CONF_TARGETS,
                    default=current_targets,
                ): selector.EntitySelector(selector.EntitySelectorConfig(multiple=True)),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
