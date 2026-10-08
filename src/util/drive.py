"""
Low-level driving helpers.

`limit_to_safe_range` and `steer_toward_target` are vendored verbatim from the
official RLBotPythonExample (MIT licensed). This is the PROVEN steering law:

    heading_error = atan2(local.y, local.x)   # local.y = rightward, local.x = ahead
    steer = clamp(heading_error * 5, -1, 1)    # no sign flip: target-on-right -> steer right

Verified numerically (target ahead -> 0, right -> +1, left -> -1, behind -> +1
i.e. turn around). The longitudinal control law (throttle/brake/reverse/arrival)
lives in navigation.py, not here.
"""

import math

from rlbot.utils.structures.game_data_struct import PlayerInfo

from util.orientation import Orientation, relative_location
from util.vec import Vec3


def limit_to_safe_range(value: float) -> float:
    """Clamp a controller value (throttle/steer/pitch/yaw/roll) to [-1, 1]."""
    if value < -1:
        return -1
    if value > 1:
        return 1
    return value


def steer_toward_target(car: PlayerInfo, target: Vec3) -> float:
    relative = relative_location(Vec3(car.physics.location), Orientation(car.physics.rotation), target)
    angle = math.atan2(relative.y, relative.x)
    return limit_to_safe_range(angle * 5)
