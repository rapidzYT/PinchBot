"""
Software validation for the vendored, proven utilities (Vec3, Orientation,
relative_location, steer_toward_target). These lock in the coordinate / sign
conventions the navigation and (later) pinch geometry depend on.
"""

import math

import pytest

from util.vec import Vec3
from util.orientation import Orientation, relative_location
from util.drive import steer_toward_target, limit_to_safe_range
from fake_packet import make_packet


# --- Vec3 ---------------------------------------------------------------------

def test_vec3_basic_ops():
    a = Vec3(1, 2, 3)
    b = Vec3(4, 5, 6)
    assert (a + b)[0] == 5 and (a + b).y == 7 and (a + b).z == 9
    assert (b - a).x == 3
    assert a.dot(b) == pytest.approx(1 * 4 + 2 * 5 + 3 * 6)
    assert Vec3(3, 4, 0).length() == pytest.approx(5.0)
    assert Vec3(3, 4, 0).normalized().length() == pytest.approx(1.0)
    assert Vec3(0, 0, 5).flat().z == 0
    assert a.dist(b) == pytest.approx((b - a).length())
    assert Vec3(1, 0, 0).rescale(7).length() == pytest.approx(7.0)


def test_vec3_cross_and_angle():
    assert Vec3(1, 0, 0).cross(Vec3(0, 1, 0)).z == pytest.approx(1.0)
    assert Vec3(1, 0, 0).ang_to(Vec3(0, 1, 0)) == pytest.approx(math.pi / 2)


def test_vec3_copy_from_packet_vector():
    # Vec3 should wrap the ctypes Vector3 from a real packet.
    loc = make_packet(car_location=(10, 20, 30)).game_cars[0].physics.location
    v = Vec3(loc)
    assert (v.x, v.y, v.z) == (10, 20, 30)


# --- Orientation basis --------------------------------------------------------

@pytest.mark.parametrize("pitch,yaw,roll", [
    (0, 0, 0), (0, math.pi / 2, 0), (0.3, 1.1, -0.4), (-0.8, -2.3, 0.9),
])
def test_orientation_is_orthonormal(pitch, yaw, roll):
    class R:
        pass
    r = R(); r.pitch, r.yaw, r.roll = pitch, yaw, roll
    o = Orientation(r)
    assert o.forward.length() == pytest.approx(1.0)
    assert o.right.length() == pytest.approx(1.0)
    assert o.up.length() == pytest.approx(1.0)
    assert o.forward.dot(o.right) == pytest.approx(0.0, abs=1e-9)
    assert o.forward.dot(o.up) == pytest.approx(0.0, abs=1e-9)
    assert o.right.dot(o.up) == pytest.approx(0.0, abs=1e-9)


def test_grounded_orientation_axes():
    class R:
        pass
    r = R(); r.pitch, r.yaw, r.roll = 0.0, 0.0, 0.0
    o = Orientation(r)
    assert (round(o.forward.x), round(o.forward.y), round(o.forward.z)) == (1, 0, 0)
    assert (round(o.right.x), round(o.right.y), round(o.right.z)) == (0, 1, 0)
    assert (round(o.up.x), round(o.up.y), round(o.up.z)) == (0, 0, 1)
    # yaw = +90deg -> forward points +y
    r.yaw = math.pi / 2
    o2 = Orientation(r)
    assert o2.forward.y == pytest.approx(1.0)
    assert o2.forward.x == pytest.approx(0.0, abs=1e-9)


# --- relative_location --------------------------------------------------------

def test_relative_location_frame():
    class R:
        pass
    r = R(); r.pitch, r.yaw, r.roll = 0.0, 0.0, 0.0  # facing +x
    o = Orientation(r)
    c = Vec3(0, 0, 17)
    assert relative_location(c, o, Vec3(1000, 0, 17)).x == pytest.approx(1000)   # ahead
    assert relative_location(c, o, Vec3(0, 1000, 17)).y == pytest.approx(1000)   # right (+y)
    assert relative_location(c, o, Vec3(0, -1000, 17)).y == pytest.approx(-1000)  # left (-y)
    assert relative_location(c, o, Vec3(-1000, 0, 17)).x == pytest.approx(-1000)  # behind


# --- Steering law -------------------------------------------------------------

def test_limit_to_safe_range():
    assert limit_to_safe_range(0.45) == pytest.approx(0.45)
    assert limit_to_safe_range(-5.6) == -1
    assert limit_to_safe_range(5.6) == 1


def test_steer_signs_facing_plus_x():
    car = make_packet(car_location=(0, 0, 17), car_rotation=(0, 0, 0)).game_cars[0]
    assert steer_toward_target(car, Vec3(1000, 0, 17)) == pytest.approx(0.0)   # ahead
    assert steer_toward_target(car, Vec3(0, 1000, 17)) == pytest.approx(1.0)   # right
    assert steer_toward_target(car, Vec3(0, -1000, 17)) == pytest.approx(-1.0)  # left
    # directly behind -> turn around (hard steer, not zero)
    assert abs(steer_toward_target(car, Vec3(-1000, 0, 17))) == pytest.approx(1.0)


def test_steer_is_frame_relative_not_world():
    # A car facing -y (yaw=-90deg). RLBot axes are LEFT-handed, so by the proven
    # Orientation formula this car's "right" vector is +x (not -x). Steering must be
    # relative to the car's own frame, so:
    car = make_packet(car_location=(0, 0, 17), car_rotation=(0, -math.pi / 2, 0)).game_cars[0]
    # target at +x is to the car's right -> steer right (+).
    assert steer_toward_target(car, Vec3(1000, 0, 17)) > 0.5
    # target at -x is to the car's left -> steer left (-).
    assert steer_toward_target(car, Vec3(-1000, 0, 17)) < -0.5
