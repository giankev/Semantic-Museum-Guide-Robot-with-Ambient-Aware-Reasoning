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
        if (
            request.intent == "recommend_and_prepare_navigation"
            and not constraints
        ):
            return self._decide_follow_up(request)

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
            return self._clarification(
                request,
                recommendation["reason"],
                recommendation["rejected_rooms"],
            )

        decision = ReasoningDecision(
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
        if request.session_id:
            self.semantic_graph.remember_session_request(
                request.session_id, request.intent, constraints
            )
            self.semantic_graph.remember_session_destination(
                request.session_id, selected_room["id"]
            )
            state = "recommended"
            if request.intent == "recommend_and_prepare_navigation":
                state = "navigation_requested"
            self.semantic_graph.update_session_interaction_state(
                request.session_id, state
            )
        return decision

    def _decide_follow_up(
        self, request: StructuredRequest
    ) -> ReasoningDecision:
        context = (
            self.semantic_graph.get_session_context(request.session_id)
            if request.session_id
            else None
        )
        destination = context.get("wants_to_reach") if context else None
        if not destination:
            return self._clarification(
                request,
                "No previous destination is available for this session.",
                [],
            )

        constraints = context["constraints"]
        rejected = self.semantic_graph.room_rejections(destination, constraints)
        if rejected:
            return self._clarification(
                request,
                "The remembered destination no longer satisfies the current "
                "museum state and remembered preferences.",
                [{"room": destination, "reasons": rejected}],
            )

        room = self.semantic_graph.get_room(destination)
        self.semantic_graph.remember_session_request(
            request.session_id, request.intent, {}
        )
        self.semantic_graph.update_session_interaction_state(
            request.session_id, "navigation_requested"
        )
        return ReasoningDecision(
            request_id=request.request_id,
            session_id=request.session_id,
            status="success",
            intent=request.intent,
            selected_room=destination,
            selected_room_display_name=room["display_name"],
            skill=Skill.NAVIGATE_TO,
            nav_pose=room["nav_pose"],
            reason="Revalidated the remembered destination against the "
            "current semantic scene graph.",
            rejected_rooms=[],
        )

    def _clarification(
        self, request: StructuredRequest, reason: str,
        rejected_rooms: list[dict[str, Any]],
    ) -> ReasoningDecision:
        if request.session_id:
            self.semantic_graph.update_session_interaction_state(
                request.session_id, "clarification_needed"
            )
        return ReasoningDecision(
            request_id=request.request_id,
            session_id=request.session_id,
            status="no_match",
            intent=request.intent,
            skill=Skill.ASK_CLARIFICATION,
            reason=reason,
            rejected_rooms=rejected_rooms,
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
