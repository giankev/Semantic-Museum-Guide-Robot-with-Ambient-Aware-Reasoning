import math

from museum_assistant.engagement import (
    EngagementModel,
    EngagementState,
    frontal_lidar_candidate,
)


def update(model, now, visual=True, central=True, distance=1.5):
    return model.update(
        now=now,
        visual_person=visual,
        central=central,
        distance_m=distance,
    )


def test_t1_no_person():
    assert update(EngagementModel(), 0, False, False, None).state is EngagementState.NO_PERSON


def test_t2_visual_only_never_engages():
    model = EngagementModel()
    assert all(update(model, time, distance=None).state is not EngagementState.ENGAGED
               for time in (0, 1, 3, 10))


def test_t3_lidar_only_never_engages():
    model = EngagementModel()
    assert all(update(model, time, visual=False).state is EngagementState.NO_PERSON
               for time in (0, 1, 3))


def test_t4_brief_pass_by():
    model = EngagementModel()
    assert update(model, 0).state is EngagementState.PASSING
    assert update(model, 0.5, False, False, None).state is EngagementState.NO_PERSON


def test_t5_stationary_near_person_engages_after_potential():
    model = EngagementModel()
    update(model, 0)
    assert update(model, 1.1).state is EngagementState.POTENTIAL_INTERACTION
    assert update(model, 2.6).state is EngagementState.ENGAGED


def test_t6_visible_but_too_far_never_engages():
    model = EngagementModel()
    assert all(update(model, time, distance=2.1).state is not EngagementState.ENGAGED
               for time in (0, 2, 5))


def test_t7_fast_radial_motion_never_engages():
    model = EngagementModel()
    update(model, 0, distance=1.9)
    update(model, 1.1, distance=1.5)
    assert update(model, 2.6, distance=0.9).state is not EngagementState.ENGAGED


def test_t8_engaged_then_disappears():
    model = EngagementModel()
    update(model, 0)
    update(model, 1.1)
    assert update(model, 2.6).state is EngagementState.ENGAGED
    assert update(model, 2.7, False, False, None).state is EngagementState.DISENGAGING
    assert update(model, 4.3, False, False, None).state is EngagementState.NO_PERSON


def test_t9_engaged_state_tolerates_sensor_jitter():
    model = EngagementModel()
    for time in (0, 1.1, 2.6):
        update(model, time)
    assert update(model, 2.7, False, False, None).state is EngagementState.DISENGAGING
    assert update(model, 2.9).state is EngagementState.ENGAGED
    assert update(model, 3.0, False, False, None).state is EngagementState.DISENGAGING
    assert update(model, 3.2).state is EngagementState.ENGAGED


def test_t10_invalid_lidar_is_safe():
    ranges = [math.nan, math.inf, -1.0, 0.2]
    assert frontal_lidar_candidate(ranges, -0.2, 0.1, 0.05, 25.0) == (None, None)


def test_lidar_uses_closest_valid_point_in_frontal_cone():
    distance, bearing = frontal_lidar_candidate(
        [4.0, 1.2, 0.8, math.inf], -0.9, 0.3, 0.05, 25.0
    )
    assert distance == 0.8
    assert abs(bearing + 0.3) < 1e-9


def test_t11_deterministic_repeatability():
    def run():
        model = EngagementModel()
        return [update(model, time).state for time in (0, 1.1, 2.6, 3.0)]

    assert run() == run()
