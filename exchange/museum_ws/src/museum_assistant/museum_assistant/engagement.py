"""Deterministic visual, spatial, motion, and dwell-time fusion."""

from dataclasses import dataclass
from enum import Enum
import math


class EngagementState(str, Enum):
    NO_PERSON = "NO_PERSON"
    PASSING = "PASSING"
    POTENTIAL_INTERACTION = "POTENTIAL_INTERACTION"
    ENGAGED = "ENGAGED"
    DISENGAGING = "DISENGAGING"


@dataclass(frozen=True)
class EngagementResult:
    state: EngagementState
    near_visible_person: bool
    radial_speed_mps: float | None
    dwell_s: float


def frontal_lidar_candidate(ranges, angle_min, angle_increment, range_min,
                            range_max, half_angle=math.radians(35.0)):
    candidates = []
    for index, value in enumerate(ranges):
        angle = angle_min + index * angle_increment
        valid = math.isfinite(value) and max(0.35, range_min) <= value <= range_max
        if valid and abs(angle) <= half_angle:
            candidates.append((float(value), angle))
    return min(candidates, default=(None, None))


class EngagementModel:
    def __init__(self, max_distance_m=2.0, max_speed_mps=0.25,
                 potential_dwell_s=1.0, engaged_dwell_s=2.5,
                 disengage_s=1.5):
        self.max_distance_m = max_distance_m
        self.max_speed = max_speed_mps
        self.potential_dwell_s = potential_dwell_s
        self.engaged_dwell_s = engaged_dwell_s
        self.disengage_s = disengage_s
        self.state = EngagementState.NO_PERSON
        self._near_since = self._lost_since = self._previous_lidar = None

    def update(self, *, now, visual_person, central, distance_m):
        speed = self._radial_speed(distance_m, now)
        near = (visual_person and central and distance_m is not None
                and distance_m <= self.max_distance_m)
        if near:
            self._lost_since = None
            self._near_since = now if self._near_since is None else self._near_since
            dwell = max(0.0, now - self._near_since)
            stationary = speed is not None and abs(speed) <= self.max_speed
            if dwell >= self.engaged_dwell_s and stationary:
                self.state = EngagementState.ENGAGED
            elif dwell >= self.potential_dwell_s:
                self.state = EngagementState.POTENTIAL_INTERACTION
            else:
                self.state = EngagementState.PASSING
        elif self.state in {EngagementState.ENGAGED, EngagementState.DISENGAGING}:
            self._lost_since = now if self._lost_since is None else self._lost_since
            dwell = max(0.0, now - (self._near_since or now))
            if now - self._lost_since >= self.disengage_s:
                self.state = EngagementState.NO_PERSON
                self._near_since = self._lost_since = None
            else:
                self.state = EngagementState.DISENGAGING
        else:
            self._near_since, dwell = None, 0.0
            self.state = (EngagementState.PASSING if visual_person
                          else EngagementState.NO_PERSON)
        return EngagementResult(self.state, near, speed, dwell)

    def _radial_speed(self, distance, now):
        speed = None
        if distance is not None and self._previous_lidar is not None:
            old_distance, old_time = self._previous_lidar
            if now > old_time:
                speed = (distance - old_distance) / (now - old_time)
        if distance is not None:
            self._previous_lidar = distance, now
        return speed
