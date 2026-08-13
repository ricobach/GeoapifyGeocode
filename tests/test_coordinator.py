"""Unit tests for GeoapifyGeocode coordinator helpers."""

from custom_components.geoapify_geocode.coordinator import (
    GeoapifyResult,
    TargetStateCache,
    haversine_m,
)


def _result(lat: float, lon: float) -> GeoapifyResult:
    return GeoapifyResult(
        formatted="Test address",
        country="Denmark",
        timezone={"name": "Europe/Copenhagen"},
        properties={},
        lat=lat,
        lon=lon,
    )


def test_haversine_zero_distance() -> None:
    assert haversine_m(55.6761, 12.5683, 55.6761, 12.5683) == 0


def test_cache_refreshes_after_movement() -> None:
    cache = TargetStateCache()
    cache.set("person.test", _result(55.6761, 12.5683), now=100)

    assert not cache.should_update(
        "person.test", 55.6761, 12.5683, 100, 1800, now=200
    )
    assert cache.should_update(
        "person.test", 55.6861, 12.5683, 100, 1800, now=200
    )


def test_cache_refreshes_after_max_age() -> None:
    cache = TargetStateCache()
    cache.set("person.test", _result(55.6761, 12.5683), now=100)

    assert cache.should_update(
        "person.test", 55.6761, 12.5683, 100, 1800, now=1900
    )
