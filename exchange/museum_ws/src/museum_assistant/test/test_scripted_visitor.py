import math

import pytest

from museum_assistant.scripted_visitor import (
    LagRecoverScenario,
    ScriptedVisitorPhase,
    limited_follow_step,
)


def test_motion_toward_robot_is_limited_by_speed():
    result = limited_follow_step(
        (0.0, 0.0),
        (5.0, 0.0),
        follow_distance=1.5,
        speed=0.5,
        dt=0.2,
    )

    assert math.dist((0.0, 0.0), result) == pytest.approx(0.1)


def test_visitor_does_not_move_inside_follow_distance():
    assert limited_follow_step(
        (0.0, 0.0),
        (1.0, 0.0),
        follow_distance=1.5,
        speed=0.5,
        dt=0.2,
    ) == (0.0, 0.0)


def test_lag_phase_stops_visitor():
    scenario = LagRecoverScenario(lag_after_seconds=5.0)
    scenario.handle_escort_state("escorting", now=10.0)

    result = scenario.step((0.0, 0.0), (5.0, 0.0), now=15.0, dt=0.2)

    assert result == (0.0, 0.0)
    assert scenario.phase is ScriptedVisitorPhase.LAGGING


def test_waiting_uses_catchup_then_escorting_resumes_following():
    scenario = LagRecoverScenario(catchup_speed=0.8)
    scenario.handle_escort_state("escorting", now=0.0)
    scenario.step((0.0, 0.0), (5.0, 0.0), now=5.0, dt=0.2)
    scenario.handle_escort_state("waiting", now=8.0)

    result = scenario.step((0.0, 0.0), (5.0, 0.0), now=8.2, dt=0.2)

    assert result == pytest.approx((0.16, 0.0))
    assert scenario.phase is ScriptedVisitorPhase.CATCHING_UP

    scenario.handle_escort_state("escorting", now=9.0)
    assert scenario.phase is ScriptedVisitorPhase.FOLLOWING
    assert scenario.step(
        result,
        (5.0, 0.0),
        now=20.0,
        dt=0.2,
    ) != result


@pytest.mark.parametrize("terminal_state", ["arrived", "lost"])
def test_terminal_escort_state_stops_motion(terminal_state):
    scenario = LagRecoverScenario()
    scenario.handle_escort_state("escorting", now=0.0)
    scenario.handle_escort_state(terminal_state, now=1.0)

    assert scenario.step(
        (0.0, 0.0),
        (5.0, 0.0),
        now=1.2,
        dt=0.2,
    ) == (0.0, 0.0)
    assert scenario.phase is ScriptedVisitorPhase.DONE
