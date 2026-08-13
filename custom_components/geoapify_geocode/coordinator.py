"""Geoapify API client and data coordinator."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
import logging
import math
import time
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_MAX_AGE,
    CONF_MIN_DISTANCE_M,
    CONF_SCAN_INTERVAL,
    CONF_TARGETS,
    DEFAULT_MAX_AGE,
    DEFAULT_MIN_DISTANCE_M,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)
GEOAPIFY_REVERSE_URL = "https://api.geoapify.com/v1/geocode/reverse"
MAX_CONCURRENT_REQUESTS = 4


class GeoapifyError(Exception):
    """Base class for Geoapify errors."""


class GeoapifyAuthenticationError(GeoapifyError):
    """Raised when the Geoapify API key is rejected."""


class GeoapifyRateLimitError(GeoapifyError):
    """Raised when Geoapify rate limits the client."""

    def __init__(self, retry_after: float) -> None:
        super().__init__("Geoapify API rate limit exceeded")
        self.retry_after = retry_after


class GeoapifyConnectionError(GeoapifyError):
    """Raised when Geoapify cannot be reached."""


class GeoapifyResponseError(GeoapifyError):
    """Raised for an unexpected Geoapify response."""


@dataclass(slots=True)
class GeoapifyResult:
    """Normalized reverse-geocoding result."""

    formatted: str
    country: str | None
    timezone: dict[str, Any] | None
    properties: dict[str, Any]
    lat: float
    lon: float


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance in metres."""
    radius_m = 6_371_000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius_m * c


def _retry_after_seconds(value: str | None) -> float:
    """Parse and clamp Retry-After seconds."""
    try:
        seconds = float(value) if value is not None else 60.0
    except ValueError:
        seconds = 60.0
    return min(max(seconds, 30.0), 3600.0)


class GeoapifyClient:
    """Minimal asynchronous Geoapify API client."""

    def __init__(self, hass: HomeAssistant, api_key: str) -> None:
        self._api_key = api_key
        self._session = async_get_clientsession(hass)

    async def reverse(self, lat: float, lon: float) -> GeoapifyResult:
        """Reverse geocode latitude/longitude."""
        params = {"lat": str(lat), "lon": str(lon), "apiKey": self._api_key}

        try:
            async with self._session.get(
                GEOAPIFY_REVERSE_URL,
                params=params,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as response:
                body = await response.text()

                if response.status in (401, 403):
                    raise GeoapifyAuthenticationError("Geoapify API key was rejected")
                if response.status == 429:
                    raise GeoapifyRateLimitError(
                        _retry_after_seconds(response.headers.get("Retry-After"))
                    )
                if response.status >= 500:
                    raise GeoapifyConnectionError(
                        f"Geoapify service returned HTTP {response.status}"
                    )
                if not 200 <= response.status < 300:
                    raise GeoapifyResponseError(
                        f"Geoapify returned HTTP {response.status}: {body[:200]}"
                    )

                try:
                    data = await response.json()
                except (aiohttp.ContentTypeError, ValueError) as err:
                    raise GeoapifyResponseError(
                        "Geoapify returned invalid JSON"
                    ) from err
        except asyncio.TimeoutError as err:
            raise GeoapifyConnectionError("Timed out connecting to Geoapify") from err
        except aiohttp.ClientError as err:
            raise GeoapifyConnectionError(
                f"Error connecting to Geoapify: {err}"
            ) from err

        features = data.get("features") or []
        if not features:
            raise GeoapifyResponseError("Geoapify response contained no results")

        properties = (features[0] or {}).get("properties") or {}
        formatted = properties.get("formatted")
        if not formatted:
            raise GeoapifyResponseError("Geoapify response contained no formatted address")

        timezone = properties.get("timezone")
        if timezone is not None and not isinstance(timezone, dict):
            timezone = None

        return GeoapifyResult(
            formatted=formatted,
            country=properties.get("country"),
            timezone=timezone,
            properties=properties,
            lat=lat,
            lon=lon,
        )

    async def validate(self, lat: float, lon: float) -> None:
        """Validate credentials and connectivity with a reverse lookup."""
        await self.reverse(lat, lon)


class TargetStateCache:
    """Hold the last successful result and location for each target."""

    def __init__(self) -> None:
        self.last_latlon: dict[str, tuple[float, float]] = {}
        self.last_result: dict[str, GeoapifyResult] = {}
        self.last_updated: dict[str, float] = {}

    def should_update(
        self,
        entity_id: str,
        lat: float,
        lon: float,
        min_distance_m: int,
        max_age: int,
        *,
        now: float | None = None,
    ) -> bool:
        """Return whether movement or result age requires a new API call."""
        if entity_id not in self.last_latlon or entity_id not in self.last_updated:
            return True

        now = time.monotonic() if now is None else now
        if now - self.last_updated[entity_id] >= max_age:
            return True

        previous_lat, previous_lon = self.last_latlon[entity_id]
        return (
            haversine_m(previous_lat, previous_lon, lat, lon)
            >= float(min_distance_m)
        )

    def set(
        self,
        entity_id: str,
        result: GeoapifyResult,
        *,
        now: float | None = None,
    ) -> None:
        """Store a successful result."""
        self.last_latlon[entity_id] = (result.lat, result.lon)
        self.last_result[entity_id] = result
        self.last_updated[entity_id] = time.monotonic() if now is None else now


class GeoapifyCoordinator(DataUpdateCoordinator[dict[str, GeoapifyResult]]):
    """Coordinate reverse-geocoding updates for all configured targets."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: GeoapifyClient,
    ) -> None:
        self.entry = entry
        self.client = client
        self.cache = TargetStateCache()
        self.targets = entry.options.get(CONF_TARGETS, entry.data.get(CONF_TARGETS, []))
        self.min_distance_m = int(
            entry.options.get(CONF_MIN_DISTANCE_M, DEFAULT_MIN_DISTANCE_M)
        )
        self.max_age = int(entry.options.get(CONF_MAX_AGE, DEFAULT_MAX_AGE))
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
        self._rate_limited_until = 0.0

        scan_interval = int(
            entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )

        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )

    async def _async_update_target(
        self, entity_id: str
    ) -> GeoapifyResult | None:
        """Update one target, returning cached data where appropriate."""
        state = self.hass.states.get(entity_id)
        if state is None:
            _LOGGER.debug("Target entity missing: %s", entity_id)
            return self.cache.last_result.get(entity_id)

        lat = state.attributes.get("latitude")
        lon = state.attributes.get("longitude")
        if lat is None or lon is None:
            _LOGGER.debug("Target %s is missing latitude/longitude", entity_id)
            return self.cache.last_result.get(entity_id)

        try:
            lat_f = float(lat)
            lon_f = float(lon)
        except (TypeError, ValueError):
            _LOGGER.debug(
                "Target %s has non-numeric coordinates: lat=%s lon=%s",
                entity_id,
                lat,
                lon,
            )
            return self.cache.last_result.get(entity_id)

        if not self.cache.should_update(
            entity_id,
            lat_f,
            lon_f,
            self.min_distance_m,
            self.max_age,
        ):
            return self.cache.last_result.get(entity_id)

        now = time.monotonic()
        if now < self._rate_limited_until:
            return self.cache.last_result.get(entity_id)

        try:
            async with self._semaphore:
                result = await self.client.reverse(lat_f, lon_f)
        except GeoapifyRateLimitError as err:
            self._rate_limited_until = max(
                self._rate_limited_until, time.monotonic() + err.retry_after
            )
            if entity_id in self.cache.last_result:
                _LOGGER.warning(
                    "Geoapify rate limited requests; using cached result for %s",
                    entity_id,
                )
                return self.cache.last_result[entity_id]
            raise
        except (GeoapifyConnectionError, GeoapifyResponseError) as err:
            if entity_id in self.cache.last_result:
                _LOGGER.warning(
                    "Geoapify update failed for %s; using cached result: %s",
                    entity_id,
                    err,
                )
                return self.cache.last_result[entity_id]
            raise

        self.cache.set(entity_id, result)
        return result

    async def _async_update_data(self) -> dict[str, GeoapifyResult]:
        """Fetch all targets while isolating per-target failures."""
        if not self.targets:
            return {}

        outcomes = await asyncio.gather(
            *(self._async_update_target(entity_id) for entity_id in self.targets),
            return_exceptions=True,
        )

        results: dict[str, GeoapifyResult] = {}
        failures: list[Exception] = []

        for entity_id, outcome in zip(self.targets, outcomes, strict=True):
            if isinstance(outcome, GeoapifyAuthenticationError):
                raise ConfigEntryAuthFailed(
                    "Geoapify rejected the configured API key"
                ) from outcome
            if isinstance(outcome, GeoapifyRateLimitError):
                failures.append(outcome)
                _LOGGER.warning("Geoapify rate limit reached for %s", entity_id)
                continue
            if isinstance(outcome, Exception):
                failures.append(outcome)
                _LOGGER.warning("Geoapify update failed for %s: %s", entity_id, outcome)
                continue
            if outcome is not None:
                results[entity_id] = outcome

        if results:
            return results

        if failures:
            first = failures[0]
            if isinstance(first, GeoapifyRateLimitError):
                raise UpdateFailed(
                    "Geoapify API rate limit exceeded",
                    retry_after=first.retry_after,
                ) from first
            raise UpdateFailed(f"Unable to update Geoapify data: {first}") from first

        return {}
