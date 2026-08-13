"""Config flow for GeoapifyGeocode."""

from __future__ import annotations

from typing import Any, Mapping

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_API_KEY,
    CONF_MAX_AGE,
    CONF_MIN_DISTANCE_M,
    CONF_SCAN_INTERVAL,
    CONF_TARGETS,
    DEFAULT_MAX_AGE,
    DEFAULT_MIN_DISTANCE_M,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .coordinator import (
    GeoapifyAuthenticationError,
    GeoapifyClient,
    GeoapifyConnectionError,
    GeoapifyRateLimitError,
    GeoapifyResponseError,
)


class GeoapifyGeocodeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for GeoapifyGeocode."""

    VERSION = 1
    MINOR_VERSION = 2

    async def _async_validate_api_key(self, api_key: str) -> str | None:
        """Return a config-flow error key, or None when validation succeeds."""
        client = GeoapifyClient(self.hass, api_key)
        try:
            await client.validate(self.hass.config.latitude, self.hass.config.longitude)
        except GeoapifyAuthenticationError:
            return "invalid_auth"
        except GeoapifyRateLimitError:
            return "rate_limited"
        except GeoapifyConnectionError:
            return "cannot_connect"
        except GeoapifyResponseError:
            return "unknown"
        return None

    @staticmethod
    def _target_selector() -> selector.EntitySelector:
        return selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain=["person", "device_tracker"],
                multiple=True,
            )
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial setup step."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        errors: dict[str, str] = {}
        if user_input is not None:
            error = await self._async_validate_api_key(user_input[CONF_API_KEY])
            if error is None:
                return self.async_create_entry(
                    title="GeoapifyGeocode",
                    data={CONF_API_KEY: user_input[CONF_API_KEY]},
                    options={
                        CONF_TARGETS: user_input[CONF_TARGETS],
                        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
                        CONF_MIN_DISTANCE_M: DEFAULT_MIN_DISTANCE_M,
                        CONF_MAX_AGE: DEFAULT_MAX_AGE,
                    },
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_KEY): str,
                    vol.Required(CONF_TARGETS): self._target_selector(),
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> FlowResult:
        """Start reauthentication after an API-key failure."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Validate and replace an invalid API key."""
        errors: dict[str, str] = {}
        if user_input is not None:
            error = await self._async_validate_api_key(user_input[CONF_API_KEY])
            if error is None:
                entry = self._get_reauth_entry()
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={CONF_API_KEY: user_input[CONF_API_KEY]},
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): str}),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Allow proactive replacement of the Geoapify API key."""
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()

        if user_input is not None:
            error = await self._async_validate_api_key(user_input[CONF_API_KEY])
            if error is None:
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={CONF_API_KEY: user_input[CONF_API_KEY]},
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_API_KEY,
                        default=entry.data.get(CONF_API_KEY, ""),
                    ): str
                }
            ),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> GeoapifyGeocodeOptionsFlow:
        """Return the options flow."""
        return GeoapifyGeocodeOptionsFlow(config_entry)


class GeoapifyGeocodeOptionsFlow(config_entries.OptionsFlow):
    """Handle GeoapifyGeocode options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage optional behavior settings."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_targets = self._config_entry.options.get(
            CONF_TARGETS,
            self._config_entry.data.get(CONF_TARGETS, []),
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=int(
                            self._config_entry.options.get(
                                CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                            )
                        ),
                    ): vol.All(int, vol.Range(min=30, max=3600)),
                    vol.Optional(
                        CONF_MIN_DISTANCE_M,
                        default=int(
                            self._config_entry.options.get(
                                CONF_MIN_DISTANCE_M, DEFAULT_MIN_DISTANCE_M
                            )
                        ),
                    ): vol.All(int, vol.Range(min=0, max=50000)),
                    vol.Optional(
                        CONF_MAX_AGE,
                        default=int(
                            self._config_entry.options.get(
                                CONF_MAX_AGE, DEFAULT_MAX_AGE
                            )
                        ),
                    ): vol.All(int, vol.Range(min=60, max=86400)),
                    vol.Optional(
                        CONF_TARGETS,
                        default=current_targets,
                    ): GeoapifyGeocodeConfigFlow._target_selector(),
                }
            ),
        )
