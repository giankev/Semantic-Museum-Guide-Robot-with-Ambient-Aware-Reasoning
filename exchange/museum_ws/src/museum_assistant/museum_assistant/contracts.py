"""Small ROS-independent data models used by the current reasoning pipeline."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


SUPPORTED_INTENTS = {"recommend", "recommend_and_prepare_navigation"}
SUPPORTED_CONSTRAINTS = {
    "style",
    "avoid_crowd",
    "child_friendly",
    "wheelchair_accessible",
}


class ContractValidationError(ValueError):
    """Raised when request data does not match the supported schema."""


class Skill(str, Enum):
    NAVIGATE_TO = "navigate_to"
    ASK_CLARIFICATION = "ask_clarification"


class SessionLifecycle(str, Enum):
    CREATED = "created"
    ACTIVE = "active"
    ENDING = "ending"
    CLOSED = "closed"


@dataclass
class PersonTrack:
    """Transient person identifier produced after the perception boundary."""

    track_id: str

    def __post_init__(self) -> None:
        _require_nonempty_string(self.track_id, "track_id")


@dataclass
class SessionState:
    """Minimum state needed by the next Session Manager milestone."""

    session_id: str
    track_id: str
    state: SessionLifecycle = SessionLifecycle.CREATED

    def __post_init__(self) -> None:
        _require_nonempty_string(self.session_id, "session_id")
        _require_nonempty_string(self.track_id, "track_id")
        try:
            self.state = SessionLifecycle(self.state)
        except (TypeError, ValueError) as exc:
            raise ContractValidationError(
                f"Unknown session state: {self.state!r}."
            ) from exc

    def to_dict(self) -> dict[str, str]:
        return {
            "session_id": self.session_id,
            "track_id": self.track_id,
            "state": self.state.value,
        }


@dataclass
class StructuredRequest:
    """Validated form of the existing user-request JSON."""

    intent: str
    constraints: dict[str, Any] = field(default_factory=dict)
    request_id: str | None = None
    session_id: str | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.intent, str)
            or self.intent not in SUPPORTED_INTENTS
        ):
            supported = ", ".join(sorted(SUPPORTED_INTENTS))
            raise ContractValidationError(
                "Unsupported or missing intent. "
                f"Supported intents: {supported}."
            )
        _validate_optional_string(self.request_id, "request_id")
        _validate_optional_string(self.session_id, "session_id")

        if not isinstance(self.constraints, dict):
            raise ContractValidationError(
                "constraints must be a JSON object when provided."
            )
        unknown = sorted(set(self.constraints) - SUPPORTED_CONSTRAINTS)
        if unknown:
            raise ContractValidationError(
                f"Unsupported constraints: {', '.join(unknown)}."
            )

        style = self.constraints.get("style")
        if style is not None and not isinstance(style, str):
            raise ContractValidationError(
                "constraints.style must be a string."
            )
        for name in (
            "avoid_crowd",
            "child_friendly",
            "wheelchair_accessible",
        ):
            value = self.constraints.get(name)
            if value is not None and not isinstance(value, bool):
                raise ContractValidationError(
                    f"constraints.{name} must be a boolean."
                )

        self.constraints = dict(self.constraints)

    @classmethod
    def from_dict(cls, data: Any) -> "StructuredRequest":
        if not isinstance(data, dict):
            raise ContractValidationError("Request must be a JSON object.")
        return cls(
            request_id=data.get("request_id"),
            session_id=data.get("session_id"),
            intent=data.get("intent"),
            constraints=data.get("constraints", {}),
        )

    def to_dict(self) -> dict[str, Any]:
        data = {
            "request_id": self.request_id,
            "intent": self.intent,
            "constraints": dict(self.constraints),
        }
        if self.session_id is not None:
            data["session_id"] = self.session_id
        return data


@dataclass
class ReasoningDecision:
    """Typed form of the existing assistant-response JSON."""

    status: str
    skill: Skill
    reason: str
    request_id: str | None = None
    session_id: str | None = None
    intent: str | None = None
    selected_room: str | None = None
    selected_room_display_name: str | None = None
    nav_pose: dict[str, float] | None = None
    matching_artworks: list[str] = field(default_factory=list)
    rejected_rooms: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = {
            "request_id": self.request_id,
            "status": self.status,
            "intent": self.intent,
            "selected_room": self.selected_room,
            "selected_room_display_name": self.selected_room_display_name,
            "skill": self.skill.value,
            "nav_pose": (
                dict(self.nav_pose) if self.nav_pose is not None else None
            ),
            "reason": self.reason,
            "matching_artworks": list(self.matching_artworks),
            "rejected_rooms": list(self.rejected_rooms),
        }
        if self.session_id is not None:
            data["session_id"] = self.session_id
        return data

    @classmethod
    def invalid(
        cls,
        reason: str,
        request_id: str | None = None,
        session_id: str | None = None,
        intent: str | None = None,
    ) -> "ReasoningDecision":
        return cls(
            request_id=request_id,
            session_id=session_id,
            status="invalid_request",
            intent=intent,
            skill=Skill.ASK_CLARIFICATION,
            reason=reason,
        )


def _require_nonempty_string(value: Any, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContractValidationError(
            f"{name} must be a non-empty string."
        )


def _validate_optional_string(value: Any, name: str) -> None:
    if value is not None and not isinstance(value, str):
        raise ContractValidationError(
            f"{name} must be a string when provided."
        )
