"""
Software validation for the generic navigation controller (navigation.drive_to_target).

Focus areas (the mission's navigation rules):
  * correct steering sign toward the target (frame-relative),
  * NO BLIND REVERSE: a stationary car with the target behind turns around under
    forward throttle; throttle<0 appears only as braking against forward motion,
  * clean arrival: slow to a stop within the arrival radius and hold,
  * desired-speed-from-stopping-distance behaves (accelerate / coast / brake),
  * controls always finite and in range,
  * a 1-D longitudinal simulation actually converges and stops (no overshoot blow-up).

These are software checks. Physical arrival quality is confirmed in-game (NavTest).
"""

import math

import pytest
from rlbot.agents.base_agent import SimpleControllerState

import navigation
from navigation import (
    drive_to_target,
    MAX_DRIVE_SPEED,
    BRAKE_DECEL,
    DEFAULT_ARRIVAL_RADIUS,
    HOLD_SPEED,
    TURN_SPEED_CAP,
    NAV_DRIVE,
    NAV_TURN,
    NAV_BRAKE,
    NAV_ARRIVED,
)
from util.vec import Vec3
from fake_packet import make_packet


def car_with(location=(0, 0, 17), velocity=(0, 0, 0), rotation=(0, 0, 0)):
    """A PlayerInfo (real packet car) with the given ground state. rotation=(pitch,yaw,roll)."""
    return make_packet(car_location=location, car_velocity=velocity, car_rotation=rotation).game_cars[0]


# --- API / ranges -------------------------------------------------------------

def test_returns_controls_and_telemetry():
    controls, tele = drive_to_target(car_with(), Vec3(2000, 0, 17))
    assert isinstance(controls, SimpleControllerState)
    assert isinstance(tele, dict)
    for key in ("state", "target_distance", "heading_error", "velocity_toward_target",
                "desired_speed", "throttle", "steer", "car_forward"):
        assert key in tele


def test_controls_in_range_over_sweep():
    for xy in [(2000, 0), (0, 2000), (-2000, 0), (0, -2000), (1500, -1500), (-30, 40)]:
        for yaw in [0.0, 1.0, -2.0, math.pi]:
            for spd in [0.0, 500.0, 1400.0]:
                car = car_with(velocity=(spd, 0, 0), rotation=(0, yaw, 0))
                controls, _ = drive_to_target(car, Vec3(xy[0], xy[1], 17))
                for v in (controls.throttle, controls.steer):
                    assert -1.0 <= v <= 1.0 and math.isfinite(v)
                assert controls.handbrake is False
                assert controls.boost is False


# --- Steering sign ------------------------------------------------------------

def test_steer_toward_side_target():
    car = car_with(rotation=(0, 0, 0))  # facing +x
    c_right, _ = drive_to_target(car, Vec3(1000, 1000, 17))
    c_left, _ = drive_to_target(car, Vec3(1000, -1000, 17))
    assert c_right.steer > 0     # target forward-right -> steer right
    assert c_left.steer < 0      # target forward-left -> steer left


# --- THE anti-blind-reverse invariant -----------------------------------------

def test_stationary_target_behind_turns_around_never_reverses():
    # Car facing +x, stopped. Target is directly BEHIND at -x.
    car = car_with(location=(0, 0, 17), velocity=(0, 0, 0), rotation=(0, 0, 0))
    controls, tele = drive_to_target(car, Vec3(-2000, 0, 17))
    assert controls.throttle >= 0.0          # must NOT reverse just because target is behind
    assert controls.throttle == pytest.approx(1.0)   # accelerate forward to pivot around
    assert abs(controls.steer) == pytest.approx(1.0)  # hard steer to turn around
    assert tele["state"] == NAV_TURN


def test_slow_target_behind_drives_forward_to_turn():
    # Moving slowly (below the turn-speed cap), target behind -> accelerate forward & turn.
    car = car_with(velocity=(200, 0, 0), rotation=(0, 0, 0))
    controls, tele = drive_to_target(car, Vec3(-3000, 0, 17))
    assert controls.throttle == pytest.approx(1.0)
    assert tele["state"] == NAV_TURN


# --- Driving / desired-speed law ----------------------------------------------

def test_far_target_accelerates():
    car = car_with(velocity=(0, 0, 0), rotation=(0, 0, 0))
    controls, tele = drive_to_target(car, Vec3(3000, 0, 17))
    assert controls.throttle == pytest.approx(1.0)
    assert tele["state"] == NAV_DRIVE
    assert tele["desired_speed"] == pytest.approx(MAX_DRIVE_SPEED)  # capped when far


def test_overspeed_toward_near_target_brakes():
    # Target ahead but close enough that current speed exceeds a clean-stop speed -> brake.
    car = car_with(velocity=(1400, 0, 0), rotation=(0, 0, 0))
    controls, tele = drive_to_target(car, Vec3(300, 0, 17))  # remaining ~180
    assert controls.throttle == pytest.approx(-1.0)   # braking (deceleration), not reversing
    assert tele["state"] == NAV_DRIVE
    assert tele["forward_speed"] > tele["desired_speed"]


def test_coast_when_at_desired_speed():
    car = car_with(velocity=(1400, 0, 0), rotation=(0, 0, 0))
    controls, _ = drive_to_target(car, Vec3(5000, 0, 17))  # desired capped at 1410, err ~10
    assert controls.throttle == pytest.approx(0.0)


# --- Arrival ------------------------------------------------------------------

def test_arrival_hold_when_slow_and_close():
    car = car_with(location=(0, 0, 17), velocity=(0, 0, 0), rotation=(0, 0, 0))
    controls, tele = drive_to_target(car, Vec3(50, 0, 17), arrival_radius=120)
    assert controls.throttle == pytest.approx(0.0)
    assert controls.steer == pytest.approx(0.0)
    assert tele["state"] == NAV_ARRIVED


def test_arrival_brakes_when_still_moving():
    car = car_with(location=(0, 0, 17), velocity=(900, 0, 0), rotation=(0, 0, 0))
    controls, tele = drive_to_target(car, Vec3(50, 0, 17), arrival_radius=120)
    assert controls.throttle == pytest.approx(-1.0)
    assert tele["state"] == NAV_BRAKE


def test_desired_speed_drops_to_zero_at_arrival_edge():
    car = car_with(rotation=(0, 0, 0))
    _, tele = drive_to_target(car, Vec3(121, 0, 17), arrival_radius=120)  # remaining ~1
    assert tele["desired_speed"] < 90.0  # sqrt(2*3500*1) ~ 84 -> small, nearly stopped


# --- Measured quantities ------------------------------------------------------

def test_velocity_toward_target_sign():
    toward = car_with(velocity=(500, 0, 0), rotation=(0, 0, 0))
    _, t1 = drive_to_target(toward, Vec3(2000, 0, 17))
    assert t1["velocity_toward_target"] == pytest.approx(500, abs=1)
    away = car_with(velocity=(500, 0, 0), rotation=(0, 0, 0))
    _, t2 = drive_to_target(away, Vec3(-2000, 0, 17))
    assert t2["velocity_toward_target"] == pytest.approx(-500, abs=1)


def test_target_distance_is_truthful():
    car = car_with(location=(100, 200, 17))
    _, tele = drive_to_target(car, Vec3(1100, 200, 17))
    assert tele["target_distance"] == pytest.approx(1000, abs=1)


# --- Frame-relative (team-agnostic) -------------------------------------------

def test_navigation_is_frame_relative():
    # Car facing -y (yaw=-90). Target straight ahead of it (further -y) -> go straight.
    car = car_with(location=(0, 0, 17), velocity=(0, 0, 0), rotation=(0, -math.pi / 2, 0))
    controls, tele = drive_to_target(car, Vec3(0, -3000, 17))
    assert abs(controls.steer) < 0.05           # essentially straight ahead
    assert controls.throttle == pytest.approx(1.0)
    assert tele["state"] == NAV_DRIVE


# --- Longitudinal convergence simulation --------------------------------------

def test_longitudinal_convergence_and_stop():
    """
    Crude 1-D forward point-mass model (NOT real RL physics) to confirm the control
    law converges: the car should accelerate, cruise, brake, and STOP within the
    arrival radius of a target straight ahead -- without overshooting past it or
    reversing.
    """
    dt = 1.0 / 120.0
    x = 0.0
    vx = 0.0
    target_x = 3000.0
    arrival = DEFAULT_ARRIVAL_RADIUS
    last_state = None
    max_x = 0.0

    for _ in range(2400):
        car = car_with(location=(x, 0, 17), velocity=(vx, 0, 0), rotation=(0, 0, 0))
        controls, tele = drive_to_target(car, Vec3(target_x, 0, 17), arrival_radius=arrival)
        last_state = tele["state"]
        thr = controls.throttle
        if thr > 0:
            a = 1600.0 * max(0.0, 1.0 - max(0.0, vx) / MAX_DRIVE_SPEED)  # crude accel curve
        elif thr < 0:
            a = -BRAKE_DECEL if vx > 0 else 0.0                          # brake only while moving fwd
        else:
            a = -525.0 if vx > 0 else 0.0                                # coast decel
        vx = max(0.0, vx + a * dt)   # forward-only model: never goes negative
        x += vx * dt
        max_x = max(max_x, x)

    dist_final = target_x - x
    assert 0.0 <= dist_final <= arrival + 5.0        # stopped within the arrival radius, short of target
    assert vx < HOLD_SPEED + 10.0                     # essentially stopped
    assert max_x <= target_x + 5.0                    # never overshot past the target
    assert last_state in (NAV_ARRIVED, NAV_BRAKE)
