"""
Vec3 -- a tiny 3D vector helper.

Vendored verbatim from the official RLBotPythonExample (MIT licensed), which is
the project's designated API/utility reference. Reused rather than reinvented so
we inherit its proven, battle-tested behavior. The in-game axes are left-handed
(see https://github.com/RLBot/RLBot/wiki/Useful-Game-Values).

Cast flatbuffer/ctypes vectors from the packet like: `Vec3(car.physics.location)`.
"""

import math
from typing import Union

from rlbot.utils.structures.game_data_struct import Vector3


class Vec3:
    __slots__ = ['x', 'y', 'z']

    def __init__(self, x: Union[float, 'Vec3', 'Vector3'] = 0, y: float = 0, z: float = 0):
        """Create a Vec3. If x is a vector-like object (has .x), copy it and ignore y/z."""
        if hasattr(x, 'x'):
            self.x = float(x.x)
            self.y = float(x.y) if hasattr(x, 'y') else 0
            self.z = float(x.z) if hasattr(x, 'z') else 0
        else:
            self.x = float(x)
            self.y = float(y)
            self.z = float(z)

    def __getitem__(self, item: int):
        return (self.x, self.y, self.z)[item]

    def __add__(self, other: 'Vec3') -> 'Vec3':
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: 'Vec3') -> 'Vec3':
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __neg__(self):
        return Vec3(-self.x, -self.y, -self.z)

    def __mul__(self, scale: float) -> 'Vec3':
        return Vec3(self.x * scale, self.y * scale, self.z * scale)

    def __rmul__(self, scale):
        return self * scale

    def __truediv__(self, scale: float) -> 'Vec3':
        scale = 1 / float(scale)
        return self * scale

    def __str__(self):
        return f"Vec3({self.x:.2f}, {self.y:.2f}, {self.z:.2f})"

    def __repr__(self):
        return self.__str__()

    def flat(self):
        """Returns a copy projected onto the ground plane (z=0)."""
        return Vec3(self.x, self.y, 0)

    def length(self):
        """Length / magnitude / norm."""
        return math.sqrt(self.x ** 2 + self.y ** 2 + self.z ** 2)

    def dist(self, other: 'Vec3') -> float:
        return (self - other).length()

    def normalized(self):
        """Same direction, length 1."""
        return self / self.length()

    def rescale(self, new_len: float) -> 'Vec3':
        """Same direction, given length."""
        return new_len * self.normalized()

    def dot(self, other: 'Vec3') -> float:
        return self.x * other.x + self.y * other.y + self.z * other.z

    def cross(self, other: 'Vec3') -> 'Vec3':
        return Vec3(
            self.y * other.z - self.z * other.y,
            self.z * other.x - self.x * other.z,
            self.x * other.y - self.y * other.x,
        )

    def ang_to(self, ideal: 'Vec3') -> float:
        """Angle to another vector, in [0, pi]."""
        cos_ang = self.dot(ideal) / (self.length() * ideal.length())
        return math.acos(cos_ang)
