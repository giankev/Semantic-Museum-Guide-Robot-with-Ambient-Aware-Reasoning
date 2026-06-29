from __future__ import annotations

from copy import deepcopy
from typing import Any


SUPPORTED_INTENTS = {"recommend", "recommend_and_prepare_navigation"}
SUPPORTED_CONSTRAINTS = {
    "style",
    "avoid_crowd",
    "child_friendly",
    "wheelchair_accessible",
}


class DeterministicReasoner:
    def __init__(self, semantic_graph):
        self.semantic_graph = semantic_graph

    def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        validation_error = self._validate_request(request)
        if validation_error:
            return _invalid_response(request, validation_error)

        request_id = request.get("request_id")
        intent = request["intent"]
        constraints = request.get("constraints", {})

        recommendation = self.semantic_graph.recommend_room(
            style=constraints.get("style"),
            avoid_crowd=constraints.get("avoid_crowd", False),
            child_friendly=constraints.get("child_friendly"),
            wheelchair_accessible=constraints.get("wheelchair_accessible"),
        )

        selected_room = recommendation["selected_room"]
        if not selected_room:
            return {
                "request_id": request_id,
                "status": "no_match",
                "intent": intent,
                "selected_room": None,
                "selected_room_display_name": None,
                "skill": "ask_clarification",
                "nav_pose": None,
                "reason": recommendation["reason"],
                "matching_artworks": [],
                "rejected_rooms": recommendation["rejected_rooms"],
            }

        return {
            "request_id": request_id,
            "status": "success",
            "intent": intent,
            "selected_room": selected_room["id"],
            "selected_room_display_name": selected_room["display_name"],
            "skill": "navigate_to",
            "nav_pose": deepcopy(selected_room["nav_pose"]),
            "reason": recommendation["reason"],
            "matching_artworks": [
                artwork["id"] for artwork in recommendation["matching_artworks"]
            ],
            "rejected_rooms": recommendation["rejected_rooms"],
        }

    def _validate_request(self, request: Any) -> str | None:
        if not isinstance(request, dict):
            return "Request must be a JSON object."

        request_id = request.get("request_id")
        if request_id is not None and not isinstance(request_id, str):
            return "request_id must be a string when provided."

        intent = request.get("intent")
        if intent not in SUPPORTED_INTENTS:
            supported = ", ".join(sorted(SUPPORTED_INTENTS))
            return f"Unsupported or missing intent. Supported intents: {supported}."

        constraints = request.get("constraints", {})
        if not isinstance(constraints, dict):
            return "constraints must be a JSON object when provided."

        unknown_constraints = sorted(set(constraints) - SUPPORTED_CONSTRAINTS)
        if unknown_constraints:
            return "Unsupported constraints: " + ", ".join(unknown_constraints) + "."

        style = constraints.get("style")
        if style is not None and not isinstance(style, str):
            return "constraints.style must be a string."

        for field in ("avoid_crowd", "child_friendly", "wheelchair_accessible"):
            value = constraints.get(field)
            if value is not None and not isinstance(value, bool):
                return f"constraints.{field} must be a boolean."

        return None


def reason_about_request(semantic_graph, request: dict[str, Any]) -> dict[str, Any]:
    return DeterministicReasoner(semantic_graph).handle_request(request)


def _invalid_response(request: Any, reason: str) -> dict[str, Any]:
    request_id = request.get("request_id") if isinstance(request, dict) else None
    intent = request.get("intent") if isinstance(request, dict) else None
    return {
        "request_id": request_id,
        "status": "invalid_request",
        "intent": intent,
        "selected_room": None,
        "selected_room_display_name": None,
        "skill": "ask_clarification",
        "nav_pose": None,
        "reason": reason,
        "matching_artworks": [],
        "rejected_rooms": [],
    }
