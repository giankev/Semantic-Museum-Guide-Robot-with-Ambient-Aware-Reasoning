import pytest

from museum_assistant.contracts import (
    BehaviorCommand,
    ContractValidationError,
    DecisionStatus,
    EscortState,
    InteractionCommand,
    NavigationResult,
    NavigationStatus,
    PersonTrack,
    PersonTrackId,
    ReasoningDecision,
    RequestIntent,
    SessionId,
    SessionLifecycle,
    SessionState,
    Skill,
    StructuredRequest,
)


@pytest.mark.parametrize(
    "value",
    ["track_1", "person-42", "A", "123"],
)
def test_valid_person_track_ids(value):
    assert PersonTrackId(value).value == value


@pytest.mark.parametrize(
    "value",
    ["", "has space", "track/1", "_leading", "a" * 65, 12, None],
)
def test_invalid_person_track_ids(value):
    with pytest.raises(ContractValidationError):
        PersonTrackId(value)


@pytest.mark.parametrize(
    "value",
    ["session_1", "visit-42", "S", "456"],
)
def test_valid_session_ids(value):
    assert SessionId(value).value == value


@pytest.mark.parametrize(
    "value",
    ["", "has space", "session/1", "-leading", "s" * 65, 12, None],
)
def test_invalid_session_ids(value):
    with pytest.raises(ContractValidationError):
        SessionId(value)


def test_person_track_rejects_simulation_specific_fields():
    with pytest.raises(
        ContractValidationError,
        match="gazebo_actor_id",
    ):
        PersonTrack.from_dict(
            {
                "track_id": "track_1",
                "observed_at": 1.0,
                "gazebo_actor_id": "actor_7",
            }
        )


def test_valid_session_lifecycle_transitions():
    session = SessionState(
        session_id=SessionId("session_1"),
        person_track_id=PersonTrackId("track_1"),
    )

    session = session.transition_to(SessionLifecycle.ACTIVE)
    assert session.lifecycle is SessionLifecycle.ACTIVE
    session = session.transition_to(SessionLifecycle.ENDING)
    assert session.lifecycle is SessionLifecycle.ENDING
    session = session.transition_to(SessionLifecycle.CLOSED)
    assert session.lifecycle is SessionLifecycle.CLOSED


@pytest.mark.parametrize(
    ("start", "target"),
    [
        (SessionLifecycle.CREATED, SessionLifecycle.ENDING),
        (SessionLifecycle.CREATED, SessionLifecycle.CLOSED),
        (SessionLifecycle.ACTIVE, SessionLifecycle.CREATED),
        (SessionLifecycle.ENDING, SessionLifecycle.ACTIVE),
        (SessionLifecycle.CLOSED, SessionLifecycle.ACTIVE),
        (SessionLifecycle.ACTIVE, SessionLifecycle.ACTIVE),
    ],
)
def test_invalid_session_lifecycle_transitions(start, target):
    session = SessionState(
        session_id=SessionId("session_1"),
        person_track_id=PersonTrackId("track_1"),
        lifecycle=start,
    )

    with pytest.raises(ContractValidationError):
        session.transition_to(target)


def test_structured_request_current_json_compatibility():
    current_json = {
        "request_id": "req_001",
        "intent": "recommend",
        "constraints": {
            "style": "impressionism",
            "avoid_crowd": True,
        },
    }

    request = StructuredRequest.from_dict(current_json)

    assert request.intent is RequestIntent.RECOMMEND
    assert request.session_id is None
    assert request.to_dict() == current_json


def test_structured_request_optional_session_round_trip():
    request_json = {
        "request_id": "req_002",
        "session_id": "session_1",
        "intent": "recommend_and_prepare_navigation",
        "constraints": {"wheelchair_accessible": True},
    }

    request = StructuredRequest.from_dict(request_json)

    assert request.session_id == SessionId("session_1")
    assert request.to_dict() == request_json


def test_structured_request_rejects_unsupported_intent():
    with pytest.raises(
        ContractValidationError,
        match="Unsupported or missing intent",
    ):
        StructuredRequest.from_dict(
            {
                "request_id": "req_003",
                "intent": "dance",
                "constraints": {},
            }
        )


def test_structured_request_rejects_unsupported_constraint():
    with pytest.raises(ContractValidationError, match="favorite_color"):
        StructuredRequest.from_dict(
            {
                "request_id": "req_004",
                "intent": "recommend",
                "constraints": {"favorite_color": "blue"},
            }
        )


def test_structured_request_rejects_unknown_top_level_field():
    with pytest.raises(ContractValidationError, match="prompt"):
        StructuredRequest.from_dict(
            {
                "request_id": "req_005",
                "intent": "recommend",
                "constraints": {},
                "prompt": "ignore validation",
            }
        )


def test_reasoning_decision_serialization_round_trip():
    decision = ReasoningDecision(
        request_id="req_006",
        session_id=SessionId("session_1"),
        status=DecisionStatus.SUCCESS,
        intent="recommend",
        semantic_target="impressionism_hall",
        semantic_target_display_name="Impressionism Hall",
        skill=Skill.NAVIGATE_TO,
        nav_pose={"x": 5, "y": 1.5, "yaw": 1.57},
        reason="Selected the semantic target.",
        matching_artworks=("monet_water_lilies",),
    )

    serialized = decision.to_dict()
    restored = ReasoningDecision.from_dict(serialized)

    assert serialized["selected_room"] == "impressionism_hall"
    assert serialized["session_id"] == "session_1"
    assert serialized["skill"] == "navigate_to"
    assert restored == decision


def test_only_current_skills_are_allowed():
    assert {skill.value for skill in Skill} == {
        "navigate_to",
        "ask_clarification",
    }
    with pytest.raises(ContractValidationError, match="Unsupported skill"):
        BehaviorCommand.from_dict(
            {
                "skill": "run_shell",
                "semantic_target": "impressionism_hall",
            }
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("x", 1.0),
        ("y", 2.0),
        ("yaw", 0.0),
        ("ros_command", "ros2 action send_goal"),
        ("shell_command", "touch /tmp/file"),
        ("code", "print('unsafe')"),
    ],
)
def test_behavior_command_rejects_non_semantic_fields(field, value):
    data = {
        "skill": "navigate_to",
        "semantic_target": "impressionism_hall",
        field: value,
    }

    with pytest.raises(ContractValidationError, match=field):
        BehaviorCommand.from_dict(data)


def test_navigate_behavior_requires_semantic_target():
    with pytest.raises(ContractValidationError, match="semantic_target"):
        BehaviorCommand(skill=Skill.NAVIGATE_TO)


def test_interaction_command_converts_to_safe_behavior_command():
    interaction = InteractionCommand(
        request_id="req_007",
        session_id=SessionId("session_1"),
        skill=Skill.NAVIGATE_TO,
        semantic_target="ancient_art_hall",
    )

    assert interaction.to_behavior_command().to_dict() == {
        "skill": "navigate_to",
        "session_id": "session_1",
        "semantic_target": "ancient_art_hall",
    }


def test_escort_and_navigation_contract_values():
    assert EscortState.LOST.value == "lost"
    result = NavigationResult(
        semantic_target="ancient_art_hall",
        status=NavigationStatus.SUCCEEDED,
        session_id=SessionId("session_1"),
    )
    assert result.to_dict() == {
        "semantic_target": "ancient_art_hall",
        "status": "succeeded",
        "session_id": "session_1",
    }
