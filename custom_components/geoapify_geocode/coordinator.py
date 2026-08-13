from __future__ import annotations

import math
from dataclasses import dataclass

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DEFAULT_MIN_DISTANCE_M


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    # Earth radius in meters
    r = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


@dataclass
class ReverseResult:
    formatted: str
    country: str | None
    timezone: dict | None
    properties: dict
    lat: float
    lon: float


class GeoapifyReverseClient:
    def __init__(self, hass: HomeAssistant, api_key: str) -> None:
        self._hass = hass
        self._api_key = api_key
        self._session = async_get_clientsession(hass)

    async def reverse(self, lat: float, lon: float) -> ReverseResult:
        url = "https://api.geoapify.com/v1/geocode/reverse"
        params = {"lat": str(lat), "lon": str(lon), "apiKey": self._api_key}

        async with self._session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            # Raise for non-2xx with readable body
            text = await resp.text()
            if resp.status < 200 or resp.status >= 300:
                raise RuntimeError(f"Geoapify HTTP {resp.status}: {text}")

            data = await resp.json()

        features = data.get("features") or []
        if not features:
            raise RuntimeError(f"Geoapify response missing features: {data}")

        props = (features[0] or {}).get("properties") or {}

        formatted = props.get("formatted") or "unknown"
        country = props.get("country")
        timezone = props.get("timezone")

        # Geoapify also echoes lat/lon in properties, but we keep the input too
        return ReverseResult(
            formatted=formatted,
            country=country,
            timezone=timezone,
            properties=props,
            lat=lat,
            lon=lon,
        )


class TargetStateCache:
    """Holds last known coords & last good result per target entity."""
    def __init__(self) -> None:
        self.last_latlon: dict[str, tuple[float, float]] = {}
        self.last_result: dict[str, ReverseResult] = {}

    def should_update(self, entity_id: str, lat: float, lon: float, min_distance_m: int) -> bool:
        if min_distance_m is None:
            min_distance_m = DEFAULT_MIN_DISTANCE_M
        if entity_id not in self.last_latlon:
            return True
        prev_lat, prev_lon = self.last_latlon[entity_id]
        return haversine_m(prev_lat, prev_lon, lat, lon) >= float(min_distance_m)

    def set(self, entity_id: str, result: ReverseResult) -> None:
        self.last_latlon[entity_id] = (result.lat, result.lon)
        self.last_result[entity_id] = result
