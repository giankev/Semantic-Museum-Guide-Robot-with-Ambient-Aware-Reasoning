"""Resolve semantic decisions to supplied-museum routes without owning Nav2."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from museum_assistant.supplied_museum_navigation import load_route_plan


class SemanticRouteConfigurationError(ValueError):
    """Raised when semantic-to-physical route configuration is inconsistent."""


@dataclass(frozen=True)
class ResolvedSemanticRoute:
    semantic_room: str
    physical_room: str
    route: str
    final_candidate: str
    waypoint_names: tuple[str, ...]


@dataclass(frozen=True)
class DispatchResult:
    route_request: dict[str, Any] | None
    reason: str

    @property
    def dispatched(self) -> bool:
        return self.route_request is not None


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
    """Validated, immutable semantic-room to physical-route resolver."""

    def __init__(self, routes: dict[str, ResolvedSemanticRoute]):
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
        if mapping.get("schema_version") != 1:
            raise SemanticRouteConfigurationError(
                "Semantic route mapping schema_version must be 1"
            )
        definitions = mapping.get("semantic_routes")
        if not isinstance(definitions, dict) or not definitions:
            raise SemanticRouteConfigurationError(
                "semantic_routes must be a non-empty mapping"
            )

        try:
            layout = yaml.safe_load(layout_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise SemanticRouteConfigurationError(
                f"Cannot load supplied museum room layout: {exc}"
            ) from exc
        if not isinstance(layout, dict):
            raise SemanticRouteConfigurationError(
                "Supplied museum room layout must be a YAML mapping"
            )
        candidates = layout.get("candidate_poses")
        physical_areas = layout.get("physical_areas")
        if not isinstance(candidates, dict) or not isinstance(
            physical_areas, dict
        ):
            raise SemanticRouteConfigurationError(
                "Supplied museum room layout is missing candidates or areas"
            )

        semantic_room_ids = set(semantic_graph.room_ids())
        resolved: dict[str, ResolvedSemanticRoute] = {}
        for semantic_room, definition in definitions.items():
            if semantic_room not in semantic_room_ids:
                raise SemanticRouteConfigurationError(
                    f"Unknown semantic room in route mapping: {semantic_room}"
                )
            if not isinstance(definition, dict):
                raise SemanticRouteConfigurationError(
                    f"Mapping for {semantic_room} must be a YAML mapping"
                )
            route = definition.get("route")
            physical_room = definition.get("physical_room")
            if not isinstance(route, str) or not route:
                raise SemanticRouteConfigurationError(
                    f"Mapping for {semantic_room} has no valid route"
                )
            if not isinstance(physical_room, str) or not physical_room:
                raise SemanticRouteConfigurationError(
                    f"Mapping for {semantic_room} has no valid physical_room"
                )
            if route != physical_room:
                raise SemanticRouteConfigurationError(
                    f"Route {route!r} for {semantic_room} targets the different "
                    f"physical room {physical_room!r}"
                )
            if physical_room not in physical_areas:
                raise SemanticRouteConfigurationError(
                    f"Unknown physical room for {semantic_room}: {physical_room}"
                )
            try:
                waypoints = load_route_plan(route, routes_path, layout_path)
            except (OSError, ValueError, yaml.YAMLError) as exc:
                raise SemanticRouteConfigurationError(
                    f"Invalid route {route!r} for {semantic_room}: {exc}"
                ) from exc

            final_candidate = waypoints[-1].name
            final_definition = candidates.get(final_candidate)
            if not isinstance(final_definition, dict):
                raise SemanticRouteConfigurationError(
                    f"Final waypoint {final_candidate!r} is not a room candidate"
                )
            final_area = final_definition.get("area")
            if final_area != physical_room:
                raise SemanticRouteConfigurationError(
                    f"Route {route!r} for {semantic_room} ends in "
                    f"{final_area!r}, not {physical_room!r}"
                )
            resolved[semantic_room] = ResolvedSemanticRoute(
                semantic_room=semantic_room,
                physical_room=physical_room,
                route=route,
                final_candidate=final_candidate,
                waypoint_names=tuple(waypoint.name for waypoint in waypoints),
            )
        return cls(resolved)

    def resolve(self, semantic_room: str) -> ResolvedSemanticRoute:
        try:
            return self._routes[semantic_room]
        except KeyError as exc:
            raise KeyError(
                f"No supplied-museum route for semantic room: {semantic_room}"
            ) from exc

    def mappings(self) -> dict[str, ResolvedSemanticRoute]:
        return dict(self._routes)


class ReasoningRouteDispatcher:
    """Filter decisions and emit at most one route request per correlation id."""

    def __init__(self, resolver: SemanticRouteResolver):
        self.resolver = resolver
        self._dispatched: set[tuple[Any, Any]] = set()
        self.route_request_count = 0

    def prepare(self, decision: Any) -> DispatchResult:
        if not isinstance(decision, dict):
            return DispatchResult(None, "decision_not_object")
        if decision.get("status") != "success":
            return DispatchResult(None, "decision_status_not_success")
        if decision.get("skill") != "navigate_to":
            return DispatchResult(None, "skill_not_executable")

        semantic_room = decision.get("selected_room")
        if not isinstance(semantic_room, str) or not semantic_room:
            return DispatchResult(None, "selected_room_missing")
        correlation = (decision.get("session_id"), decision.get("request_id"))
        if correlation in self._dispatched:
            return DispatchResult(None, "duplicate_decision")
        try:
            resolved = self.resolver.resolve(semantic_room)
        except KeyError:
            return DispatchResult(None, "unknown_semantic_route")

        route_request = {
            "request_id": decision.get("request_id"),
            "session_id": decision.get("session_id"),
            "selected_room": semantic_room,
            "route": resolved.route,
            "physical_room": resolved.physical_room,
            "final_candidate": resolved.final_candidate,
            "waypoint_names": list(resolved.waypoint_names),
        }
        self._dispatched.add(correlation)
        self.route_request_count += 1
        return DispatchResult(route_request, "dispatched")
