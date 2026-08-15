"""Unit tests for GPS movement detection."""

from custom_components.geoapify_geocode.movement import GPSSample, MovementHistory


def _sample(
    timestamp: float,
    lat: float,
    lon: float,
    accuracy: float | None = 5,
) -> GPSSample:
    return GPSSample(timestamp, lat, lon, accuracy)


def test_prefers_reference_near_five_minutes_with_irregular_updates() -> None:
    history = MovementHistory(
        history_window=600,
        comparison_age=300,
        min_reference_age=60,
        min_distance_m=20,
        default_accuracy_m=25,
        stationary_timeout=0,
    )
    history.add(_sample(100, 55.6761, 12.5683))
    history.add(_sample(240, 55.6761, 12.5683))
    history.add(_sample(415, 55.6761, 12.5683))
    history.add(_sample(700, 55.6861, 12.5683))

    result = history.evaluate(now=700)

    assert result.reference is not None
    assert result.reference.timestamp == 415
    assert result.reference_age == 285
    assert result.is_moving is True


def test_gps_accuracy_suppresses_normal_drift() -> None:
    history = MovementHistory(
        history_window=600,
        comparison_age=300,
        min_reference_age=60,
        min_distance_m=10,
        default_accuracy_m=25,
        stationary_timeout=0,
    )
    history.add(_sample(100, 55.6761, 12.5683, 30))
    history.add(_sample(400, 55.6763, 12.5683, 30))

    result = history.evaluate(now=400)

    assert result.displacement_m is not None
    assert result.effective_threshold_m == 60
    assert result.displacement_m < result.effective_threshold_m
    assert result.is_moving is False


def test_missing_accuracy_uses_configured_fallback() -> None:
    history = MovementHistory(
        history_window=600,
        comparison_age=300,
        min_reference_age=60,
        min_distance_m=10,
        default_accuracy_m=25,
        stationary_timeout=0,
    )
    history.add(_sample(100, 55.6761, 12.5683, None))
    history.add(_sample(400, 55.6762, 12.5683, None))

    result = history.evaluate(now=400)

    assert result.effective_threshold_m == 50
    assert result.is_moving is False


def test_insufficient_history_is_unknown() -> None:
    history = MovementHistory(min_reference_age=60)
    history.add(_sample(100, 55.6761, 12.5683))
    history.add(_sample(130, 55.6861, 12.5683))

    result = history.evaluate(now=130)

    assert result.reference is None
    assert result.is_moving is None


def test_stationary_timeout_holds_moving_state_briefly() -> None:
    history = MovementHistory(
        history_window=600,
        comparison_age=60,
        min_reference_age=60,
        min_distance_m=20,
        default_accuracy_m=5,
        stationary_timeout=120,
    )
    history.add(_sample(100, 55.6761, 12.5683))
    history.add(_sample(160, 55.6861, 12.5683))
    assert history.evaluate(now=160).is_moving is True

    history.samples.clear()
    history.add(_sample(170, 55.6861, 12.5683))
    history.add(_sample(230, 55.6861, 12.5683))
    assert history.evaluate(now=230).is_moving is True
    assert history.evaluate(now=300).is_moving is False


def test_old_samples_are_pruned() -> None:
    history = MovementHistory(history_window=600, min_reference_age=60)
    history.add(_sample(0, 55.6761, 12.5683))
    history.add(_sample(500, 55.6761, 12.5683))
    history.add(_sample(700, 55.6761, 12.5683))

    result = history.evaluate(now=700)

    assert result.sample_count == 2
