"""Minimal ROS-independent contracts for the museum assistant."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, replace
from enum import Enum
import math
import re
from typing import Any


SUPPORTED_CONSTRAINTS = {
    "style",
    "avoid_crowd",
    "child_friendly",
    "wheelchair_accessible",
}

_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_NAV_POSE_FIELDS = {"x", "y", "yaw"}


class ContractValidationError(ValueError):
    """Raised when data does not satisfy a contract."""


class RequestIntent(str, Enum):
    RECOMMEND = "recommend"
    RECOMMEND_AND_PREPARE_NAVIGATION = "recommend_and_prepare_navigation"


class DecisionStatus(str, Enum):
    SUCCESS = "success"
    NO_MATCH = "no_match"
    INVALID_REQUEST = "invalid_request"


class Skill(str, Enum):
    """Fixed whitelist of currently supported abstract skills."""

    NAVIGATE_TO = "navigate_to"
    ASK_CLARIFICATION = "ask_clarification"


class SessionLifecycle(str, Enum):
    CREATED = "created"
    ACTIVE = "active"
    ENDING = "ending"
    CLOSED = "closed"


_SESSION_TRANSITIONS = {
    SessionLifecycle.CREATED: {SessionLifecycle.ACTIVE},
    SessionLifecycle.ACTIVE: {SessionLifecycle.ENDING},
    SessionLifecycle.ENDING: {SessionLifecycle.CLOSED},
    SessionLifecycle.CLOSED: set(),
}


class EscortState(str, Enum):
    """Contract values only; no escort supervisor is implemented."""

    FOLLOWING = "following"
    STOPPED = "stopped"
    LAGGING = "lagging"
    LOST = "lost"
    RECOVERED = "recovered"
    ARRIVED = "arrived"


class NavigationStatus(str, Enum):
    SUCCEEDED = "succeeded"
    ABORTED = "aborted"
    CANCELED = "canceled"
    REJECTED = "rejected"


@dataclass(frozen=True)
class PersonTrackId:
    value: str

    def __post_init__(self) -> None:
        _validate_identifier(self.value, "PersonTrackId")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class SessionId:
    value: str

    def __post_init__(self) -> None:
        _validate_identifier(self.value, "SessionId")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class PersonTrack:
    """Transient identity with no simulation-specific identifier."""

    track_id: PersonTrackId
    observed_at: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "track_id", _as_track_id(self.track_id))
        if (
            isinstance(self.observed_at, bool)
            or not isinstance(self.observed_at, (int, float))
            or not math.isfinite(self.observed_at)
            or self.observed_at < 0
        ):
            raise ContractValidationError(
                "observed_at must be a finite, non-negative number."
            )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PersonTrack":
        _validate_object(data, {"track_id", "observed_at"}, "PersonTrack")
        return cls(
            track_id=_as_track_id(data.get("track_id")),
            observed_at=data.get("observed_at"),
        )


@dataclass(frozen=True)
class SessionState:
    session_id: SessionId
    person_track_id: PersonTrackId
    lifecycle: SessionLifecycle = SessionLifecycle.CREATED

    def __post_init__(self) -> None:
        object.__setattr__(self, "session_id", _as_session_id(self.session_id))
        object.__setattr__(
            self,
            "person_track_id",
            _as_track_id(self.person_track_id),
        )
        object.__setattr__(
            self,
            "lifecycle",
            _as_enum(self.lifecycle, SessionLifecycle, "session lifecycle"),
        )

    def transition_to(self, lifecycle: SessionLifecycle) -> "SessionState":
        target = _as_enum(
            lifecycle,
            SessionLifecycle,
            "session lifecycle",
        )
        if target not in _SESSION_TRANSITIONS[self.lifecycle]:
            raise ContractValidationError(
                "Invalid session transition: "
                f"{self.lifecycle.value} -> {target.value}."
            )
        return replace(self, lifecycle=target)


@dataclass(frozen=True)
class StructuredRequest:
    """Validated language-to-reasoning request."""

    intent: RequestIntent
    request_id: str | None = None
    constraints: dict[str, Any] = field(default_factory=dict)
    session_id: SessionId | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "intent",
            _as_request_intent(self.intent),
        )
        _validate_optional_string(self.request_id, "request_id")

        if not isinstance(self.constraints, dict):
            raise ContractValidationError(
                "constraints must be a JSON object when provided."
            )
        unknown = sorted(set(self.constraints) - SUPPORTED_CONSTRAINTS)
        if unknown:
            raise ContractValidationError(
                f"Unsupported constraints: {', '.join(unknown)}."
            )

        constraints = deepcopy(self.constraints)
        style = constraints.get("style")
        if style is not None and not isinstance(style, str):
            raise ContractValidationError(
                "constraints.style must be a string."
            )
        for name in (
            "avoid_crowd",
            "child_friendly",
            "wheelchair_accessible",
        ):
            value = constraints.get(name)
            if value is not None and not isinstance(value, bool):
                raise ContractValidationError(
                    f"constraints.{name} must be a boolean."
                )
        object.__setattr__(self, "constraints", constraints)

        if self.session_id is not None:
            object.__setattr__(
                self,
                "session_id",
                _as_session_id(self.session_id),
            )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StructuredRequest":
        _validate_object(
            data,
            {"request_id", "session_id", "intent", "constraints"},
            "request",
        )
        return cls(
            request_id=data.get("request_id"),
            session_id=_optional_session_id(data.get("session_id")),
            intent=data.get("intent"),
            constraints=data.get("constraints", {}),
        )

    def to_dict(self) -> dict[str, Any]:
        data = {
            "request_id": self.request_id,
            "intent": self.intent.value,
            "constraints": deepcopy(self.constraints),
        }
        if self.session_id is not None:
            data["session_id"] = self.session_id.value
        return data


@dataclass(frozen=True)
class ReasoningDecision:
    """Typed result whose semantic target is authoritative.

    ``nav_pose`` remains only for current JSON compatibility and debugging.
    Raw poses are not part of the language-to-behavior interface.
    """

    status: DecisionStatus
    skill: Skill
    reason: str
    request_id: str | None = None
    session_id: SessionId | None = None
    intent: str | None = None
    semantic_target: str | None = None
    semantic_target_display_name: str | None = None
    nav_pose: dict[str, float] | None = None
    matching_artworks: tuple[str, ...] = ()
    rejected_rooms: tuple[dict[str, Any], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "status",
            _as_enum(self.status, DecisionStatus, "decision status"),
        )
        object.__setattr__(
            self,
            "skill",
            _as_enum(self.skill, Skill, "skill"),
        )
        _validate_optional_string(self.request_id, "request_id")
        _validate_optional_string(self.intent, "intent")
        _validate_text(self.reason, "reason")
        _validate_optional_text(self.semantic_target, "semantic_target")
        _validate_optional_text(
            self.semantic_target_display_name,
            "semantic_target_display_name",
        )

        if self.session_id is not None:
            object.__setattr__(
                self,
                "session_id",
                _as_session_id(self.session_id),
            )

        _validate_skill_target(self.skill, self.semantic_target)
        if (
            self.status is DecisionStatus.SUCCESS
            and self.skill is not Skill.NAVIGATE_TO
        ):
            raise ContractValidationError(
                "A successful decision must use navigate_to."
            )
        if (
            self.status
            in {DecisionStatus.NO_MATCH, DecisionStatus.INVALID_REQUEST}
            and self.skill is not Skill.ASK_CLARIFICATION
        ):
            raise ContractValidationError(
                f"A {self.status.value} decision must use ask_clarification."
            )

        if self.nav_pose is not None:
            if self.skill is not Skill.NAVIGATE_TO:
                raise ContractValidationError(
                    "nav_pose is allowed only for navigate_to decisions."
                )
            object.__setattr__(
                self,
                "nav_pose",
                _validated_nav_pose(self.nav_pose),
            )

        try:
            artworks = tuple(self.matching_artworks)
            rejected = tuple(deepcopy(self.rejected_rooms))
        except TypeError as exc:
            raise ContractValidationError(
                "Decision collections must be iterable."
            ) from exc
        for artwork_id in artworks:
            _validate_text(artwork_id, "matching artwork id")
        if not all(isinstance(item, dict) for item in rejected):
            raise ContractValidationError(
                "rejected_rooms must contain JSON objects."
            )
        object.__setattr__(self, "matching_artworks", artworks)
        object.__setattr__(self, "rejected_rooms", rejected)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReasoningDecision":
        _validate_object(
            data,
            {
                "request_id",
                "session_id",
                "status",
                "intent",
                "selected_room",
                "selected_room_display_name",
                "skill",
                "nav_pose",
                "reason",
                "matching_artworks",
                "rejected_rooms",
            },
            "ReasoningDecision",
        )
        return cls(
            request_id=data.get("request_id"),
            session_id=_optional_session_id(data.get("session_id")),
            status=data.get("status"),
            intent=data.get("intent"),
            semantic_target=data.get("selected_room"),
            semantic_target_display_name=data.get(
                "selected_room_display_name"
            ),
            skill=data.get("skill"),
            nav_pose=data.get("nav_pose"),
            reason=data.get("reason"),
            matching_artworks=tuple(data.get("matching_artworks", [])),
            rejected_rooms=tuple(data.get("rejected_rooms", [])),
        )

    @classmethod
    def invalid(
        cls,
        reason: str,
        request_id: str | None = None,
        session_id: SessionId | None = None,
        intent: str | None = None,
    ) -> "ReasoningDecision":
        return cls(
            request_id=request_id,
            session_id=session_id,
            status=DecisionStatus.INVALID_REQUEST,
            intent=intent,
            skill=Skill.ASK_CLARIFICATION,
            reason=reason,
        )

    def to_dict(self) -> dict[str, Any]:
        data = {
            "request_id": self.request_id,
            "status": self.status.value,
            "intent": self.intent,
            "selected_room": self.semantic_target,
            "selected_room_display_name": (
                self.semantic_target_display_name
            ),
            "skill": self.skill.value,
            "nav_pose": deepcopy(self.nav_pose),
            "reason": self.reason,
            "matching_artworks": list(self.matching_artworks),
            "rejected_rooms": deepcopy(list(self.rejected_rooms)),
        }
        if self.session_id is not None:
            data["session_id"] = self.session_id.value
        return data


@dataclass(frozen=True)
class InteractionCommand:
    """Interaction intent; no Interaction Manager is implemented."""

    skill: Skill
    request_id: str | None = None
    session_id: SessionId | None = None
    semantic_target: str | None = None
    clarification_question: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "skill", _as_enum(self.skill, Skill, "skill"))
        _validate_optional_string(self.request_id, "request_id")
        _validate_optional_text(self.semantic_target, "semantic_target")
        _validate_optional_text(
            self.clarification_question,
            "clarification_question",
        )
        if self.session_id is not None:
            object.__setattr__(
                self,
                "session_id",
                _as_session_id(self.session_id),
            )
        _validate_command_arguments(
            self.skill,
            self.semantic_target,
            self.clarification_question,
        )

    def to_behavior_command(self) -> "BehaviorCommand":
        return BehaviorCommand(
            skill=self.skill,
            session_id=self.session_id,
            semantic_target=self.semantic_target,
            clarification_question=self.clarification_question,
        )


@dataclass(frozen=True)
class BehaviorCommand:
    """Whitelisted semantic command; text fields are never executable."""

    skill: Skill
    session_id: SessionId | None = None
    semantic_target: str | None = None
    clarification_question: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "skill", _as_enum(self.skill, Skill, "skill"))
        _validate_optional_text(self.semantic_target, "semantic_target")
        _validate_optional_text(
            self.clarification_question,
            "clarification_question",
        )
        if self.session_id is not None:
            object.__setattr__(
                self,
                "session_id",
                _as_session_id(self.session_id),
            )
        _validate_command_arguments(
            self.skill,
            self.semantic_target,
            self.clarification_question,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BehaviorCommand":
        _validate_object(
            data,
            {
                "skill",
                "session_id",
                "semantic_target",
                "clarification_question",
            },
            "BehaviorCommand",
        )
        return cls(
            skill=data.get("skill"),
            session_id=_optional_session_id(data.get("session_id")),
            semantic_target=data.get("semantic_target"),
            clarification_question=data.get("clarification_question"),
        )

    def to_dict(self) -> dict[str, Any]:
        data = {
            "skill": self.skill.value,
            "semantic_target": self.semantic_target,
        }
        if self.session_id is not None:
            data["session_id"] = self.session_id.value
        if self.clarification_question is not None:
            data["clarification_question"] = self.clarification_question
        return data


@dataclass(frozen=True)
class NavigationResult:
    """Semantic outcome; no Nav2 semantic executor is implemented."""

    semantic_target: str
    status: NavigationStatus
    session_id: SessionId | None = None

    def __post_init__(self) -> None:
        _validate_text(self.semantic_target, "semantic_target")
        object.__setattr__(
            self,
            "status",
            _as_enum(self.status, NavigationStatus, "navigation status"),
        )
        if self.session_id is not None:
            object.__setattr__(
                self,
                "session_id",
                _as_session_id(self.session_id),
            )

    def to_dict(self) -> dict[str, str]:
        data = {
            "semantic_target": self.semantic_target,
            "status": self.status.value,
        }
        if self.session_id is not None:
            data["session_id"] = self.session_id.value
        return data


def _validate_identifier(value: Any, label: str) -> None:
    if not isinstance(value, str) or not _IDENTIFIER_PATTERN.fullmatch(value):
        raise ContractValidationError(
            f"{label} must be 1-64 characters using letters, digits, "
            "underscores, or hyphens, and must start with a letter or digit."
        )


def _as_track_id(value: Any) -> PersonTrackId:
    return value if isinstance(value, PersonTrackId) else PersonTrackId(value)


def _as_session_id(value: Any) -> SessionId:
    return value if isinstance(value, SessionId) else SessionId(value)


def _optional_session_id(value: Any) -> SessionId | None:
    return None if value is None else _as_session_id(value)


def _as_request_intent(value: Any) -> RequestIntent:
    try:
        return (
            value
            if isinstance(value, RequestIntent)
            else RequestIntent(value)
        )
    except (TypeError, ValueError) as exc:
        supported = ", ".join(intent.value for intent in RequestIntent)
        raise ContractValidationError(
            "Unsupported or missing intent. "
            f"Supported intents: {supported}."
        ) from exc


def _as_enum(value: Any, enum_type: type[Enum], label: str) -> Any:
    try:
        return value if isinstance(value, enum_type) else enum_type(value)
    except (TypeError, ValueError) as exc:
        allowed = ", ".join(item.value for item in enum_type)
        raise ContractValidationError(
            f"Unsupported {label}: {value!r}. Allowed values: {allowed}."
        ) from exc


def _validate_object(
    data: Any,
    allowed_fields: set[str],
    label: str,
) -> None:
    if not isinstance(data, dict):
        raise ContractValidationError(
            f"{label.capitalize()} must be a JSON object."
        )
    unknown = sorted(set(data) - allowed_fields)
    if unknown:
        raise ContractValidationError(
            f"Unsupported {label} fields: {', '.join(unknown)}."
        )


def _validate_text(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContractValidationError(f"{label} must be a non-empty string.")


def _validate_optional_text(value: Any, label: str) -> None:
    if value is not None:
        _validate_text(value, label)


def _validate_optional_string(value: Any, label: str) -> None:
    if value is not None and not isinstance(value, str):
        raise ContractValidationError(
            f"{label} must be a string when provided."
        )


def _validate_skill_target(skill: Skill, target: str | None) -> None:
    if skill is Skill.NAVIGATE_TO and target is None:
        raise ContractValidationError(
            "navigate_to requires a semantic_target."
        )
    if skill is Skill.ASK_CLARIFICATION and target is not None:
        raise ContractValidationError(
            "ask_clarification must not contain a semantic_target."
        )


def _validate_command_arguments(
    skill: Skill,
    target: str | None,
    question: str | None,
) -> None:
    _validate_skill_target(skill, target)
    if skill is Skill.NAVIGATE_TO and question is not None:
        raise ContractValidationError(
            "navigate_to must not contain a clarification_question."
        )
    if skill is Skill.ASK_CLARIFICATION and question is None:
        raise ContractValidationError(
            "ask_clarification requires a clarification_question."
        )


def _validated_nav_pose(value: Any) -> dict[str, float]:
    if not isinstance(value, dict) or set(value) != _NAV_POSE_FIELDS:
        raise ContractValidationError(
            "nav_pose must contain exactly x, y, and yaw."
        )
    pose = {}
    for name in ("x", "y", "yaw"):
        coordinate = value[name]
        if (
            isinstance(coordinate, bool)
            or not isinstance(coordinate, (int, float))
            or not math.isfinite(coordinate)
        ):
            raise ContractValidationError(
                f"nav_pose.{name} must be a finite number."
            )
        pose[name] = float(coordinate)
    return pose
