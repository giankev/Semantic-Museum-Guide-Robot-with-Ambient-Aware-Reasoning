"""ROS-independent field mapping for the social-layer compatibility bridge."""

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class CompatibilityPerson:
    name: str
    x: float
    y: float
    vx: float
    vy: float
    reliability: float = 1.0


@dataclass(frozen=True)
class CompatibilityPeople:
    frame_id: str
    stamp_sec: int
    stamp_nanosec: int
    people: tuple[CompatibilityPerson, ...]


def compatibility_people_fields(
    *,
    frame_id: str,
    stamp_sec: int,
    stamp_nanosec: int,
    pedestrians: Iterable[tuple[str, float, float, float, float]],
) -> CompatibilityPeople:
    """Map only the fields required by the third-party people message."""
    people = tuple(
        CompatibilityPerson(
            name=identifier,
            x=x,
            y=y,
            vx=vx,
            vy=vy,
        )
        for identifier, x, y, vx, vy in pedestrians
    )
    return CompatibilityPeople(
        frame_id=frame_id,
        stamp_sec=stamp_sec,
        stamp_nanosec=stamp_nanosec,
        people=people,
    )
