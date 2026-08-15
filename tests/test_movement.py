"""Unit tests for GPS movement calculation."""

from datetime import UTC, datetime, timedelta

from custom_components.geoapify_geocode.movement import GPSHistory, GPSSample

BASE = datetime(2026, 8, 15, 10, 0, tzinfo=UTC)


def _history(**kwargs) -> GPSHistory:
    return GPSHistory(
        history_window=kwargs.get("history_window", 600),
        comparison_age=kwargs.get("comparison_age", 300),
        min_reference_age=kwargs.get("min_reference_age", 60),
        min_distance_m=kwargs.get("min_distance_m", 20),
        default_accuracy=kwargs.get("default_accuracy", 25),
        stationary_timeout=kwargs.get("stationary_timeout", 120),
    )


def _sample(
    seconds: int,
    lat: float,
    lon: float,
    accuracy: float | None = 5,
) -> GPSSample:
    return GPSSample(BASE + timedelta(seconds=seconds), lat, lon, accuracy)


def test_insufficient_history_is_unknown() -> None:
    gps = _history()
    gps.add_sample(_sample(0, 55.6761, 12.5683))

    result = gps.evaluate()

    assert result.is_moving is None
    assert result.reference is None


def test_uses_point_closest_to_target_age() -> None:
    gps = _history()
    gps.add_sample(_sample(0, 55.6761, 12.5683))
    gps.add_sample(_sample(170, 55.6761, 12.5683))
    gps.add_sample(_sample(305, 55.6761, 12.5683))
    gps.add_sample(_sample(600, 55.6761, 12.5683))

    result = gps.evaluate()

    assert result.reference is not None
    assert result.reference.timestamp == BASE + timedelta(seconds=305)
    assert result.reference_age == 295


def test_accuracy_suppresses_gps_drift() -> None:
    gps = _history()
    gps.add_sample(_sample(0, 55.6761, 12.5683, 25))
    gps.add_sample(_sample(300, 55.67635, 12.5683, 25))

    result = gps.evaluate()

    assert result.displacement_m is not None
    assert result.effective_threshold_m == 50
    assert result.is_moving is False


def test_meaningful_displacement_is_moving() -> None:
    gps = _history()
    gps.add_sample(_sample(0, 55.6761, 12.5683, 5))
    gps.add_sample(_sample(300, 55.6771, 12.5683, 5))

    result = gps.evaluate()

    assert result.displacement_m is not None
    assert result.effective_threshold_m is not None
    assert result.displacement_m > result.effective_threshold_m
    assert result.is_moving is True
    assert result.last_meaningful_movement == BASE + timedelta(seconds=300)


def test_missing_accuracy_uses_default() -> None:
    gps = _history(default_accuracy=30)
    gps.add_sample(_sample(0, 55.6761, 12.5683, None))
    gps.add_sample(_sample(300, 55.6761, 12.5683, None))

    result = gps.evaluate()

    assert result.effective_threshold_m == 60
    assert result.is_moving is False


def test_stationary_timeout_prevents_immediate_flap() -> None:
    gps = _history(stationary_timeout=120)
    gps.add_sample(_sample(0, 55.6761, 12.5683, 5))
    gps.add_sample(_sample(300, 55.6771, 12.5683, 5))
    assert gps.evaluate().is_moving is True

    gps.add_sample(_sample(360, 55.6771, 12.5683, 5))
    result = gps.evaluate()

    assert result.is_moving is True


def test_old_samples_are_pruned() -> None:
    gps = _history(history_window=600)
    gps.add_sample(_sample(0, 55.6761, 12.5683))
    gps.add_sample(_sample(700, 55.6761, 12.5683))

    assert len(gps.samples) == 1


def test_stale_history_becomes_unknown() -> None:
    gps = _history(history_window=600)
    gps.add_sample(_sample(0, 55.6761, 12.5683))
    gps.add_sample(_sample(300, 55.6771, 12.5683))

    result = gps.evaluate(now=BASE + timedelta(seconds=1000))

    assert result.is_moving is None
    assert result.sample_count == 0
