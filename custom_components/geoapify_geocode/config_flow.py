"""Config flow for GeoapifyGeocode."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, override

import voluptuous as vol

from homeassistant.config_entries import (
    SOURCE_USER,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    FlowType,
    SubentryFlowContext,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_API_KEY,
    CONF_MAX_AGE,
    CONF_MIN_DISTANCE_M,
    CONF_SCAN_INTERVAL,
    CONF_SOURCE_ENTITY,
    DEFAULT_MAX_AGE,
    DEFAULT_MIN_DISTANCE_M,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SUBENTRY_TYPE_TRACKED_ENTITY,
)
from .coordinator import (
    GeoapifyAuthenticationError,
    GeoapifyClient,
    GeoapifyConnectionError,
    GeoapifyRateLimitError,
    GeoapifyResponseError,
)


class GeoapifyGeocodeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for GeoapifyGeocode."""

    VERSION = 2

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

    @classmethod
    @callback
    @override
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return supported config subentry types."""
        return {SUBENTRY_TYPE_TRACKED_ENTITY: TrackedEntitySubentryFlow}

    async def async_on_create_entry(
        self, result: ConfigFlowResult
    ) -> ConfigFlowResult:
        """Offer adding the first tracked entity after configuring the API key."""
        subentry_result = await self.hass.config_entries.subentries.async_init(
            (result["result"].entry_id, SUBENTRY_TYPE_TRACKED_ENTITY),
            context=SubentryFlowContext(source=SOURCE_USER),
        )
        result["next_flow"] = (
            FlowType.CONFIG_SUBENTRIES_FLOW,
            subentry_result["flow_id"],
        )
        return result

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure the shared Geoapify API key."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        errors: dict[str, str] = {}
        if user_input is not None:
            error = await self._async_validate_api_key(user_input[CONF_API_KEY])
            if error is None:
                return self.async_create_entry(
                    title="GeoapifyGeocode",
                    data={CONF_API_KEY: user_input[CONF_API_KEY]},
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): str}),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start reauthentication after an API-key failure."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
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
    ) -> ConfigFlowResult:
        """Allow proactive replacement of the shared Geoapify API key."""
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


class TrackedEntitySubentryFlow(ConfigSubentryFlow):
    """Add and reconfigure one tracked person or device tracker."""

    @staticmethod
    def _source_selector() -> selector.EntitySelector:
        return selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain=["person", "device_tracker"],
                multiple=False,
            )
        )

    def _title_for_source(self, source_entity: str) -> str:
        """Return a friendly device/subentry title."""
        state = self.hass.states.get(source_entity)
        if state is None:
            return source_entity
        return state.attributes.get("friendly_name", source_entity)

    def _schema(
        self,
        *,
        source_entity: str | None = None,
        values: Mapping[str, Any] | None = None,
        include_source: bool = True,
    ) -> vol.Schema:
        """Build the tracked-entity settings schema."""
        values = values or {}
        fields: dict[vol.Marker, Any] = {}
        if include_source:
            marker = vol.Required(CONF_SOURCE_ENTITY)
            if source_entity is not None:
                marker = vol.Required(CONF_SOURCE_ENTITY, default=source_entity)
            fields[marker] = self._source_selector()

        fields.update(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=int(values.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
                ): vol.All(int, vol.Range(min=30, max=3600)),
                vol.Optional(
                    CONF_MIN_DISTANCE_M,
                    default=int(values.get(CONF_MIN_DISTANCE_M, DEFAULT_MIN_DISTANCE_M)),
                ): vol.All(int, vol.Range(min=0, max=50000)),
                vol.Optional(
                    CONF_MAX_AGE,
                    default=int(values.get(CONF_MAX_AGE, DEFAULT_MAX_AGE)),
                ): vol.All(int, vol.Range(min=60, max=86400)),
            }
        )
        return vol.Schema(fields)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Add one tracked entity."""
        if user_input is not None:
            source_entity = user_input[CONF_SOURCE_ENTITY]
            entry = self._get_entry()
            if any(
                subentry.unique_id == source_entity
                for subentry in entry.subentries.values()
            ):
                return self.async_abort(reason="already_configured")

            return self.async_create_entry(
                title=self._title_for_source(source_entity),
                data=user_input,
                unique_id=source_entity,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=self._schema(),
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Reconfigure one tracked entity's geocode settings."""
        entry = self._get_entry()
        subentry = self._get_reconfigure_subentry()
        source_entity = subentry.data[CONF_SOURCE_ENTITY]

        if user_input is not None:
            updated_data = {CONF_SOURCE_ENTITY: source_entity, **user_input}
            return self.async_update_and_abort(
                entry,
                subentry,
                data=updated_data,
                title=self._title_for_source(source_entity),
            )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self._schema(values=subentry.data, include_source=False),
            description_placeholders={"source": self._title_for_source(source_entity)},
        )
