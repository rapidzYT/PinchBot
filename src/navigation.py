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
"""

import math

from rlbot.agents.base_agent import SimpleControllerState

from util.vec import Vec3
from util.orientation import Orientation, relative_location
from util.drive import limit_to_safe_range

# --- Physical constants (unreal units). These are real Rocket League values. ---
MAX_DRIVE_SPEED = 1410.0   # top ground speed on throttle alone (no boost), uu/s
BRAKE_DECEL = 3500.0       # deceleration while braking (throttle opposite motion), uu/s^2

# --- Controller tuning. Empirical values, each with a stated reason. ---
DEFAULT_ARRIVAL_RADIUS = 120.0  # ~one car length; inside this we consider ourselves "arrived"
HOLD_SPEED = 40.0               # |forward speed| under this at arrival -> fully stop & hold (uu/s)
THROTTLE_DEADZONE = 50.0        # speed-error band where we coast rather than throttle/brake (uu/s)
TURN_SPEED_CAP = 700.0          # cap speed while turning around so the turn radius stays tight (uu/s)
STEER_GAIN = 5.0                # proven RLBot example steering gain
FACING_ANGLE = math.pi / 2.0    # |heading error| beyond this => the target is behind us

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
    desired_speed = min(MAX_DRIVE_SPEED, math.sqrt(2.0 * BRAKE_DECEL * remaining))

    target_behind = abs(heading_error) > FACING_ANGLE
    if target_behind:
        # Keep forward motion but cap the speed so we can turn around tightly.
        desired_speed = min(desired_speed, TURN_SPEED_CAP)

    if dist <= arrival_radius:
        # Arrived: kill any residual speed, then hold still.
        if abs(forward_speed) > HOLD_SPEED:
            throttle = -1.0 if forward_speed > 0.0 else 1.0   # brake against current motion
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
            throttle = -1.0                                    # BRAKE: going faster than a clean stop allows
        else:
            throttle = 0.0                                     # coast at desired speed
        state = NAV_TURN if target_behind else NAV_DRIVE

    controls.throttle = throttle
    controls.steer = steer
    controls.handbrake = False   # v1: no powerslide (turn-speed cap keeps turns tight); future tuning
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
        "velocity_toward_target": vel_toward_target,
        "desired_speed": desired_speed,
        "throttle": throttle,
        "steer": steer,
    }
    return controls, telemetry
