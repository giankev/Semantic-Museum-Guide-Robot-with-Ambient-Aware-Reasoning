"""Pure helpers for the opt-in simulated ground-truth odometry adapter."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Sequence


ODOM_FRAME = "odom"
BASE_FRAME = "base_footprint"
POSE_COVARIANCE_DIAGONAL = (1e-4, 1e-4, 1e-3, 1e-3, 1e-3, 4e-4)
TWIST_COVARIANCE_DIAGONAL = (1e-3, 1e-3, 1e-3, 1e-3, 1e-3, 1e-3)


def _finite(values: Iterable[float]) -> bool:
    return all(math.isfinite(value) for value in values)


def normalize_angle(angle: float) -> float:
    return math.atan2(math.sin(angle), math.cos(angle))


def yaw_from_quaternion(quaternion: Sequence[float]) -> float:
    if len(quaternion) != 4 or not _finite(quaternion):
        raise ValueError("quaternion must contain four finite values")
    x, y, z, w = quaternion
    norm = math.sqrt(x * x + y * y + z * z + w * w)
    if norm < 1e-9:
        raise ValueError("quaternion norm is zero")
    x, y, z, w = (value / norm for value in quaternion)
    return math.atan2(2.0 * (w * z + x * y),
                      1.0 - 2.0 * (y * y + z * z))


def quaternion_from_yaw(yaw: float) -> tuple[float, float, float, float]:
    if not math.isfinite(yaw):
        raise ValueError("yaw must be finite")
    return (0.0, 0.0, math.sin(yaw / 2.0), math.cos(yaw / 2.0))


def validate_timestamp(sec: int, nanosec: int, previous_ns: int | None = None) -> int:
    if not isinstance(sec, int) or not isinstance(nanosec, int):
        raise ValueError("timestamp fields must be integers")
    if sec < 0 or not 0 <= nanosec < 1_000_000_000:
        raise ValueError("timestamp is outside ROS time bounds")
    timestamp_ns = sec * 1_000_000_000 + nanosec
    if previous_ns is not None and timestamp_ns <= previous_ns:
        raise ValueError("ground-truth timestamp is not strictly increasing")
    return timestamp_ns


def validate_sample(
    position: Sequence[float],
    quaternion: Sequence[float],
    linear_velocity: Sequence[float],
    angular_velocity: Sequence[float],
) -> None:
    for name, values, size in (
        ("position", position, 3),
        ("quaternion", quaternion, 4),
        ("linear velocity", linear_velocity, 3),
        ("angular velocity", angular_velocity, 3),
    ):
        if len(values) != size or not _finite(values):
            raise ValueError(f"{name} must contain {size} finite values")
    yaw_from_quaternion(quaternion)


def diagonal_covariance(diagonal: Sequence[float]) -> tuple[float, ...]:
    if len(diagonal) != 6 or not _finite(diagonal) or any(value < 0 for value in diagonal):
        raise ValueError("covariance diagonal must contain six finite nonnegative values")
    covariance = [0.0] * 36
    for index, value in zip((0, 7, 14, 21, 28, 35), diagonal):
        covariance[index] = value
    return tuple(covariance)


POSE_COVARIANCE = diagonal_covariance(POSE_COVARIANCE_DIAGONAL)
TWIST_COVARIANCE = diagonal_covariance(TWIST_COVARIANCE_DIAGONAL)


@dataclass(frozen=True)
class PlanarAlignment:
    """Align a world pose to an odom frame fixed at the first valid sample."""

    x: float
    y: float
    z: float
    yaw: float

    @classmethod
    def from_pose(
        cls, position: Sequence[float], quaternion: Sequence[float]
    ) -> "PlanarAlignment":
        validate_sample(position, quaternion, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
        return cls(position[0], position[1], position[2], yaw_from_quaternion(quaternion))

    def apply(
        self, position: Sequence[float], quaternion: Sequence[float]
    ) -> tuple[tuple[float, float, float], tuple[float, float, float, float]]:
        validate_sample(position, quaternion, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
        dx, dy = position[0] - self.x, position[1] - self.y
        cosine, sine = math.cos(self.yaw), math.sin(self.yaw)
        aligned_position = (
            cosine * dx + sine * dy,
            -sine * dx + cosine * dy,
            position[2] - self.z,
        )
        aligned_yaw = normalize_angle(yaw_from_quaternion(quaternion) - self.yaw)
        return aligned_position, quaternion_from_yaw(aligned_yaw)


def is_stale(now_ns: int, last_input_ns: int | None, timeout_ns: int) -> bool:
    if timeout_ns <= 0:
        raise ValueError("stale timeout must be positive")
    return last_input_ns is not None and now_ns - last_input_ns > timeout_ns

