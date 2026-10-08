"""
Orientation + relative_location.

Vendored verbatim from the official RLBotPythonExample (MIT licensed). Builds the
car's forward/right/up basis from its Rotator and converts world points into the
car's local frame. Verified numerically: the basis is orthonormal, and for a
grounded car (pitch=roll=0, yaw=0) forward=+x, right=+y, up=+z.
"""

import math

from util.vec import Vec3


class Orientation:
    """Forward / right / up unit vectors derived from a Rotator (pitch, yaw, roll)."""

    def __init__(self, rotation):
        self.yaw = float(rotation.yaw)
        self.roll = float(rotation.roll)
        self.pitch = float(rotation.pitch)

        cr = math.cos(self.roll)
        sr = math.sin(self.roll)
        cp = math.cos(self.pitch)
        sp = math.sin(self.pitch)
        cy = math.cos(self.yaw)
        sy = math.sin(self.yaw)

        self.forward = Vec3(cp * cy, cp * sy, sp)
        self.right = Vec3(cy * sp * sr - cr * sy, sy * sp * sr + cr * cy, -cp * sr)
        self.up = Vec3(-cr * cy * sp - sr * sy, -cr * sy * sp + sr * cy, cp * cr)


def relative_location(center: Vec3, ori: Orientation, target: Vec3) -> Vec3:
    """
    `target` expressed in the local frame centered at `center` with orientation `ori`:

    * x: how far in FRONT
    * y: how far to the RIGHT
    * z: how far ABOVE
    """
    x = (target - center).dot(ori.forward)
    y = (target - center).dot(ori.right)
    z = (target - center).dot(ori.up)
    return Vec3(x, y, z)
