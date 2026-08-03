from pathlib import Path

import pytest

from museum_assistant.contracts import (
    ContractValidationError,
    PersonTrack,
    ReasoningDecision,
    SessionLifecycle,
    SessionState,
    StructuredRequest,
)
from museum_assistant.reasoning import DeterministicReasoner
from museum_assistant.semantic_graph import load_semantic_graph


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SEMANTIC_MAP = PACKAGE_ROOT / "config" / "semantic_map.yaml"


def make_reasoner():
    return DeterministicReasoner(load_semantic_graph(SEMANTIC_MAP))


def test_person_track_and_session_state_creation():
    track = PersonTrack(track_id="track_1")
    session = SessionState(
        session_id="session_1",
        track_id=track.track_id,
    )

    assert track.track_id == "track_1"
    assert session.session_id == "session_1"
    assert session.track_id == "track_1"
    assert session.state is SessionLifecycle.CREATED


def test_valid_current_request():
    data = {
        "request_id": "req_001",
        "intent": "recommend",
        "constraints": {
            "style": "impressionism",
            "avoid_crowd": True,
        },
    }

    assert StructuredRequest.from_dict(data).to_dict() == data


def test_request_with_optional_session_id():
    data = {
        "request_id": "req_002",
        "session_id": "session_1",
        "intent": "recommend_and_prepare_navigation",
        "constraints": {"wheelchair_accessible": True},
    }

    request = StructuredRequest.from_dict(data)

    assert request.session_id == "session_1"
    assert request.to_dict() == data


def test_session_id_passes_through_reasoning_decision():
    request = StructuredRequest.from_dict(
        {
            "request_id": "req_session",
            "session_id": "session_1",
            "intent": "recommend",
            "constraints": {"style": "impressionism"},
        }
    )

    decision = make_reasoner().decide(request)

    assert isinstance(decision, ReasoningDecision)
    assert decision.session_id == "session_1"
    assert decision.to_dict()["session_id"] == "session_1"


def test_request_rejects_invalid_intent():
    with pytest.raises(ContractValidationError):
        StructuredRequest.from_dict(
            {
                "request_id": "req_003",
                "intent": "dance",
                "constraints": {},
            }
        )


def test_request_rejects_invalid_constraint():
    with pytest.raises(ContractValidationError):
        StructuredRequest.from_dict(
            {
                "request_id": "req_004",
                "intent": "recommend",
                "constraints": {"favorite_color": "blue"},
            }
        )


def test_deterministic_reasoning_success_is_preserved():
    response = make_reasoner().handle_request(
        {
            "request_id": "req_005",
            "intent": "recommend",
            "constraints": {
                "style": "impressionism",
                "avoid_crowd": True,
            },
        }
    )

    assert response["status"] == "success"
    assert response["selected_room"] == "impressionism_hall"
    assert response["skill"] == "navigate_to"
    assert response["nav_pose"] == {"x": 5.0, "y": 1.5, "yaw": 1.57}
    assert "session_id" not in response


def test_deterministic_reasoning_no_match_is_preserved():
    response = make_reasoner().handle_request(
        {
            "request_id": "req_006",
            "intent": "recommend",
            "constraints": {"style": "surrealist_clockwork"},
        }
    )

    assert response["status"] == "no_match"
    assert response["selected_room"] is None
    assert response["skill"] == "ask_clarification"


def test_deterministic_reasoning_invalid_response_is_preserved():
    response = make_reasoner().handle_request(
        {
            "request_id": "req_007",
            "intent": "dance",
            "constraints": {},
        }
    )

    assert response["status"] == "invalid_request"
    assert response["selected_room"] is None
    assert response["skill"] == "ask_clarification"
