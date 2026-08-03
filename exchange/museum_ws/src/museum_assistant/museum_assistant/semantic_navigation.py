"""Small ROS-independent checks for executable reasoning decisions."""

import math
from typing import Any


def navigation_pose_from_decision(
    decision: Any,
) -> tuple[float, float, float] | None:
    if not isinstance(decision, dict):
        return None
    if decision.get("status") != "success":
        return None
    if decision.get("skill") != "navigate_to":
        return None
    if decision.get("intent") != "recommend_and_prepare_navigation":
        return None

    nav_pose = decision.get("nav_pose")
    if not isinstance(nav_pose, dict):
        return None

    values = []
    for field in ("x", "y", "yaw"):
        value = nav_pose.get(field)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            return None
        values.append(float(value))

    return values[0], values[1], values[2]
