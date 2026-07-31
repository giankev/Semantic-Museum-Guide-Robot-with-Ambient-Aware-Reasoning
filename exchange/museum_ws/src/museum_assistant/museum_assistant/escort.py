"""Minimal ROS-independent state logic for one social escort task."""

import math
from enum import Enum


class EscortState(str, Enum):
    ESCORTING = "escorting"
    WAITING = "waiting"
    LOST = "lost"
    ARRIVED = "arrived"


class EscortSupervisor:
    """Track whether one visitor is still accompanying the robot."""

    def __init__(
        self,
        resume_distance: float = 2.0,
        wait_distance: float = 3.0,
        lost_distance: float = 8.0,
        arrival_distance: float = 2.5,
        wait_delay: float = 3.0,
        absence_timeout: float = 3.0,
    ):
        distances = (
            resume_distance,
            wait_distance,
            lost_distance,
            arrival_distance,
        )
        if any(not math.isfinite(value) or value <= 0.0 for value in distances):
            raise ValueError("Escort distances must be finite and positive.")
        if not resume_distance < wait_distance < lost_distance:
            raise ValueError(
                "Escort distances must satisfy "
                "resume_distance < wait_distance < lost_distance."
            )
        if (
            not math.isfinite(wait_delay)
            or wait_delay < 0.0
            or not math.isfinite(absence_timeout)
            or absence_timeout < 0.0
        ):
            raise ValueError("Escort timeouts must be finite and non-negative.")

        self.resume_distance = resume_distance
        self.wait_distance = wait_distance
        self.lost_distance = lost_distance
        self.arrival_distance = arrival_distance
        self.wait_delay = wait_delay
        self.absence_timeout = absence_timeout

        self.state: EscortState | None = None
        self.navigation_reached_destination = False
        self._lag_started_at: float | None = None
        self._absent_since: float | None = None
        self._last_present = False
        self._last_distance: float | None = None

    @property
    def distance_to_robot(self) -> float | None:
        if not self._last_present:
            return None
        return self._last_distance

    def start(self) -> EscortState:
        self.state = EscortState.ESCORTING
        self.navigation_reached_destination = False
        self._lag_started_at = None
        self._absent_since = None
        return self.state

    def stop(self) -> None:
        self.state = None
        self.navigation_reached_destination = False
        self._lag_started_at = None
        self._absent_since = None

    def observe(
        self,
        *,
        present: bool,
        distance_to_robot: float | None,
        now: float,
    ) -> EscortState | None:
        if not isinstance(present, bool):
            raise ValueError("present must be a boolean.")
        if not math.isfinite(now):
            raise ValueError("Observation time must be finite.")
        if present:
            if (
                isinstance(distance_to_robot, bool)
                or not isinstance(distance_to_robot, (int, float))
                or not math.isfinite(distance_to_robot)
                or distance_to_robot < 0.0
            ):
                raise ValueError(
                    "A present visitor requires a finite non-negative distance."
                )
            distance_to_robot = float(distance_to_robot)
        else:
            distance_to_robot = None

        self._last_present = present
        self._last_distance = distance_to_robot

        if self.state is None or self.state in {
            EscortState.LOST,
            EscortState.ARRIVED,
        }:
            return self.state

        if not present:
            self._lag_started_at = None
            if self._absent_since is None:
                self._absent_since = now
            if now - self._absent_since >= self.absence_timeout:
                self.state = EscortState.LOST
            return self.state

        self._absent_since = None
        if distance_to_robot >= self.lost_distance:
            self.state = EscortState.LOST
            self._lag_started_at = None
            return self.state

        if self.navigation_reached_destination:
            if distance_to_robot <= self.arrival_distance:
                self.state = EscortState.ARRIVED
            else:
                self.state = EscortState.WAITING
            return self.state

        if self.state is EscortState.ESCORTING:
            if distance_to_robot > self.wait_distance:
                if self._lag_started_at is None:
                    self._lag_started_at = now
                if now - self._lag_started_at >= self.wait_delay:
                    self.state = EscortState.WAITING
            else:
                self._lag_started_at = None
        elif (
            self.state is EscortState.WAITING
            and distance_to_robot <= self.resume_distance
        ):
            self.state = EscortState.ESCORTING
            self._lag_started_at = None

        return self.state

    def navigation_succeeded(self) -> EscortState | None:
        if self.state is None or self.state in {
            EscortState.LOST,
            EscortState.ARRIVED,
        }:
            return self.state

        self.navigation_reached_destination = True
        self._lag_started_at = None

        if not self._last_present or self._last_distance is None:
            self.state = EscortState.WAITING
        elif self._last_distance >= self.lost_distance:
            self.state = EscortState.LOST
        elif self._last_distance <= self.arrival_distance:
            self.state = EscortState.ARRIVED
        else:
            self.state = EscortState.WAITING

        return self.state
