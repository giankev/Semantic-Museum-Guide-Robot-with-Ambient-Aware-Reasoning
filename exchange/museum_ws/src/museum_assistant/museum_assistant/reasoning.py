from __future__ import annotations

from typing import Any

from museum_assistant.contracts import (
    ContractValidationError,
    ReasoningDecision,
    Skill,
    StructuredRequest,
    SUPPORTED_CONSTRAINTS as CONTRACT_SUPPORTED_CONSTRAINTS,
    SUPPORTED_INTENTS as CONTRACT_SUPPORTED_INTENTS,
)


SUPPORTED_INTENTS = CONTRACT_SUPPORTED_INTENTS
SUPPORTED_CONSTRAINTS = CONTRACT_SUPPORTED_CONSTRAINTS


class DeterministicReasoner:
    def __init__(self, semantic_graph):
        self.semantic_graph = semantic_graph

    def handle_request(self, request: Any) -> dict[str, Any]:
        """Validate a JSON-compatible request and serialize its decision."""
        try:
            structured_request = StructuredRequest.from_dict(request)
        except ContractValidationError as exc:
            return _invalid_response(request, str(exc))

        return self.decide(structured_request).to_dict()

    def decide(self, request: StructuredRequest) -> ReasoningDecision:
        """Apply deterministic semantic reasoning to a validated request."""
        constraints = request.constraints
        recommendation = self.semantic_graph.recommend_room(
            style=constraints.get("style"),
            avoid_crowd=constraints.get("avoid_crowd", False),
            avoid_noise=constraints.get("avoid_noise", False),
            child_friendly=constraints.get("child_friendly"),
            wheelchair_accessible=constraints.get(
                "wheelchair_accessible"
            ),
        )

        selected_room = recommendation["selected_room"]
        if not selected_room:
            return ReasoningDecision(
                request_id=request.request_id,
                session_id=request.session_id,
                status="no_match",
                intent=request.intent,
                selected_room=None,
                selected_room_display_name=None,
                skill=Skill.ASK_CLARIFICATION,
                nav_pose=None,
                reason=recommendation["reason"],
                rejected_rooms=recommendation["rejected_rooms"],
            )

        return ReasoningDecision(
            request_id=request.request_id,
            session_id=request.session_id,
            status="success",
            intent=request.intent,
            selected_room=selected_room["id"],
            selected_room_display_name=selected_room["display_name"],
            skill=Skill.NAVIGATE_TO,
            nav_pose=selected_room["nav_pose"],
            reason=recommendation["reason"],
            matching_artworks=[
                artwork["id"]
                for artwork in recommendation["matching_artworks"]
            ],
            rejected_rooms=recommendation["rejected_rooms"],
        )

    def _validate_request(self, request: Any) -> str | None:
        """Compatibility helper retained for callers of the previous API."""
        try:
            StructuredRequest.from_dict(request)
        except ContractValidationError as exc:
            return str(exc)
        return None


def reason_about_request(
    semantic_graph,
    request: Any,
) -> dict[str, Any]:
    return DeterministicReasoner(semantic_graph).handle_request(request)


def _invalid_response(
    request: Any,
    reason: str,
) -> dict[str, Any]:
    request_id = None
    intent = None
    session_id = None

    if isinstance(request, dict):
        if isinstance(request.get("request_id"), str):
            request_id = request["request_id"]
        if isinstance(request.get("intent"), str):
            intent = request["intent"]
        if isinstance(request.get("session_id"), str):
            session_id = request["session_id"]

    return ReasoningDecision.invalid(
        request_id=request_id,
        session_id=session_id,
        intent=intent,
        reason=reason,
    ).to_dict()
