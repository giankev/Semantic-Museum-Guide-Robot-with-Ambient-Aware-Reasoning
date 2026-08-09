"""Resolve semantic decisions to supplied-museum routes without owning Nav2."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from museum_assistant.supplied_museum_navigation import load_route_plan


class SemanticRouteConfigurationError(ValueError):
    """Raised when semantic-to-physical route configuration is inconsistent."""


def _read_mapping(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SemanticRouteConfigurationError(
            f"Cannot read semantic route mapping {path}: {exc}"
        ) from exc
    except yaml.YAMLError as exc:
        raise SemanticRouteConfigurationError(
            f"Invalid YAML in semantic route mapping {path}: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise SemanticRouteConfigurationError(
            "Semantic route mapping must contain a YAML mapping"
        )
    return data


class SemanticRouteResolver:
    """Validated semantic-room to supplied-museum route resolver."""

    def __init__(self, routes: dict[str, str]):
        self._routes = dict(routes)

    @classmethod
    def from_files(
        cls,
        mapping_path: str | Path,
        semantic_graph,
        routes_path: str | Path,
        layout_path: str | Path,
    ) -> "SemanticRouteResolver":
        mapping_path = Path(mapping_path)
        routes_path = Path(routes_path)
        layout_path = Path(layout_path)
        mapping = _read_mapping(mapping_path)
        definitions = mapping.get("semantic_routes")
        if not isinstance(definitions, dict) or not definitions:
            raise SemanticRouteConfigurationError(
                "semantic_routes must be a non-empty mapping"
            )

        semantic_room_ids = set(semantic_graph.room_ids())
        resolved: dict[str, str] = {}
        for semantic_room, route in definitions.items():
            if semantic_room not in semantic_room_ids:
                raise SemanticRouteConfigurationError(
                    f"Unknown semantic room in route mapping: {semantic_room}"
                )
            if not isinstance(route, str) or not route:
                raise SemanticRouteConfigurationError(
                    f"Mapping for {semantic_room} has no valid route"
                )
            try:
                load_route_plan(route, routes_path, layout_path)
            except (OSError, ValueError, yaml.YAMLError) as exc:
                raise SemanticRouteConfigurationError(
                    f"Invalid route {route!r} for {semantic_room}: {exc}"
                ) from exc
            resolved[semantic_room] = route
        return cls(resolved)

    def resolve(self, semantic_room: str) -> str:
        try:
            return self._routes[semantic_room]
        except KeyError as exc:
            raise KeyError(
                f"No supplied-museum route for semantic room: {semantic_room}"
            ) from exc

    def mappings(self) -> dict[str, str]:
        return dict(self._routes)


class ReasoningRouteDispatcher:
    """Filter decisions and emit at most one route request per correlation id."""

    def __init__(self, resolver: SemanticRouteResolver):
        self.resolver = resolver
        self._dispatched: set[tuple[Any, Any]] = set()
        self.route_request_count = 0

    def prepare(self, decision: Any) -> tuple[dict[str, Any] | None, str]:
        if not isinstance(decision, dict):
            return None, "decision_not_object"
        if decision.get("status") != "success":
            return None, "decision_status_not_success"
        if decision.get("intent") != "recommend_and_prepare_navigation":
            return None, "intent_not_executable"
        if decision.get("skill") != "navigate_to":
            return None, "skill_not_executable"

        semantic_room = decision.get("selected_room")
        if not isinstance(semantic_room, str) or not semantic_room:
            return None, "selected_room_missing"
        correlation = (decision.get("session_id"), decision.get("request_id"))
        if correlation in self._dispatched:
            return None, "duplicate_decision"
        try:
            route = self.resolver.resolve(semantic_room)
        except KeyError:
            return None, "unknown_semantic_route"

        route_request = {
            "request_id": decision.get("request_id"),
            "session_id": decision.get("session_id"),
            "selected_room": semantic_room,
            "route": route,
        }
        self._dispatched.add(correlation)
        self.route_request_count += 1
        return route_request, "dispatched"
