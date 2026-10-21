"""
StabilizeTest -- Checkpoint 4/5 wall-pinch setup bot.

This is deliberately a separate bot from the frozen foundation, navigation,
and geometry inspection bots.  It exercises the first live state-machine layer:

    SEARCH -> SETUP -> STABILIZE -> HOLD

The bot drives to the geometry module's ``approach_point`` and stops there.  It
does not drive at the contact point, does not jump, does not boost, and has no
EXECUTE path.  A viable setup is therefore still a zero-intentional-contact
test of reaching and holding the pinch setup.

The setup is recomputed from the live ball every tick.  If the setup becomes
invalid, progress diverges repeatedly, or stabilization takes too long, the
bot enters a short neutral recovery window and then searches again.  A timer
never advances the bot to EXECUTE.
"""

import math
from collections import deque

from rlbot.agents.base_agent import BaseAgent, SimpleControllerState
from rlbot.utils.structures.game_data_struct import GameTickPacket

from util.vec import Vec3
import navigation
import wall_pinch_geometry as geom


TELEMETRY_EVERY_TICKS = 30

# The setup target is roughly 493 uu from the ball.  This arrival radius leaves
# a substantial geometric gap before the car can reach the contact surface.
SETUP_ARRIVAL_RADIUS = 140.0  # empirical ground-navigation arrival band (uu)

# Pre-position while a ball is demonstrably moving INTO the wall.  This is not
# a pinch-validity relaxation: the bot remains in SETUP until the strict
# geometry gate is satisfied.  The purpose is to remove the avoidable delay
# between seeing an approaching ball and beginning the ground drive.
PREPARE_MAX_WALL_GAP = 1000.0  # empirical early-warning band (uu)
PREPARE_MIN_INWARD_SPEED = 100.0  # uu/s; reject stationary/off-wall balls

# Progress checks use game time, not callback count, so they remain meaningful
# at the configured 120 Hz tick rate and if the framework skips callbacks.
PROGRESS_SAMPLE_SECONDS = 0.20
PROGRESS_DISTANCE_TOLERANCE = 35.0  # ignore small physics/measurement noise (uu)
PROGRESS_BAD_STREAK_LIMIT = 4       # about 0.8 s of repeated regression
HEADING_BAD_TOLERANCE = 0.15        # radians per sample
HEADING_BAD_STREAK_LIMIT = 4
STABILIZE_TIMEOUT_SECONDS = 10.0    # empirical escape hatch; never advances execution
RECOVERY_SECONDS = 0.40             # neutral reset window before SEARCH resumes
TARGET_SHIFT_RESET_DISTANCE = 250.0 # a materially new target gets a fresh trend window


STATE_WAIT = "WAIT"
STATE_SEARCH = "SEARCH"
STATE_SETUP = "SETUP"
STATE_STABILIZE = "STABILIZE"
STATE_HOLD = "HOLD"
STATE_RECOVER = "RECOVER"


class StabilizeTest(BaseAgent):
    """Drive to and hold a live wall-pinch approach point, without contact."""

    def initialize_agent(self):
        self.tick = 0
        self.state = STATE_WAIT
        self.tracking_since = None
        self.recovery_until = None
        self.last_target = None
        self.last_sample_time = None
        self.progress_history = deque(maxlen=6)
        self.distance_bad_streak = 0
        self.heading_bad_streak = 0
        self.last_telemetry = {}
        self._telemetry_time = 0.0
        self._recovery_reason = ""
        self._last_wall_velocity = float("nan")
        self.logger.info(
            f"StabilizeTest initialized (name={self.name!r}, index={self.index}, "
            f"team={self.team}). SETUP/STABILIZE only -- no ball contact."
        )
    def get_output(self, packet: GameTickPacket) -> SimpleControllerState:
        self.tick += 1
        neutral = SimpleControllerState()

        if self.index < 0 or self.index >= packet.num_cars:
            self._reset_tracking()
            self.state = STATE_SEARCH
            self._record_rejected(None, "no_valid_car")
            return neutral

        car = packet.game_cars[self.index]
        now = float(packet.game_info.seconds_elapsed)
        self._telemetry_time = now

        if not packet.game_info.is_round_active:
            self._reset_tracking()
            self.state = STATE_WAIT
            self._record_rejected(None, "round_inactive")
            self._render(car, None, None)
            self._telemetry()
            return neutral

        ball_pos = Vec3(packet.game_ball.physics.location)
        ball_vel = Vec3(packet.game_ball.physics.velocity)
        setup = geom.compute_wall_pinch_setup(ball_pos, ball_vel, self.team)
        self._last_wall_velocity = (
            ball_vel.dot(setup.wall_normal) if setup.wall else float("nan")
        )

        if self.state == STATE_RECOVER:
            if self.recovery_until is not None and now < self.recovery_until:
                self._record_rejected(setup, "recovery")
                self._render(car, setup, None)
                self._telemetry()
                return neutral
            self._reset_tracking()
            self.state = STATE_SEARCH

        preparing = self._should_prepare(setup)
        if not setup.viable and not preparing:
            self._reset_tracking()
            self.state = STATE_SEARCH
            self._record_rejected(setup, setup.reject_reason)
            self._render(car, setup, None)
            self._telemetry()
            return neutral

        # A large target jump means the live ball produced a materially new
        # setup.  Re-start the convergence window instead of judging the old
        # trend against a different target.
        if self.last_target is not None:
            target_shift = (setup.approach_point - self.last_target).flat().length()
            if target_shift > TARGET_SHIFT_RESET_DISTANCE:
                self._reset_tracking()

        if self.tracking_since is None:
            self.tracking_since = now
            # Permit the current tick to seed the first progress sample.  The
            # next sample then has a real baseline instead of losing the first
            # 0.2 s of convergence evidence.
            self.last_sample_time = now - PROGRESS_SAMPLE_SECONDS
            self.progress_history.clear()
            self.distance_bad_streak = 0
            self.heading_bad_streak = 0

        self.state = STATE_STABILIZE if setup.viable else STATE_SETUP
        controls, nav_telemetry = navigation.drive_to_target(
            car, setup.approach_point, arrival_radius=SETUP_ARRIVAL_RADIUS
        )
        self.last_target = setup.approach_point

        if self._progress_is_diverging(now, nav_telemetry):
            self._begin_recovery(now, "progress_diverged")
            self._record_telemetry(setup, nav_telemetry)
            self._render(car, setup, nav_telemetry)
            self._telemetry()
            return neutral

        if now - self.tracking_since > STABILIZE_TIMEOUT_SECONDS:
            self._begin_recovery(now, "stabilize_timeout")
            self._record_telemetry(setup, nav_telemetry)
            self._render(car, setup, nav_telemetry)
            self._telemetry()
            return neutral

        if nav_telemetry["state"] == navigation.NAV_ARRIVED:
            if setup.viable:
                self.state = STATE_HOLD
            else:
                # Hold the safe pre-position while waiting for the strict
                # near-wall geometry gate to become valid.
                self.state = STATE_SETUP
            controls = SimpleControllerState()

        self._record_telemetry(setup, nav_telemetry)
        self._render(car, setup, nav_telemetry)
        self._telemetry()
        return controls

    def _should_prepare(self, setup) -> bool:
        """Whether a rejected setup is a safe, early pre-position opportunity."""
        if setup.viable or setup.reject_reason != "ball_not_near_wall":
            return False
        if setup.ball_wall_gap > PREPARE_MAX_WALL_GAP:
            return False
        if self._last_wall_velocity > -PREPARE_MIN_INWARD_SPEED:
            return False
        # The geometry module has already computed this point; repeat the
        # sanity checks here because this branch intentionally uses a setup
        # before the near-wall validity gate passes.
        return (
            math.isfinite(setup.target_distance)
            and setup.target_distance <= geom.MAX_TARGET_DIST
            and math.isfinite(setup.approach_point.x)
            and math.isfinite(setup.approach_point.y)
            and math.isfinite(setup.approach_point.z)
        )

    def _reset_tracking(self):
        self.tracking_since = None
        self.recovery_until = None
        self.last_target = None
        self.last_sample_time = None
        self.progress_history.clear()
        self.distance_bad_streak = 0
        self.heading_bad_streak = 0

    def _begin_recovery(self, now: float, reason: str):
        self.state = STATE_RECOVER
        self.recovery_until = now + RECOVERY_SECONDS
        self.tracking_since = None
        self.last_sample_time = None
        self.progress_history.clear()
        self.distance_bad_streak = 0
        self.heading_bad_streak = 0
        self.last_target = None
        self._recovery_reason = reason

    def _progress_is_diverging(self, now: float, tele: dict) -> bool:
        """Return true only after repeated, time-spaced regression evidence."""
        if self.last_sample_time is not None and now - self.last_sample_time < PROGRESS_SAMPLE_SECONDS:
            return False

        distance = float(tele["target_distance"])
        heading = abs(float(tele["heading_error"]))
        self.last_sample_time = now
        self.progress_history.append((now, distance, heading))

        if len(self.progress_history) < 2:
            return False

        _, old_distance, old_heading = self.progress_history[-2]
        if distance > old_distance + PROGRESS_DISTANCE_TOLERANCE:
            self.distance_bad_streak += 1
        else:
            self.distance_bad_streak = 0

        if heading > old_heading + HEADING_BAD_TOLERANCE:
            self.heading_bad_streak += 1
        else:
            self.heading_bad_streak = 0

        return (
            self.distance_bad_streak >= PROGRESS_BAD_STREAK_LIMIT
            or self.heading_bad_streak >= HEADING_BAD_STREAK_LIMIT
        )

    def _record_rejected(self, setup, reason: str):
        self.last_telemetry = {
            "state": self.state,
            "setup_viable": False if setup is None else bool(setup.viable),
            "setup_reason": reason,
            "ball_wall_gap": float("nan") if setup is None else setup.ball_wall_gap,
            "target_distance": float("nan") if setup is None else setup.target_distance,
            "heading_error": float("nan"),
            "velocity_toward_target": float("nan"),
            "progress_bad_streak": self.distance_bad_streak,
            "heading_bad_streak": self.heading_bad_streak,
            "wall_velocity": self._last_wall_velocity,
        }

    def _record_telemetry(self, setup, nav_telemetry):
        self.last_telemetry = dict(nav_telemetry)
        self.last_telemetry.update({
            "state": self.state,
            "setup_viable": bool(setup.viable),
            "setup_reason": (
                self._recovery_reason if self.state == STATE_RECOVER else setup.reject_reason
            ),
            "ball_wall_gap": setup.ball_wall_gap,
            "setup_target_distance": setup.target_distance,
            "progress_bad_streak": self.distance_bad_streak,
            "heading_bad_streak": self.heading_bad_streak,
            "wall_velocity": self._last_wall_velocity,
            "stabilize_elapsed": (
                0.0 if self.tracking_since is None
                else max(0.0, self._current_time - self.tracking_since)
            ),
        })

    def _render(self, car, setup, nav_telemetry):
        r = self.renderer
        if r is None:
            return

        r.begin_rendering()
        if setup is not None and setup.wall:
            wall_x = geom.field.SIDE_WALL_X if setup.wall == geom.WALL_RIGHT else -geom.field.SIDE_WALL_X
            r.draw_line_3d(
                Vec3(wall_x, setup.ball_pos.y - 600.0, 20.0),
                Vec3(wall_x, setup.ball_pos.y + 600.0, 20.0),
                r.white(),
            )
            r.draw_rect_3d(setup.ball_pos, 30, 30, True, r.cyan(), centered=True)
            r.draw_rect_3d(setup.contact_point, 20, 20, True, r.red(), centered=True)
            r.draw_rect_3d(setup.approach_point, 26, 26, True, r.lime(), centered=True)
            r.draw_line_3d(setup.approach_point, setup.contact_point, r.lime())
            r.draw_line_3d(
                setup.ball_pos,
                setup.ball_pos + setup.expected_pinch_direction * 400.0,
                r.yellow(),
            )
            if car is not None:
                car_loc = Vec3(car.physics.location)
                r.draw_line_3d(car_loc, setup.approach_point, r.cyan())

        status = f"StabilizeTest {self.state}"
        if setup is None:
            status += " REJECT:no_packet_setup"
        elif setup.viable:
            status += f" wall={setup.wall} gap={setup.ball_wall_gap:.0f}"
            if nav_telemetry is not None:
                status += (
                    f" dist={nav_telemetry['target_distance']:.0f}"
                    f" he={math.degrees(nav_telemetry['heading_error']):.0f}deg"
                )
        elif self.state == STATE_SETUP:
            status += f" PREPARE wall={setup.wall} gap={setup.ball_wall_gap:.0f}"
        else:
            status += f" REJECT:{setup.reject_reason} gap={setup.ball_wall_gap:.0f}"
        status_color = r.white() if setup and setup.viable else r.yellow() if self.state == STATE_SETUP else r.red()
        r.draw_string_2d(20, 20, 1, 1, status, status_color)
        r.end_rendering()

    @property
    def _current_time(self) -> float:
        """The last game time stored by get_output, for telemetry only."""
        return self._telemetry_time

    def _telemetry(self):
        if self.tick % TELEMETRY_EVERY_TICKS != 0:
            return
        t = self.last_telemetry
        print(
            f"[StabilizeTest] tick={self.tick} state={t.get('state', self.state)} "
            f"viable={t.get('setup_viable', False)} reason={t.get('setup_reason', '') or '-'} "
            f"gap={t.get('ball_wall_gap', float('nan')):.0f} "
            f"wall_vel={t.get('wall_velocity', float('nan')):.0f} "
            f"dist={t.get('target_distance', float('nan')):.0f} "
            f"he_deg={math.degrees(t.get('heading_error', float('nan'))):.0f} "
            f"vel_to_tgt={t.get('velocity_toward_target', float('nan')):.0f} "
            f"bad_dist={t.get('progress_bad_streak', 0)} "
            f"bad_heading={t.get('heading_bad_streak', 0)}"
        )

# This checkpoint intentionally stops at setup stabilization; execution is later.

