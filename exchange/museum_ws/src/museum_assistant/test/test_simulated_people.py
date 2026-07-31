import pytest

from museum_assistant.simulated_people import people_from_model_positions


def observe(positions, timestamp, previous=None):
    return people_from_model_positions(
        positions,
        timestamp=timestamp,
        previous_positions=previous or {},
    )


def test_first_observation_has_zero_velocity():
    samples, _ = observe({"visitor_marker": (1.0, 2.0, 0.0)}, 10.0)

    assert (samples[0].vx, samples[0].vy) == (0.0, 0.0)


def test_position_change_produces_finite_difference_velocity():
    _, previous = observe({"visitor_marker": (1.0, 2.0, 0.0)}, 10.0)

    samples, _ = observe(
        {"visitor_marker": (2.0, 1.0, 0.0)},
        12.0,
        previous,
    )

    assert samples[0].vx == pytest.approx(0.5)
    assert samples[0].vy == pytest.approx(-0.5)


def test_stationary_person_has_zero_velocity():
    _, previous = observe({"guide_marker": (2.2, -0.35, 0.0)}, 10.0)

    samples, _ = observe(
        {"guide_marker": (2.2, -0.35, 0.0)},
        11.0,
        previous,
    )

    assert (samples[0].vx, samples[0].vy) == (0.0, 0.0)


@pytest.mark.parametrize("timestamp", [10.0, 9.0])
def test_non_positive_dt_is_safe(timestamp):
    _, previous = observe({"staff_marker": (8.2, 0.45, 0.0)}, 10.0)

    samples, _ = observe(
        {"staff_marker": (8.7, 0.95, 0.0)},
        timestamp,
        previous,
    )

    assert (samples[0].vx, samples[0].vy) == (0.0, 0.0)


def test_models_map_to_stable_public_ids():
    samples, _ = observe(
        {
            "visitor_marker": (0.0, 0.0, 0.0),
            "guide_marker": (1.0, 0.0, 0.0),
            "staff_marker": (2.0, 0.0, 0.0),
        },
        1.0,
    )

    assert [sample.identifier for sample in samples] == [
        "visitor_1",
        "guide_1",
        "staff_1",
    ]
    assert "marker" not in str(samples)


def test_robot_model_is_never_a_pedestrian():
    samples, _ = observe({"tiago": (0.0, 0.0, 0.0)}, 1.0)

    assert samples == []
