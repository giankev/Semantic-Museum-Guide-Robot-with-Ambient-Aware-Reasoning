from museum_assistant.escort import EscortState, EscortSupervisor


def make_escort():
    return EscortSupervisor(
        resume_distance=2.0,
        wait_distance=3.0,
        lost_distance=8.0,
        arrival_distance=2.5,
        wait_delay=3.0,
        absence_timeout=3.0,
    )


def observe(escort, distance, now):
    return escort.observe(
        present=True,
        distance_to_robot=distance,
        now=now,
    )


def test_task_starts_escorting():
    escort = make_escort()

    assert escort.start() is EscortState.ESCORTING


def test_brief_lag_does_not_wait_before_delay():
    escort = make_escort()
    escort.start()

    observe(escort, 3.5, 10.0)

    assert observe(escort, 3.5, 12.9) is EscortState.ESCORTING


def test_sustained_lag_transitions_to_waiting():
    escort = make_escort()
    escort.start()

    observe(escort, 3.5, 10.0)

    assert observe(escort, 3.5, 13.0) is EscortState.WAITING


def test_waiting_resumes_below_resume_distance():
    escort = make_escort()
    escort.start()
    observe(escort, 3.5, 10.0)
    observe(escort, 3.5, 13.0)

    assert observe(escort, 2.0, 14.0) is EscortState.ESCORTING


def test_escorting_becomes_lost_when_visitor_is_too_far():
    escort = make_escort()
    escort.start()

    assert observe(escort, 8.0, 1.0) is EscortState.LOST


def test_waiting_becomes_lost_after_visitor_absence_timeout():
    escort = make_escort()
    escort.start()
    observe(escort, 3.5, 10.0)
    observe(escort, 3.5, 13.0)

    escort.observe(present=False, distance_to_robot=None, now=14.0)
    state = escort.observe(
        present=False,
        distance_to_robot=None,
        now=17.0,
    )

    assert state is EscortState.LOST


def test_navigation_success_with_far_visitor_is_not_arrival():
    escort = make_escort()
    observe(escort, 3.0, 1.0)
    escort.start()

    assert escort.navigation_succeeded() is EscortState.WAITING


def test_navigation_success_with_near_visitor_is_arrival():
    escort = make_escort()
    observe(escort, 1.5, 1.0)
    escort.start()

    assert escort.navigation_succeeded() is EscortState.ARRIVED


def test_visitor_can_arrive_after_navigation_succeeds():
    escort = make_escort()
    observe(escort, 3.0, 1.0)
    escort.start()
    escort.navigation_succeeded()

    assert observe(escort, 2.5, 2.0) is EscortState.ARRIVED


def test_hysteresis_prevents_waiting_toggle_near_wait_distance():
    escort = make_escort()
    escort.start()
    observe(escort, 3.5, 10.0)
    observe(escort, 3.5, 13.0)

    assert observe(escort, 2.5, 14.0) is EscortState.WAITING
    assert observe(escort, 2.0, 15.0) is EscortState.ESCORTING
    assert observe(escort, 2.5, 16.0) is EscortState.ESCORTING
