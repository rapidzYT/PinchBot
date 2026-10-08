"""
Kuxir side-wall pinch -- SEARCH / SETUP geometry (Stage 2).

This module is PURE GEOMETRY. It does not drive and it never touches the ball; it
only computes where a side-wall pinch setup is, from the live ball state, so a bot
can render it for inspection and (later) drive to it.

The mechanic (Kuxir side-wall pinch): the ball is near a side wall; the car drives
diagonally INTO the ball so the ball is compressed between the car and the wall and
squirts out ALONG the wall. The spatial relationship is CAR -> BALL -> WALL: the car
sits on the field-interior side of the ball, the wall is on the far side.

All coordinates are verified (see field.py), never remembered:
  * side walls at x = +/- field.SIDE_WALL_X  (RIGHT = +x, LEFT = -x)
  * inward normal: RIGHT wall -> (-1,0,0); LEFT wall -> (+1,0,0)
  * horizontal along-wall tangent is the y axis; its SIGN is the desired pinch
    (exit) direction.

Why the approach direction is a blend of (into-wall) and (tangent): for the ball to
exit along +tangent after being pinched on the wall, the car's push must have a
component INTO the wall (= -wall_normal) and a component along +tangent. The wall
cancels the into-wall part; the tangential part remains as the exit. So:

    approach_direction = normalize( (-wall_normal) + wall_tangent )   # ~45 deg
    contact_point      = ball_center - approach_direction * BALL_RADIUS
    approach_point     = ball_center - approach_direction * (BALL_RADIUS + STANDOFF)

which places the car interior-and-behind the ball, driving diagonally toward the
wall in the pinch direction.

A setup is only returned as viable after a full validation layer; a rejected setup
carries an explicit reject_reason (never a clamped/nonsense target).
"""

import math
from dataclasses import dataclass

from util.vec import Vec3
import field

# --- Tuning constants (empirical unless geometric; each with a reason) ---
NEAR_WALL_THRESHOLD = 900.0   # ball surface must be within this of the wall to pinch (empirical)
# Highest ball-center a car ON THE GROUND can actually contact: the ball's bottom
# (center_z - BALL_RADIUS) must be within the car's height. Above this the ball is
# up the wall -> a wall/air pinch, which is a LATER stage, not this ground setup.
# Geometry-derived (not a magic number); physical testing may adjust it.
MAX_PINCH_HEIGHT = field.BALL_RADIUS + field.OCTANE_HEIGHT   # ~129 uu
CORNER_Y_LIMIT = 4000.0       # beyond this |y| the side wall curves into the corner; flat model invalid
APPROACH_STANDOFF = 400.0     # car sets up this far behind the ball along the approach line (empirical)
TANGENT_VEL_THRESHOLD = 200.0 # above this along-wall ball speed, pinch the way it's already going (empirical)
BALL_LEAVE_WALL_SPEED = 800.0 # if the ball is moving off the wall toward midfield faster than this,
                              # the setup is stale -> reject (empirical; see STABILIZE abort rule)
MAX_TARGET_DIST = 2000.0      # sanity: the setup point must be near the ball, not thousands of uu away
FIELD_MARGIN = 100.0          # keep computed targets this far inside the walls

WALL_RIGHT = "RIGHT"
WALL_LEFT = "LEFT"


@dataclass(frozen=True)
class PinchSetup:
    viable: bool
    reject_reason: str            # "" when viable
    wall: str                     # WALL_RIGHT / WALL_LEFT / ""
    wall_normal: Vec3             # inward unit normal
    wall_tangent: Vec3            # along-wall unit, signed = pinch/exit direction
    contact_point: Vec3           # ball surface point facing the car
    approach_point: Vec3          # desired car SETUP position (interior + behind the ball)
    approach_direction: Vec3      # unit, horizontal: direction the car drives to pinch
    expected_pinch_direction: Vec3  # unit: where the ball should exit
    ball_pos: Vec3
    ball_wall_gap: float          # ball-surface-to-wall gap (uu); negative if overlapping
    target_distance: float        # approach_point -> ball distance (uu)


def _finite_vec(v: Vec3) -> bool:
    return math.isfinite(v.x) and math.isfinite(v.y) and math.isfinite(v.z)


def _in_bounds(p: Vec3) -> bool:
    return (abs(p.x) < field.SIDE_WALL_X - FIELD_MARGIN
            and abs(p.y) < field.BACK_WALL_Y - FIELD_MARGIN
            and p.z >= -1.0)


def compute_wall_pinch_setup(ball_pos: Vec3, ball_vel: Vec3, team: int) -> PinchSetup:
    """
    Compute the side-wall pinch SETUP from the live ball state, for the given team.
    Always returns a PinchSetup; check `.viable` and `.reject_reason`. The geometry
    fields are filled in whenever they can be computed (even for a rejected setup, so
    the rejection can be rendered/inspected), except on non-finite input.
    """
    zero = Vec3(0, 0, 0)

    # --- non-finite input: cannot compute anything meaningful ---
    if not (_finite_vec(ball_pos) and _finite_vec(ball_vel)):
        return PinchSetup(False, "non_finite_input", "", zero, zero, zero, zero, zero, zero,
                          ball_pos, float("nan"), float("nan"))

    # --- select the nearer side wall ---
    if ball_pos.x >= 0.0:
        wall = WALL_RIGHT
        wall_x = field.SIDE_WALL_X
        wall_normal = Vec3(-1.0, 0.0, 0.0)     # inward from the right wall
    else:
        wall = WALL_LEFT
        wall_x = -field.SIDE_WALL_X
        wall_normal = Vec3(1.0, 0.0, 0.0)      # inward from the left wall

    ball_wall_gap = (field.SIDE_WALL_X - abs(ball_pos.x)) - field.BALL_RADIUS

    # --- pinch/exit direction along the wall (the tangent sign) ---
    if abs(ball_vel.y) > TANGENT_VEL_THRESHOLD:
        tangent_sign = 1.0 if ball_vel.y > 0 else -1.0      # pinch it the way it's already rolling
    else:
        tangent_sign = field.attack_sign(team)              # else toward this team's attack goal
    wall_tangent = Vec3(0.0, tangent_sign, 0.0)
    expected_pinch_direction = Vec3(0.0, tangent_sign, 0.0)  # ball exits along the wall

    # --- approach direction: blend of into-wall (-normal) and along-wall (+tangent) ---
    approach_raw = (-1.0 * wall_normal) + wall_tangent       # e.g. right wall, +y: (1,1,0)
    approach_len = approach_raw.length()
    approach_direction = approach_raw.normalized() if approach_len > 1e-6 else zero

    # --- contact point (ball surface facing the car) and setup point (interior + behind) ---
    contact_point = ball_pos - approach_direction * field.BALL_RADIUS
    approach_point = ball_pos - approach_direction * (field.BALL_RADIUS + APPROACH_STANDOFF)
    # Put the car's setup point at driving height; keep contact at the ball's height.
    approach_point = Vec3(approach_point.x, approach_point.y, field.CAR_REST_Z)

    target_distance = (approach_point - ball_pos).flat().length()

    # --- validation (first failing check wins; never emit a nonsense target) ---
    reason = ""
    if abs(ball_pos.x) >= field.SIDE_WALL_X:
        reason = "ball_outside_field"
    elif abs(ball_pos.y) > CORNER_Y_LIMIT:
        reason = "ball_near_corner"          # flat side-wall model invalid in the rounded corner
    elif ball_wall_gap > NEAR_WALL_THRESHOLD:
        reason = "ball_not_near_wall"
    elif ball_pos.z > MAX_PINCH_HEIGHT:
        reason = "ball_too_high"
    elif ball_vel.dot(wall_normal) > BALL_LEAVE_WALL_SPEED:
        # wall_normal points inward; a large component along it means the ball is
        # rushing off the wall toward midfield -> the wall pinch setup is stale.
        reason = "ball_leaving_wall"
    elif approach_len <= 1e-6:
        reason = "approach_dir_degenerate"
    elif not _in_bounds(approach_point):
        reason = "target_out_of_bounds"
    elif target_distance > MAX_TARGET_DIST:
        reason = "target_too_far_from_ball"

    viable = reason == ""
    return PinchSetup(
        viable=viable,
        reject_reason=reason,
        wall=wall,
        wall_normal=wall_normal,
        wall_tangent=wall_tangent,
        contact_point=contact_point,
        approach_point=approach_point,
        approach_direction=approach_direction,
        expected_pinch_direction=expected_pinch_direction,
        ball_pos=ball_pos,
        ball_wall_gap=ball_wall_gap,
        target_distance=target_distance,
    )
