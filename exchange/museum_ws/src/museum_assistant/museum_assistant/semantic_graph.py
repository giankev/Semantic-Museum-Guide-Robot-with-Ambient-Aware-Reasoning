from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import networkx as nx
import yaml


VALID_STATUS = {"open", "closed"}
VALID_LEVELS = {"low", "medium", "high"}
ROOM_REQUIRED_FIELDS = {
    "id",
    "display_name",
    "type",
    "status",
    "crowd_level",
    "noise_level",
    "child_friendly",
    "wheelchair_accessible",
    "nav_pose",
    "description",
}
ARTWORK_REQUIRED_FIELDS = {
    "id",
    "title",
    "style",
    "period",
    "located_in",
    "tags",
    "description",
}
NAV_POSE_FIELDS = {"x", "y", "yaw"}


class SemanticMapError(ValueError):
    """Raised when the semantic map is incomplete or inconsistent."""


class MuseumSemanticGraph:
    def __init__(self, data: dict[str, Any]):
        self.data = data
        self.rooms = {room["id"]: room for room in data["rooms"]}
        self.artworks = {artwork["id"]: artwork for artwork in data["artworks"]}
        self.sensors = {sensor["id"]: sensor for sensor in data.get("sensors", [])}
        self.roles = {role["id"]: role for role in data.get("roles", [])}
        self.concepts = {concept["id"]: concept for concept in data.get("concepts", [])}
        self.graph = nx.DiGraph()
        self._build_graph()

    @classmethod
    def from_yaml(cls, path: str | Path) -> "MuseumSemanticGraph":
        map_path = Path(path)
        with map_path.open("r", encoding="utf-8") as stream:
            data = yaml.safe_load(stream) or {}
        validate_semantic_map(data)
        return cls(data)

    def _build_graph(self) -> None:
        for room in self.rooms.values():
            self.graph.add_node(room["id"], kind="room", **room)

        for artwork in self.artworks.values():
            self.graph.add_node(artwork["id"], kind="artwork", **artwork)
            self._add_labeled_edge(artwork["id"], artwork["located_in"], "located_in")

        for sensor in self.sensors.values():
            self.graph.add_node(sensor["id"], kind="sensor", **sensor)
            self._add_labeled_edge(sensor["id"], sensor["room"], "observes")
            self._add_labeled_edge(sensor["room"], sensor["id"], "has_sensor")

        for role in self.roles.values():
            self.graph.add_node(role["id"], kind="role", **role)
            for permission in role.get("can_update", []):
                self._add_labeled_edge(role["id"], permission, "can_update")

        for concept in self.concepts.values():
            self.graph.add_node(concept["id"], kind="concept", **concept)

        for relation in self.data.get("relations", []):
            self._add_labeled_edge(
                relation["source"],
                relation["target"],
                relation["relation"],
            )

    def _add_labeled_edge(self, source: str, target: str, relation: str) -> None:
        if self.graph.has_edge(source, target):
            relations = self.graph[source][target].setdefault("relations", [])
            if relation not in relations:
                relations.append(relation)
            self.graph[source][target]["relation"] = relation
            return
        self.graph.add_edge(source, target, relation=relation, relations=[relation])

    def room_ids(self) -> list[str]:
        return list(self.rooms.keys())

    def artwork_ids(self) -> list[str]:
        return list(self.artworks.keys())

    def get_room(self, room_id: str) -> dict[str, Any]:
        if room_id not in self.rooms:
            raise KeyError(f"Unknown room id: {room_id}")
        return deepcopy(self.rooms[room_id])

    def get_room_state(self, room_id: str) -> dict[str, str]:
        self._validate_room_id(room_id)
        room = self.rooms[room_id]
        return {
            "room_id": room_id,
            "status": room["status"],
            "crowd_level": room["crowd_level"],
            "noise_level": room["noise_level"],
        }

    def update_room_state(
        self,
        room_id: str,
        status: str | None = None,
        crowd_level: str | None = None,
        noise_level: str | None = None,
    ) -> dict[str, str]:
        self._validate_room_id(room_id)
        updates = {
            "status": status,
            "crowd_level": crowd_level,
            "noise_level": noise_level,
        }
        self._validate_room_state_values(room_id, updates)

        room = self.rooms[room_id]
        for field, value in updates.items():
            if value is not None:
                room[field] = value
                self.graph.nodes[room_id][field] = value

        return self.get_room_state(room_id)

    def get_artwork(self, artwork_id: str) -> dict[str, Any]:
        if artwork_id not in self.artworks:
            raise KeyError(f"Unknown artwork id: {artwork_id}")
        return deepcopy(self.artworks[artwork_id])

    def artworks_by_style(self, style: str) -> list[dict[str, Any]]:
        style_key = _normalize(style)
        return [
            deepcopy(artwork)
            for artwork in self.artworks.values()
            if _normalize(artwork["style"]) == style_key
        ]

    def artworks_in_room(self, room_id: str) -> list[dict[str, Any]]:
        if room_id not in self.rooms:
            raise KeyError(f"Unknown room id: {room_id}")
        return [
            deepcopy(artwork)
            for artwork in self.artworks.values()
            if artwork["located_in"] == room_id
        ]

    def rooms_matching(
        self,
        style: str | None = None,
        avoid_crowd: bool = False,
        child_friendly: bool | None = None,
        wheelchair_accessible: bool | None = None,
        require_open: bool = True,
    ) -> list[dict[str, Any]]:
        matches: list[dict[str, Any]] = []
        for room in self.rooms.values():
            rejected = self._room_rejections(
                room,
                style=style,
                avoid_crowd=avoid_crowd,
                child_friendly=child_friendly,
                wheelchair_accessible=wheelchair_accessible,
                require_open=require_open,
            )
            if not rejected:
                matches.append(deepcopy(room))
        return matches

    def recommend_room(
        self,
        style: str | None = None,
        avoid_crowd: bool = False,
        child_friendly: bool | None = None,
        wheelchair_accessible: bool | None = None,
    ) -> dict[str, Any]:
        rejected_rooms: list[dict[str, Any]] = []
        candidates: list[dict[str, Any]] = []

        for room in self.rooms.values():
            rejected = self._room_rejections(
                room,
                style=style,
                avoid_crowd=avoid_crowd,
                child_friendly=child_friendly,
                wheelchair_accessible=wheelchair_accessible,
                require_open=True,
            )
            if rejected:
                rejected_rooms.append({"room": room["id"], "reasons": rejected})
            else:
                candidates.append(room)

        if not candidates:
            return {
                "selected_room": None,
                "matching_artworks": [],
                "reason": "No open room satisfies the requested semantic constraints.",
                "rejected_rooms": rejected_rooms,
            }

        selected = sorted(
            candidates,
            key=lambda room: (
                0 if self._matching_artworks_for_room(room["id"], style) else 1,
                _crowd_rank(room["crowd_level"]),
                0 if room["status"] == "open" else 1,
                self.room_ids().index(room["id"]),
            ),
        )[0]

        matching_artworks = self._matching_artworks_for_room(selected["id"], style)
        reason = self._recommendation_reason(
            selected,
            matching_artworks,
            style,
            avoid_crowd,
            child_friendly,
            wheelchair_accessible,
        )

        return {
            "selected_room": deepcopy(selected),
            "matching_artworks": matching_artworks,
            "reason": reason,
            "rejected_rooms": rejected_rooms,
        }

    def _room_rejections(
        self,
        room: dict[str, Any],
        style: str | None,
        avoid_crowd: bool,
        child_friendly: bool | None,
        wheelchair_accessible: bool | None,
        require_open: bool,
    ) -> list[str]:
        rejected: list[str] = []
        if require_open and room["status"] != "open":
            rejected.append("room_closed")
        if avoid_crowd and room["crowd_level"] == "high":
            rejected.append("crowd_level_high")
        if child_friendly is not None and room["child_friendly"] != child_friendly:
            rejected.append("child_friendly_mismatch")
        if (
            wheelchair_accessible is not None
            and room["wheelchair_accessible"] != wheelchair_accessible
        ):
            rejected.append("wheelchair_accessible_mismatch")
        if style and not self._matching_artworks_for_room(room["id"], style):
            rejected.append("no_artwork_matching_style")
        return rejected

    def _matching_artworks_for_room(
        self, room_id: str, style: str | None = None
    ) -> list[dict[str, Any]]:
        artworks = [
            artwork
            for artwork in self.artworks.values()
            if artwork["located_in"] == room_id
        ]
        if style:
            style_key = _normalize(style)
            artworks = [
                artwork
                for artwork in artworks
                if _normalize(artwork["style"]) == style_key
            ]
        return [deepcopy(artwork) for artwork in artworks]

    def _recommendation_reason(
        self,
        selected: dict[str, Any],
        matching_artworks: list[dict[str, Any]],
        style: str | None,
        avoid_crowd: bool,
        child_friendly: bool | None,
        wheelchair_accessible: bool | None,
    ) -> str:
        parts = [
            f"Selected {selected['display_name']} because it is open",
            f"has {selected['crowd_level']} crowd level",
        ]
        if style:
            titles = ", ".join(artwork["title"] for artwork in matching_artworks)
            parts.append(f"contains {style} artwork: {titles}")
        if avoid_crowd:
            parts.append("satisfies the avoid-crowd constraint")
        if child_friendly is True:
            parts.append("is child-friendly")
        if wheelchair_accessible is True:
            parts.append("is wheelchair-accessible")
        return "; ".join(parts) + "."

    def _validate_room_id(self, room_id: str) -> None:
        if room_id not in self.rooms:
            raise ValueError(f"Unknown room id: {room_id}")

    def _validate_room_state_values(
        self, room_id: str, updates: dict[str, str | None]
    ) -> None:
        status = updates["status"]
        crowd_level = updates["crowd_level"]
        noise_level = updates["noise_level"]
        if status is not None and status not in VALID_STATUS:
            raise ValueError(
                f"Invalid status for room {room_id}: {status}. "
                f"Expected one of {sorted(VALID_STATUS)}."
            )
        if crowd_level is not None and crowd_level not in VALID_LEVELS:
            raise ValueError(
                f"Invalid crowd_level for room {room_id}: {crowd_level}. "
                f"Expected one of {sorted(VALID_LEVELS)}."
            )
        if noise_level is not None and noise_level not in VALID_LEVELS:
            raise ValueError(
                f"Invalid noise_level for room {room_id}: {noise_level}. "
                f"Expected one of {sorted(VALID_LEVELS)}."
            )


def load_semantic_graph(path: str | Path) -> MuseumSemanticGraph:
    return MuseumSemanticGraph.from_yaml(path)


def validate_semantic_map(data: dict[str, Any]) -> None:
    for field in ("rooms", "artworks", "roles", "sensors", "relations"):
        if field not in data:
            raise SemanticMapError(f"Missing top-level field: {field}")

    if not data["rooms"]:
        raise SemanticMapError("Semantic map must define at least one room")
    if not data["artworks"]:
        raise SemanticMapError("Semantic map must define at least one artwork")

    room_ids: set[str] = set()
    for room in data["rooms"]:
        _require_fields(room, ROOM_REQUIRED_FIELDS, "room")
        if room["id"] in room_ids:
            raise SemanticMapError(f"Duplicate room id: {room['id']}")
        room_ids.add(room["id"])
        if room["status"] not in VALID_STATUS:
            raise SemanticMapError(f"Invalid status for room {room['id']}: {room['status']}")
        for level_field in ("crowd_level", "noise_level"):
            if room[level_field] not in VALID_LEVELS:
                raise SemanticMapError(
                    f"Invalid {level_field} for room {room['id']}: {room[level_field]}"
                )
        _require_fields(room["nav_pose"], NAV_POSE_FIELDS, f"nav_pose for room {room['id']}")
        for bool_field in ("child_friendly", "wheelchair_accessible"):
            if not isinstance(room[bool_field], bool):
                raise SemanticMapError(f"{bool_field} must be boolean for room {room['id']}")

    artwork_ids: set[str] = set()
    for artwork in data["artworks"]:
        _require_fields(artwork, ARTWORK_REQUIRED_FIELDS, "artwork")
        if "artist" not in artwork and "culture" not in artwork:
            raise SemanticMapError(
                f"Artwork {artwork['id']} must define either artist or culture"
            )
        if artwork["id"] in artwork_ids:
            raise SemanticMapError(f"Duplicate artwork id: {artwork['id']}")
        artwork_ids.add(artwork["id"])
        if artwork["located_in"] not in room_ids:
            raise SemanticMapError(
                f"Artwork {artwork['id']} references unknown room {artwork['located_in']}"
            )
        if not isinstance(artwork["tags"], list):
            raise SemanticMapError(f"Artwork {artwork['id']} tags must be a list")

    sensor_ids: set[str] = set()
    for sensor in data.get("sensors", []):
        _require_fields(sensor, {"id", "type", "room", "observes"}, "sensor")
        if sensor["id"] in sensor_ids:
            raise SemanticMapError(f"Duplicate sensor id: {sensor['id']}")
        sensor_ids.add(sensor["id"])
        if sensor["room"] not in room_ids:
            raise SemanticMapError(
                f"Sensor {sensor['id']} references unknown room {sensor['room']}"
            )

    role_ids: set[str] = set()
    for role in data.get("roles", []):
        _require_fields(role, {"id", "display_name", "can_update"}, "role")
        if role["id"] in role_ids:
            raise SemanticMapError(f"Duplicate role id: {role['id']}")
        role_ids.add(role["id"])
        if not isinstance(role["can_update"], list):
            raise SemanticMapError(f"Role {role['id']} can_update must be a list")

    concept_ids = {concept["id"] for concept in data.get("concepts", [])}
    known_ids = room_ids | artwork_ids | sensor_ids | role_ids | concept_ids
    for relation in data.get("relations", []):
        _require_fields(relation, {"source", "relation", "target"}, "relation")
        if relation["source"] not in known_ids:
            raise SemanticMapError(f"Relation references unknown source {relation['source']}")
        if relation["target"] not in known_ids:
            raise SemanticMapError(f"Relation references unknown target {relation['target']}")


def _require_fields(item: dict[str, Any], fields: set[str], label: str) -> None:
    missing = sorted(fields - set(item))
    if missing:
        raise SemanticMapError(f"Missing fields for {label}: {', '.join(missing)}")


def _normalize(value: str) -> str:
    return value.strip().lower().replace("_", " ")


def _crowd_rank(level: str) -> int:
    return {"low": 0, "medium": 1, "high": 2}[level]
