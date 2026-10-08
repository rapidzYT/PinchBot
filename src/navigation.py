"""
Generic ground navigation (Checkpoint 1).

A single pure function, `drive_to_target`, that steers a car across the ground
to a world point and brings it to a clean stop there. It is deliberately
target-agnostic: it knows nothing about the ball or pinches -- callers pass a
target point and an arrival radius. Later stages reuse it to reach setup points.

Design guarantees (these are the mission's hard navigation rules):

  * STEERING uses the proven RLBot example convention:
        heading_error = atan2(local.y, local.x)   # local.y = rightward, local.x = ahead
        steer = clamp(heading_error * 5, -1, 1)    # target on the right -> steer right.

  * NO BLIND REVERSE. We never command throttle < 0 merely because the target is
    behind us. throttle < 0 is produced ONLY as BRAKING against the car's current
    forward motion, justified by a measured speed error. A target behind the car
    is reached by turning around under FORWARD throttle (with a capped speed so the
    turn stays tight), not by driving backwards.

  * CLEAN ARRIVAL via physics. The desired speed is derived from the remaining
    stopping distance, desired_speed = sqrt(2 * a_brake * remaining). That makes the
    car decelerate to exactly 0 at the target and hold, instead of overshooting or
    circling.

  * TEAM-AGNOSTIC. Everything is computed in the car's own frame from its live
    physics; there are no blue/orange or index-vs-team assumptions.

Known limitations (v1, to validate/tune physically):
  * A target placed very close AND almost exactly to the side (inside the car's
    minimum turning circle) at a tight arrival radius can still be hard to tuck
    into with steering alone; the controller powerslides (handbrake) in that case
    to tighten the turn, but the exact behavior is confirmed/tuned in-game.
  * Airborne handling is out of scope here: if the car has no wheel contact we
    still emit ground controls (reported via telemetry) rather than attempting a
    recovery. A later layer can own air recovery.
"""

import math

from rlbot.agents.base_agent import SimpleControllerState

from util.vec import Vec3
from util.orientation import Orientation, relative_location
from util.drive import limit_to_safe_range

# --- Physical constants (unreal units). These are real Rocket League values. ---
MAX_DRIVE_SPEED = 1410.0   # top ground speed on throttle alone (no boost), uu/s
BRAKE_DECEL = 3500.0       # deceleration while braking (throttle opposite motion), uu/s^2
# For reference: a full-lock RL turn radius is ~145 uu near standstill and GROWS with
# speed (~250 uu at 500 uu/s, ~430 uu at 1000 uu/s). So to turn tightly toward an
# off-axis target we must SLOW DOWN; otherwise the target falls inside our turning
# circle and we orbit it forever. That drives the alignment-based speed cap below.

# --- Controller tuning. Empirical values, each with a stated reason. ---
DEFAULT_ARRIVAL_RADIUS = 120.0  # ~one car length; inside this we consider ourselves "arrived"
HOLD_SPEED = 40.0               # |forward speed| under this at arrival -> fully stop & hold (uu/s)
THROTTLE_DEADZONE = 50.0        # speed-error band where we coast rather than throttle/brake (uu/s)
STEER_GAIN = 5.0                # proven RLBot example steering gain
FACING_ANGLE = math.pi / 2.0    # |heading error| beyond this => the target is behind us (TURN label)
# Alignment-based speed cap: drive full speed when pointed at the target, slow right
# down when we need to turn hard, so the turn radius stays small enough to converge
# instead of orbiting. Linear ramp between these two angles.
ALIGN_ANGLE = 0.35              # <= this (~20 deg): aligned, allow full speed
REORIENT_ANGLE = 0.80           # >= this (~46 deg): misaligned, cap speed to turn tightly
REORIENT_SPEED = 500.0          # capped speed while reorienting toward the target (uu/s)
POWERSLIDE_MIN_SPEED = 400.0    # only powerslide to tighten the turn above this speed (uu/s)

# --- State labels (for telemetry / tests) ---
NAV_DRIVE = "DRIVE"       # target ahead: driving toward it
NAV_TURN = "TURN"         # target behind: turning around under forward throttle (never reverse)
NAV_BRAKE = "BRAKE"       # within arrival radius but still moving: braking to a stop
NAV_ARRIVED = "ARRIVED"   # within arrival radius and stopped: holding


def drive_to_target(car, target: Vec3, arrival_radius: float = DEFAULT_ARRIVAL_RADIUS):
    """
    Navigate `car` (a PlayerInfo from packet.game_cars[index]) to the world point
    `target`, slowing to a clean stop within `arrival_radius`.

    Returns (SimpleControllerState, telemetry_dict).
    """
    controls = SimpleControllerState()

    car_loc = Vec3(car.physics.location)
    car_vel = Vec3(car.physics.velocity)
    ori = Orientation(car.physics.rotation)

    to_target = (target - car_loc).flat()     # drive on the ground plane
    dist = to_target.length()

    local = relative_location(car_loc, ori, target)
    heading_error = math.atan2(local.y, local.x)        # 0 = facing target, +/-pi = directly behind
    forward_speed = car_vel.dot(ori.forward)            # signed speed along the nose
    vel_toward_target = car_vel.dot(to_target.normalized()) if dist > 1e-3 else 0.0

    # Steering: proven law (frame-relative, correct signs verified from source).
    steer = limit_to_safe_range(heading_error * STEER_GAIN)

    # Speed that still permits a clean stop at the target from the current distance.
    remaining = max(0.0, dist - arrival_radius)
    stop_speed = min(MAX_DRIVE_SPEED, math.sqrt(2.0 * BRAKE_DECEL * remaining))

    # Alignment-based speed cap: the worse we're pointed, the slower we go, so the
    # turn radius shrinks and we spiral IN to the target instead of orbiting it.
    a = abs(heading_error)
    if a <= ALIGN_ANGLE:
        turn_cap = MAX_DRIVE_SPEED
    elif a >= REORIENT_ANGLE:
        turn_cap = REORIENT_SPEED
    else:
        frac = (a - ALIGN_ANGLE) / (REORIENT_ANGLE - ALIGN_ANGLE)
        turn_cap = MAX_DRIVE_SPEED + frac * (REORIENT_SPEED - MAX_DRIVE_SPEED)

    desired_speed = min(stop_speed, turn_cap)
    target_behind = a > FACING_ANGLE
    handbrake = False

    planar_speed = car_vel.flat().length()   # total ground speed (not just along the nose)

    if dist <= arrival_radius:
        # Arrived: only declare ARRIVED when actually stopped on the ground plane
        # (checking planar speed, not just forward speed, so a car still sliding
        # sideways isn't falsely called parked).
        if planar_speed > HOLD_SPEED:
            if forward_speed > HOLD_SPEED:
                throttle = -1.0                                # brake against forward motion
            elif forward_speed < -HOLD_SPEED:
                throttle = 1.0                                 # brake against backward motion
            else:
                throttle = 0.0                                 # mostly lateral slide: let it settle
            state = NAV_BRAKE
        else:
            throttle = 0.0
            steer = 0.0                                        # stop steering once parked
            state = NAV_ARRIVED
    else:
        speed_err = desired_speed - forward_speed
        if speed_err > THROTTLE_DEADZONE:
            throttle = 1.0                                     # accelerate toward desired speed
        elif speed_err < -THROTTLE_DEADZONE:
            throttle = -1.0                                    # BRAKE: going faster than a clean stop/turn allows
        else:
            throttle = 0.0                                     # coast at desired speed
        # Powerslide to tighten the turn only when badly misaligned AND moving fast
        # enough for a drift to help. (throttle<0 here is still braking, never reverse.)
        handbrake = a > REORIENT_ANGLE and forward_speed > POWERSLIDE_MIN_SPEED
        state = NAV_TURN if target_behind else NAV_DRIVE

    controls.throttle = throttle
    controls.steer = steer
    controls.handbrake = handbrake
    controls.boost = False       # v1: no boost (predictable, clean arrival); future tuning

    telemetry = {
        "state": state,
        "car_pos": (car_loc.x, car_loc.y, car_loc.z),
        "car_vel": (car_vel.x, car_vel.y, car_vel.z),
        "car_forward": (ori.forward.x, ori.forward.y, ori.forward.z),
        "target": (target.x, target.y, target.z),
        "target_distance": dist,
        "heading_error": heading_error,
        "forward_speed": forward_speed,
        "planar_speed": planar_speed,
        "velocity_toward_target": vel_toward_target,
        "has_wheel_contact": bool(getattr(car, "has_wheel_contact", True)),
        "desired_speed": desired_speed,
        "throttle": throttle,
        "steer": steer,
        "handbrake": handbrake,
    }
    return controls, telemetry
