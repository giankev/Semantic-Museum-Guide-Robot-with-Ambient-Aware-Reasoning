"""ROS-independent mapping and velocity estimates for simulated people."""

import math
from dataclasses import dataclass
from typing import Mapping


MODEL_TO_PUBLIC_ID = {
    "visitor_marker": "visitor_1",
    "guide_marker": "guide_1",
    "staff_marker": "staff_1",
}


@dataclass(frozen=True)
class PersonSample:
    identifier: str
    x: float
    y: float
    theta: float
    vx: float
    vy: float


PreviousPositions = dict[str, tuple[float, float, float]]


def people_from_model_positions(
    model_positions: Mapping[str, tuple[float, float, float]],
    *,
    timestamp: float,
    previous_positions: PreviousPositions,
) -> tuple[list[PersonSample], PreviousPositions]:
    """Map known models and estimate planar velocity by finite difference."""
    if not math.isfinite(timestamp):
        raise ValueError("People observation time must be finite.")

    samples = []
    next_positions = {}
    for model_name, identifier in MODEL_TO_PUBLIC_ID.items():
        position = model_positions.get(model_name)
        if position is None:
            continue

        x, y, theta = position
        if any(not math.isfinite(value) for value in position):
            continue

        vx = 0.0
        vy = 0.0
        previous = previous_positions.get(model_name)
        if previous is not None:
            previous_time, previous_x, previous_y = previous
            dt = timestamp - previous_time
            if math.isfinite(dt) and dt > 0.0:
                vx = (x - previous_x) / dt
                vy = (y - previous_y) / dt

        samples.append(
            PersonSample(
                identifier=identifier,
                x=x,
                y=y,
                theta=theta,
                vx=vx,
                vy=vy,
            )
        )
        next_positions[model_name] = (timestamp, x, y)

    return samples, next_positions
