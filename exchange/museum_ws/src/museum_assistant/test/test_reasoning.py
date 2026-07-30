from pathlib import Path

from museum_assistant.contracts import (
    DecisionStatus,
    ReasoningDecision,
    Skill,
    StructuredRequest,
)
from museum_assistant.reasoning import DeterministicReasoner
from museum_assistant.semantic_graph import load_semantic_graph


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SEMANTIC_MAP = PACKAGE_ROOT / "config" / "semantic_map.yaml"


def make_reasoner():
    return DeterministicReasoner(load_semantic_graph(SEMANTIC_MAP))


def test_current_deterministic_reasoning_behavior_is_preserved():
    response = make_reasoner().handle_request(
        {
            "request_id": "req_001",
            "intent": "recommend",
            "constraints": {
                "style": "impressionism",
                "avoid_crowd": True,
            },
        }
    )

    assert response["request_id"] == "req_001"
    assert response["status"] == "success"
    assert response["intent"] == "recommend"
    assert response["selected_room"] == "impressionism_hall"
    assert response["selected_room_display_name"] == "Impressionism Hall"
    assert response["skill"] == "navigate_to"
    assert response["nav_pose"] == {"x": 5.0, "y": 1.5, "yaw": 1.57}
    assert response["matching_artworks"] == ["monet_water_lilies"]
    assert "session_id" not in response


def test_reasoner_accepts_typed_request_and_returns_typed_decision():
    request = StructuredRequest.from_dict(
        {
            "request_id": "req_002",
            "session_id": "session_1",
            "intent": "recommend",
            "constraints": {"child_friendly": True},
        }
    )

    decision = make_reasoner().decide(request)

    assert isinstance(decision, ReasoningDecision)
    assert decision.status is DecisionStatus.SUCCESS
    assert decision.skill is Skill.NAVIGATE_TO
    assert decision.session_id == request.session_id
    assert decision.to_dict()["session_id"] == "session_1"


def test_reasoner_preserves_no_match_response():
    response = make_reasoner().handle_request(
        {
            "request_id": "req_003",
            "intent": "recommend",
            "constraints": {"style": "surrealist_clockwork"},
        }
    )

    assert response["status"] == "no_match"
    assert response["selected_room"] is None
    assert response["skill"] == "ask_clarification"
    assert response["nav_pose"] is None


def test_reasoner_returns_invalid_response_for_unsupported_intent():
    response = make_reasoner().handle_request(
        {
            "request_id": "req_004",
            "intent": "dance",
            "constraints": {},
        }
    )

    assert response["status"] == "invalid_request"
    assert response["intent"] == "dance"
    assert response["selected_room"] is None
    assert response["skill"] == "ask_clarification"
    assert "Unsupported or missing intent" in response["reason"]


def test_reasoner_returns_invalid_response_for_unsupported_constraint():
    response = make_reasoner().handle_request(
        {
            "request_id": "req_005",
            "intent": "recommend",
            "constraints": {"favorite_color": "blue"},
        }
    )

    assert response["status"] == "invalid_request"
    assert "favorite_color" in response["reason"]


def test_reasoner_rejects_unknown_request_fields():
    response = make_reasoner().handle_request(
        {
            "request_id": "req_006",
            "intent": "recommend",
            "constraints": {},
            "shell_command": "echo unsafe",
        }
    )

    assert response["status"] == "invalid_request"
    assert "shell_command" in response["reason"]
