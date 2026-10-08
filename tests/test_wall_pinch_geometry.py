"""
Software validation for the Kuxir side-wall pinch SETUP geometry.

Locks in the coordinate/sign conventions and the CAR -> BALL -> WALL relationship,
plus the full reject-with-reason validation layer (never emit a nonsense target).
These are software checks; the geometry is also physically inspected in-game via
the render-only GeomTest bot.
"""

import math

import pytest

import field
from util.vec import Vec3
from wall_pinch_geometry import (
    compute_wall_pinch_setup,
    PinchSetup,
    WALL_RIGHT,
    WALL_LEFT,
    NEAR_WALL_THRESHOLD,
    MAX_PINCH_HEIGHT,
    CORNER_Y_LIMIT,
    MAX_TARGET_DIST,
    APPROACH_STANDOFF,
)

SQRT2_INV = 1.0 / math.sqrt(2.0)


# --- Worked example (right wall, ball rolling +y, team 0) ---------------------

def test_worked_example_right_wall():
    ball = Vec3(3900, 1000, 93)
    vel = Vec3(0, 800, 0)              # rolling +y along the wall
    s = compute_wall_pinch_setup(ball, vel, team=0)

    assert s.viable and s.reject_reason == ""
    assert s.wall == WALL_RIGHT
    assert (s.wall_normal.x, s.wall_normal.y, s.wall_normal.z) == (-1, 0, 0)   # inward from right wall
    assert (s.wall_tangent.x, s.wall_tangent.y, s.wall_tangent.z) == (0, 1, 0)  # pinch +y (ball's dir)

    # approach direction = normalize(-normal + tangent) = normalize((1,1,0))
    assert s.approach_direction.x == pytest.approx(SQRT2_INV, abs=1e-6)
    assert s.approach_direction.y == pytest.approx(SQRT2_INV, abs=1e-6)
    assert s.approach_direction.z == pytest.approx(0.0, abs=1e-6)

    # contact on the ball surface facing the car
    assert s.contact_point.x == pytest.approx(3900 - SQRT2_INV * field.BALL_RADIUS, abs=1e-3)
    assert s.contact_point.y == pytest.approx(1000 - SQRT2_INV * field.BALL_RADIUS, abs=1e-3)

    # setup point interior + behind, at car height
    assert s.approach_point.z == pytest.approx(field.CAR_REST_Z)
    assert s.target_distance == pytest.approx(field.BALL_RADIUS + APPROACH_STANDOFF, abs=1e-3)

    # expected exit along the wall, +y
    assert (s.expected_pinch_direction.x, s.expected_pinch_direction.y) == (0, 1)


# --- CAR -> BALL -> WALL invariant -------------------------------------------

def test_car_ball_wall_ordering_right():
    s = compute_wall_pinch_setup(Vec3(3800, 500, 93), Vec3(0, 600, 0), team=0)
    assert s.viable
    # interior-most is the car setup point, then the ball, then the wall at +4096
    assert s.approach_point.x < s.ball_pos.x < field.SIDE_WALL_X


def test_car_ball_wall_ordering_left():
    s = compute_wall_pinch_setup(Vec3(-3800, 500, 93), Vec3(0, -600, 0), team=1)
    assert s.viable
    assert s.wall == WALL_LEFT
    assert (s.wall_normal.x, s.wall_normal.y, s.wall_normal.z) == (1, 0, 0)   # inward from left wall
    assert (s.wall_tangent.x, s.wall_tangent.y) == (0, -1)                    # ball rolling -y
    # interior-most is the car setup point, then the ball, then the wall at -4096
    assert s.approach_point.x > s.ball_pos.x > -field.SIDE_WALL_X


# --- Tangent (pinch direction) selection --------------------------------------

def test_tangent_follows_ball_velocity_when_fast():
    fast_plus = compute_wall_pinch_setup(Vec3(3900, 0, 93), Vec3(0, 600, 0), team=1)
    assert fast_plus.wall_tangent.y == 1    # follows +y velocity, even for team 1
    fast_minus = compute_wall_pinch_setup(Vec3(3900, 0, 93), Vec3(0, -600, 0), team=0)
    assert fast_minus.wall_tangent.y == -1  # follows -y velocity, even for team 0


def test_tangent_defaults_to_attack_goal_when_slow():
    # Ball nearly still -> pinch toward this team's attack goal.
    t0 = compute_wall_pinch_setup(Vec3(3900, 0, 93), Vec3(0, 10, 0), team=0)
    assert t0.wall_tangent.y == 1           # team 0 attacks +y
    t1 = compute_wall_pinch_setup(Vec3(3900, 0, 93), Vec3(0, 10, 0), team=1)
    assert t1.wall_tangent.y == -1          # team 1 attacks -y


# --- Validation / rejection reasons -------------------------------------------

def test_reject_ball_not_near_wall():
    s = compute_wall_pinch_setup(Vec3(0, 0, 93), Vec3(0, 0, 0), team=0)   # midfield
    assert not s.viable
    assert s.reject_reason == "ball_not_near_wall"


def test_reject_ball_too_high():
    s = compute_wall_pinch_setup(Vec3(3900, 1000, MAX_PINCH_HEIGHT + 50), Vec3(0, 400, 0), team=0)
    assert not s.viable
    assert s.reject_reason == "ball_too_high"


def test_reject_ball_near_corner():
    s = compute_wall_pinch_setup(Vec3(3900, CORNER_Y_LIMIT + 100, 93), Vec3(0, 300, 0), team=0)
    assert not s.viable
    assert s.reject_reason == "ball_near_corner"


def test_reject_ball_leaving_wall():
    # Ball near the right wall but rushing back toward midfield (-x) -> stale setup.
    leaving = compute_wall_pinch_setup(Vec3(3950, 500, 93), Vec3(-900, 0, 0), team=0)
    assert not leaving.viable and leaving.reject_reason == "ball_leaving_wall"
    # Rolling ALONG the wall (tangential) is fine.
    along = compute_wall_pinch_setup(Vec3(3950, 500, 93), Vec3(0, 900, 0), team=0)
    assert along.viable
    # Drifting slowly off the wall (below threshold) is still viable.
    slow = compute_wall_pinch_setup(Vec3(3950, 500, 93), Vec3(-500, 0, 0), team=0)
    assert slow.viable
    # Moving INTO the wall is not "leaving".
    into = compute_wall_pinch_setup(Vec3(3950, 500, 93), Vec3(500, 0, 0), team=0)
    assert into.viable


def test_reject_non_finite():
    s = compute_wall_pinch_setup(Vec3(float("nan"), 0, 93), Vec3(0, 0, 0), team=0)
    assert not s.viable
    assert s.reject_reason == "non_finite_input"


def test_viable_near_wall_band():
    # Just inside the near-wall threshold -> viable; just outside -> rejected.
    gap_ok_x = field.SIDE_WALL_X - field.BALL_RADIUS - (NEAR_WALL_THRESHOLD - 50)
    ok = compute_wall_pinch_setup(Vec3(gap_ok_x, 500, 93), Vec3(0, 400, 0), team=0)
    assert ok.viable
    gap_bad_x = field.SIDE_WALL_X - field.BALL_RADIUS - (NEAR_WALL_THRESHOLD + 50)
    bad = compute_wall_pinch_setup(Vec3(gap_bad_x, 500, 93), Vec3(0, 400, 0), team=0)
    assert not bad.viable and bad.reject_reason == "ball_not_near_wall"


# --- No nonsense targets / finiteness -----------------------------------------

def test_viable_setups_are_sane_and_finite():
    for bx in (3800, 3950, -3800, -3950):
        for by in (-3000, 0, 2500):
            s = compute_wall_pinch_setup(Vec3(bx, by, 93), Vec3(0, 500, 0), team=0)
            if not s.viable:
                continue
            for v in (s.wall_normal, s.wall_tangent, s.contact_point, s.approach_point,
                      s.approach_direction, s.expected_pinch_direction):
                assert math.isfinite(v.x) and math.isfinite(v.y) and math.isfinite(v.z)
            # target must be near the ball and well inside the field (no 5825-uu bugs)
            assert s.target_distance <= MAX_TARGET_DIST
            assert abs(s.approach_point.x) < field.SIDE_WALL_X
            assert abs(s.approach_point.y) < field.BACK_WALL_Y
            # unit vectors are unit length
            assert s.approach_direction.length() == pytest.approx(1.0, abs=1e-6)
            assert s.wall_normal.length() == pytest.approx(1.0, abs=1e-6)
            assert s.expected_pinch_direction.length() == pytest.approx(1.0, abs=1e-6)


def test_both_teams_get_valid_setups():
    for team in (0, 1):
        s = compute_wall_pinch_setup(Vec3(3900, 800, 93), Vec3(0, 0, 0), team=team)
        assert s.viable
        assert s.wall == WALL_RIGHT
