"""Small ROS-independent motion logic for the scripted escort visitor."""

import math
from enum import Enum


class ScriptedVisitorPhase(str, Enum):
    IDLE = "idle"
    FOLLOWING = "following"
    LAGGING = "lagging"
    CATCHING_UP = "catching_up"
    DONE = "done"


def limited_follow_step(
    visitor_position: tuple[float, float],
    target_position: tuple[float, float],
    *,
    follow_distance: float,
    speed: float,
    dt: float,
) -> tuple[float, float]:
    """Move toward a target without entering the configured follow radius."""
    values = (*visitor_position, *target_position, follow_distance, speed, dt)
    if any(not math.isfinite(value) for value in values):
        raise ValueError("Motion inputs must be finite.")
    if follow_distance < 0.0 or speed < 0.0 or dt < 0.0:
        raise ValueError(
            "Motion distances, speed, and time must be non-negative."
        )

    dx = target_position[0] - visitor_position[0]
    dy = target_position[1] - visitor_position[1]
    distance = math.hypot(dx, dy)
    travel = min(max(0.0, distance - follow_distance), speed * dt)
    if travel == 0.0 or distance == 0.0:
        return visitor_position

    scale = travel / distance
    return (
        visitor_position[0] + dx * scale,
        visitor_position[1] + dy * scale,
    )


class LagRecoverScenario:
    """Create one lag and recovery while following the robot."""

    def __init__(
        self,
        *,
        follow_distance: float = 1.5,
        follow_speed: float = 0.5,
        catchup_speed: float = 0.8,
        lag_after_seconds: float = 5.0,
    ):
        values = (
            follow_distance,
            follow_speed,
            catchup_speed,
            lag_after_seconds,
        )
        if any(not math.isfinite(value) for value in values):
            raise ValueError("Scripted visitor parameters must be finite.")
        if (
            follow_distance <= 0.0
            or follow_speed <= 0.0
            or catchup_speed <= 0.0
            or lag_after_seconds < 0.0
        ):
            raise ValueError(
                "Distances and speeds must be positive; lag time may be zero."
            )

        self.follow_distance = follow_distance
        self.follow_speed = follow_speed
        self.catchup_speed = catchup_speed
        self.lag_after_seconds = lag_after_seconds
        self.phase = ScriptedVisitorPhase.IDLE
        self._started_at: float | None = None
        self._lag_completed = False

    def reset(self) -> None:
        self.phase = ScriptedVisitorPhase.IDLE
        self._started_at = None
        self._lag_completed = False

    def handle_escort_state(self, state: str, *, now: float) -> None:
        """Select motion from public escort state without copying its logic."""
        if not math.isfinite(now):
            raise ValueError("Escort state time must be finite.")

        if state == "escorting":
            if self.phase is ScriptedVisitorPhase.IDLE:
                self.phase = ScriptedVisitorPhase.FOLLOWING
                self._started_at = now
            elif self.phase is ScriptedVisitorPhase.CATCHING_UP:
                self.phase = ScriptedVisitorPhase.FOLLOWING
        elif state == "waiting" and self._started_at is not None:
            self.phase = ScriptedVisitorPhase.CATCHING_UP
            self._lag_completed = True
        elif state in {"arrived", "lost"}:
            self.phase = ScriptedVisitorPhase.DONE

    def step(
        self,
        visitor_position: tuple[float, float],
        robot_position: tuple[float, float],
        *,
        now: float,
        dt: float,
    ) -> tuple[float, float]:
        if not math.isfinite(now):
            raise ValueError("Motion time must be finite.")

        if self.phase is ScriptedVisitorPhase.FOLLOWING:
            if (
                not self._lag_completed
                and self._started_at is not None
                and now - self._started_at >= self.lag_after_seconds
            ):
                self.phase = ScriptedVisitorPhase.LAGGING
                return visitor_position
            speed = self.follow_speed
        elif self.phase is ScriptedVisitorPhase.CATCHING_UP:
            speed = self.catchup_speed
        else:
            return visitor_position

        return limited_follow_step(
            visitor_position,
            robot_position,
            follow_distance=self.follow_distance,
            speed=speed,
            dt=dt,
        )
