from museum_assistant.contracts import SessionLifecycle
from museum_assistant.visitor_session import VisitorSession


def test_first_observation_creates_active_session():
    visitor = VisitorSession("visitor_marker")

    session = visitor.observe(["ground_plane", "visitor_marker"])

    assert session.session_id == "session_1"
    assert session.track_id == "visitor_1"
    assert session.state is SessionLifecycle.ACTIVE


def test_repeated_observation_reuses_session():
    visitor = VisitorSession("visitor_marker")

    first = visitor.observe(["visitor_marker"])
    second = visitor.observe(["visitor_marker"])

    assert second is first
    assert second.session_id == "session_1"


def test_public_session_data_does_not_expose_gazebo_model_name():
    visitor = VisitorSession("visitor_marker")

    public_data = visitor.observe(["visitor_marker"]).to_dict()

    assert public_data == {
        "session_id": "session_1",
        "track_id": "visitor_1",
        "state": "active",
    }
    assert "visitor_marker" not in str(public_data)


def test_present_observation_has_only_public_identity_and_distance():
    visitor = VisitorSession("visitor_marker")

    public_data = visitor.observation(
        present=True,
        distance_to_robot=1.8,
    )

    assert public_data == {
        "session_id": "session_1",
        "track_id": "visitor_1",
        "present": True,
        "distance_to_robot": 1.8,
    }
    assert "visitor_marker" not in str(public_data)


def test_absent_observation_omits_distance():
    visitor = VisitorSession("visitor_marker")

    assert visitor.observation(present=False) == {
        "session_id": "session_1",
        "track_id": "visitor_1",
        "present": False,
    }


def test_generic_session_can_activate_without_simulator_presence():
    visitor = VisitorSession("visitor_marker")
    session = visitor.activate()
    assert session.session_id == "session_1"
    assert session.track_id == "visitor_1"
    assert "visitor_marker" not in str(session.to_dict())
