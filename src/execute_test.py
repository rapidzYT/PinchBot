"""
ExecuteTest -- first intentional wall-pinch contact attempt.

This is a separate experimental bot.  It reuses the verified geometry and
navigation laws, but owns the first contact state machine:

    SEARCH -> SETUP -> STABILIZE -> EXECUTE -> VERIFY -> RECOVER

EXECUTE is entered only after a live viable setup exists and the car is close
to, grounded at, and aligned with the approach point.  The contact run is a
short, bounded throttle pulse toward the live setup's contact-center line.  It
does not claim success from the controller command; VERIFY compares the ball's
post-contact velocity with its pre-contact velocity and reports a conservative
classification.
"""

import math

from rlbot.agents.base_agent import BaseAgent, SimpleControllerState
from rlbot.utils.structures.game_data_struct import GameTickPacket

from util.vec import Vec3
from util.drive import limit_to_safe_range
from util.orientation import Orientation, relative_location
import navigation
import wall_pinch_geometry as geom


TELEMETRY_EVERY_TICKS = 30

# These are deliberately conservative first-attempt values, not a claim of a
# reliable pinch.  They are empirical knobs to tune only from physical results.
SETUP_ARRIVAL_RADIUS = 140.0
EXECUTE_GATE_RADIUS = 160.0       # car center distance from approach point (uu)
EXECUTE_ALIGN_ANGLE = 0.35        # ~20 degrees from approach direction
CONTACT_CENTER_OFFSET = geom.field.BALL_RADIUS + geom.field.CAR_HALF_LENGTH
CONTACT_EVENT_RADIUS = 65.0       # car center distance from contact-center line (uu)
EXECUTE_MAX_SECONDS = 0.75        # enough time to accelerate from a stopped setup
VERIFY_SECONDS = 0.30             # allow the ball velocity to settle
RECOVERY_SECONDS = 0.80            # avoid immediately repeating a stale attempt
STABILIZE_TIMEOUT_SECONDS = 8.0    # never wait forever for a transient setup
CREATE_SETUP_ARRIVAL_RADIUS = 120.0
CREATE_SETUP_STANDOFF = 35.0       # keep the first setup push deliberate

# Early setup uses the same proven rule as StabilizeTest, so ExecuteTest gets
# moving before a transient wall-contact window opens.
# Start moving toward the setup while the ball is still approaching the wall.
# The previous 1000-uu window was too late for the fast approaches observed in
# the first-contact run (the ball could cover that gap before the car arrived).
PREPARE_MAX_WALL_GAP = 2500.0  # empirical early-warning band (uu)
PREPARE_MIN_INWARD_SPEED = 100.0
PREPARE_MAX_LEAD_SECONDS = 2.5  # bounded prediction horizon, empirical
STABILIZE_BOOST_MIN_DISTANCE = 1400.0  # leave braking room after boost acceleration

RESULT_UNVERIFIED = "UNVERIFIED"
RESULT_MISS = "MISS"
RESULT_SOFT_CONTACT = "SOFT_CONTACT"
RESULT_NORMAL_CONTACT = "NORMAL_CONTACT"
RESULT_POSSIBLE_PINCH = "POSSIBLE_PINCH"

STATE_WAIT = "WAIT"
STATE_SEARCH = "SEARCH"
STATE_CREATE_SETUP = "CREATE_SETUP"
STATE_SETUP = "SETUP"
STATE_STABILIZE = "STABILIZE"
STATE_EXECUTE = "EXECUTE"
STATE_VERIFY = "VERIFY"
STATE_RECOVER = "RECOVER"


class ExecuteTest(BaseAgent):
    """Attempt one conservative wall contact, then measure its result."""

    # Subclasses can reuse the live SEARCH/SETUP/STABILIZE pipeline while
    # keeping intentional contact disabled until setup reliability is proven.
    ALLOW_EXECUTE = True
    CREATE_SETUP = False

    def initialize_agent(self):
        self.tick = 0
        self.state = STATE_WAIT
        self.tracking_since = None
        self.last_target = None
        self.recovery_until = None
        self.execute_started = None
        self.verify_until = None
        self.execute_target = None
        self.execute_setup = None
        self.pre_ball_velocity = None
        self.pre_ball_position = None
        self.result = RESULT_UNVERIFIED
        self.last_telemetry = {}
        self._telemetry_time = 0.0
        self._last_wall_velocity = float("nan")
        self._last_ball_z = float("nan")
        self._prepositioned = False
        self._boost_command = False
        self.creation_target = None
        mode = (
            "FIRST CONTACT ATTEMPT -- conservative verification"
            if self.ALLOW_EXECUTE
            else "SETUP ONLY -- intentional contact disabled"
        )
        self.logger.info(
            f"{self.__class__.__name__} initialized (name={self.name!r}, index={self.index}, "
            f"team={self.team}). {mode}."
        )

    def get_output(self, packet: GameTickPacket) -> SimpleControllerState:
        self.tick += 1
        neutral = SimpleControllerState()

        if self.index < 0 or self.index >= packet.num_cars:
            self._reset_search()
            self.state = STATE_SEARCH
            self._record_rejected(None, "no_valid_car")
            return neutral

        car = packet.game_cars[self.index]
        now = float(packet.game_info.seconds_elapsed)
        self._telemetry_time = now

        if not packet.game_info.is_round_active:
            self._reset_search()
            self.state = STATE_WAIT
            self._record_rejected(None, "round_inactive")
            self._render(car, None, None)
            self._telemetry()
            return neutral

        ball_pos = Vec3(packet.game_ball.physics.location)
        ball_vel = Vec3(packet.game_ball.physics.velocity)
        self._last_ball_z = ball_pos.z
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
            self._reset_search()
            self.state = STATE_SEARCH

        if self.state == STATE_VERIFY:
            if now < self.verify_until:
                self._record_verification(setup, ball_vel, now)
                self._render(car, setup, None)
                self._telemetry()
                return neutral
            self._classify_result(setup, ball_vel)
            self.state = STATE_RECOVER
            self.recovery_until = now + RECOVERY_SECONDS
            self._record_verification(setup, ball_vel, now)
            self._render(car, setup, None)
            self._telemetry()
            return neutral

        if self.CREATE_SETUP and not setup.viable:
            controls, creation_telemetry = self._create_setup_controls(
                car, setup, ball_pos, ball_vel
            )
            if creation_telemetry is not None:
                self.state = STATE_CREATE_SETUP
                self._record_telemetry(setup, creation_telemetry, ball_vel, now)
                self._render(car, setup, creation_telemetry)
                self._telemetry()
                return controls

        # Once EXECUTE has started, do not discard the attempt merely because
        # the ball rose or left the strict setup band.  Finish the bounded pulse
        # and measure what happened.
        if self.state == STATE_EXECUTE:
            controls, execute_telemetry = self._execute_controls(car)
            elapsed = now - self.execute_started
            if (
                execute_telemetry["execute_distance"] <= CONTACT_EVENT_RADIUS
                or elapsed >= EXECUTE_MAX_SECONDS
            ):
                self.state = STATE_VERIFY
                self.verify_until = now + VERIFY_SECONDS
                self._record_telemetry(setup, execute_telemetry, ball_vel, now)
                self._render(car, setup, execute_telemetry)
                self._telemetry()
                return neutral
            self._record_telemetry(setup, execute_telemetry, ball_vel, now)
            self._render(car, setup, execute_telemetry)
            self._telemetry()
            return controls

        preparing = self._should_prepare(setup)
        if not setup.viable and not preparing:
            self._reset_search()
            self.state = STATE_SEARCH
            self._record_rejected(setup, setup.reject_reason)
            self._render(car, setup, None)
            self._telemetry()
            return neutral

        navigation_target = setup.approach_point
        self._prepositioned = False
        if preparing:
            navigation_target, self._prepositioned = self._preposition_target(
                setup, ball_pos, ball_vel
            )

        if self.last_target is not None:
            target_shift = (navigation_target - self.last_target).flat().length()
            if target_shift > 250.0:
                self._reset_search()

        if self.tracking_since is None:
            self.tracking_since = now

        self.state = STATE_STABILIZE if setup.viable else STATE_SETUP
        controls, nav_telemetry = navigation.drive_to_target(
            car, navigation_target, arrival_radius=SETUP_ARRIVAL_RADIUS
        )
        self.last_target = navigation_target

        if self.tracking_since is not None and now - self.tracking_since > STABILIZE_TIMEOUT_SECONDS:
            self.state = STATE_RECOVER
            self.recovery_until = now + RECOVERY_SECONDS
            self._record_rejected(setup, "stabilize_timeout")
            self._render(car, setup, nav_telemetry)
            self._telemetry()
            return neutral

        # The useful wall-contact window can be shorter than the time needed
        # for navigation to settle from DRIVE/BRAKE to ARRIVED.  The final
        # approach is safe to gate when the independent contact checks below
        # pass: close to the setup point, grounded, and pointed along the
        # approach direction.  Waiting for a perfect navigation state made
        # the first physical run miss an otherwise aligned window at 155 uu.
        if setup.viable and nav_telemetry["state"] in (
            navigation.NAV_DRIVE,
            navigation.NAV_BRAKE,
            navigation.NAV_ARRIVED,
        ) and nav_telemetry["target_distance"] <= EXECUTE_GATE_RADIUS:
            gate = self._execute_gate(car, setup)
            if gate["execute_ready"]:
                if not self.ALLOW_EXECUTE:
                    self._boost_command = False
                    self._record_telemetry(setup, gate, ball_vel, now)
                    self._render(car, setup, gate)
                    self._telemetry()
                    return SimpleControllerState()
                self._begin_execute(now, ball_pos, ball_vel, setup)
                controls, execute_telemetry = self._execute_controls(car)
                self._record_telemetry(setup, execute_telemetry, ball_vel, now)
                self._render(car, setup, execute_telemetry)
                self._telemetry()
                return controls
            controls = self._alignment_controls(car, setup)
            self._maybe_enable_navigation_boost(car, controls, gate)
            self._record_telemetry(setup, gate, ball_vel, now)
        else:
            self._maybe_enable_navigation_boost(car, controls, nav_telemetry)
            self._record_telemetry(setup, nav_telemetry, ball_vel, now)

        self._render(car, setup, self.last_telemetry)
        self._telemetry()
        return controls

    def _should_prepare(self, setup) -> bool:
        if setup.viable or setup.reject_reason != "ball_not_near_wall":
            return False
        if setup.ball_wall_gap > PREPARE_MAX_WALL_GAP:
            return False
        if self._last_wall_velocity > -PREPARE_MIN_INWARD_SPEED:
            return False
        return (
            math.isfinite(setup.target_distance)
            and setup.target_distance <= geom.MAX_TARGET_DIST
            and math.isfinite(setup.approach_point.x)
            and math.isfinite(setup.approach_point.y)
            and math.isfinite(setup.approach_point.z)
        )

    def _create_setup_controls(self, car, setup, ball_pos, ball_vel):
        """Drive the ball toward the selected side wall before pinching.

        The target is on the interior side of the ball, so the car pushes in
        the outward direction toward the selected wall.  This is setup-making
        contact, not the pinch execution path.  Corner, height, and invalid
        geometry rejections return ``None`` so the caller remains neutral.
        """
        if setup.reject_reason not in ("ball_not_near_wall",):
            self.creation_target = None
            self._boost_command = False
            return SimpleControllerState(), None

        wall_direction = -1.0 * setup.wall_normal
        target = ball_pos - wall_direction * (
            geom.field.BALL_RADIUS + geom.field.CAR_HALF_LENGTH + CREATE_SETUP_STANDOFF
        )
        target = Vec3(target.x, target.y, geom.field.CAR_REST_Z)
        if (
            not all(math.isfinite(value) for value in (target.x, target.y, target.z))
            or abs(target.x) >= geom.field.SIDE_WALL_X - geom.FIELD_MARGIN
            or abs(target.y) >= geom.field.BACK_WALL_Y - geom.FIELD_MARGIN
        ):
            self.creation_target = None
            self._boost_command = False
            return SimpleControllerState(), None

        self.creation_target = target
        car_loc = Vec3(car.physics.location)
        target_distance = (target - car_loc).flat().length()
        wall_heading_error = self._direction_heading_error(car, wall_direction)

        if target_distance > CREATE_SETUP_ARRIVAL_RADIUS:
            controls, nav = navigation.drive_to_target(
                car, target, arrival_radius=CREATE_SETUP_ARRIVAL_RADIUS
            )
            self._maybe_enable_creation_boost(car, controls, nav)
            nav = dict(nav)
            nav.update({
                "state": STATE_CREATE_SETUP,
                "target": (target.x, target.y, target.z),
                "target_distance": target_distance,
                "heading_error": nav["heading_error"],
                "creation_target_distance": target_distance,
                "creation_wall_heading_error": wall_heading_error,
                "execute_distance": float("nan"),
                "execute_ready": False,
            })
            return controls, nav

        # Once behind the ball, push in the selected wall direction. Keep the
        # first push slow while the car aligns; use full throttle only when the
        # push direction is reasonably controlled.
        controls = SimpleControllerState()
        controls.steer = limit_to_safe_range(
            wall_heading_error * navigation.STEER_GAIN
        )
        controls.throttle = 1.0 if abs(wall_heading_error) <= 0.45 else 0.25
        controls.boost = False
        self._boost_command = False
        return controls, {
            "state": STATE_CREATE_SETUP,
            "target": (target.x, target.y, target.z),
            "target_distance": target_distance,
            "heading_error": wall_heading_error,
            "creation_target_distance": target_distance,
            "creation_wall_heading_error": wall_heading_error,
            "execute_distance": float("nan"),
            "execute_ready": False,
            "velocity_toward_target": 0.0,
        }

    def _maybe_enable_creation_boost(self, car, controls, telemetry):
        self._boost_command = False
        controls.boost = False
        if (
            controls.throttle >= 0.9
            and not controls.handbrake
            and getattr(car, "boost", 0) > 0
            and telemetry["target_distance"] > 1000.0
            and abs(telemetry["heading_error"]) <= 0.45
        ):
            controls.boost = True
            self._boost_command = True

    def _preposition_target(self, setup, ball_pos, ball_vel):
        """Aim at a bounded estimate of the wall-impact setup point.

        This is only used before the ball is near the wall.  Once the setup is
        viable, navigation returns to the live approach point.  A prediction is
        accepted only when the projected ball still produces a valid geometry;
        otherwise the current setup point is retained without clamping.
        """
        inward_speed = -self._last_wall_velocity
        if inward_speed <= PREPARE_MIN_INWARD_SPEED:
            return setup.approach_point, False

        time_to_wall = setup.ball_wall_gap / inward_speed
        if not math.isfinite(time_to_wall) or not 0.0 < time_to_wall <= PREPARE_MAX_LEAD_SECONDS:
            return setup.approach_point, False

        predicted_y = ball_pos.y + ball_vel.y * time_to_wall
        predicted_z = ball_pos.z + ball_vel.z * time_to_wall
        if setup.wall == geom.WALL_RIGHT:
            predicted_x = geom.field.SIDE_WALL_X - geom.field.BALL_RADIUS
        elif setup.wall == geom.WALL_LEFT:
            predicted_x = -geom.field.SIDE_WALL_X + geom.field.BALL_RADIUS
        else:
            return setup.approach_point, False

        predicted_ball = Vec3(predicted_x, predicted_y, predicted_z)
        predicted_setup = geom.compute_wall_pinch_setup(
            predicted_ball, ball_vel, self.team
        )
        if not predicted_setup.viable:
            return setup.approach_point, False
        return predicted_setup.approach_point, True

    def _execute_gate(self, car, setup):
        car_loc = Vec3(car.physics.location)
        distance = (setup.approach_point - car_loc).flat().length()
        heading_error = self._direction_heading_error(car, setup.approach_direction)
        ready = (
            bool(getattr(car, "has_wheel_contact", True))
            and distance <= EXECUTE_GATE_RADIUS
            and abs(heading_error) <= EXECUTE_ALIGN_ANGLE
        )
        return {
            "state": STATE_STABILIZE,
            "target": (setup.approach_point.x, setup.approach_point.y, setup.approach_point.z),
            "target_distance": distance,
            "heading_error": heading_error,
            "execute_distance": float("nan"),
            "execute_ready": ready,
            "velocity_toward_target": 0.0,
        }

    def _alignment_controls(self, car, setup):
        controls = SimpleControllerState()
        heading_error = self._direction_heading_error(car, setup.approach_direction)
        controls.steer = limit_to_safe_range(heading_error * navigation.STEER_GAIN)
        # A small grounded throttle gives the car steering authority while it
        # is still well outside the ball-contact line.
        controls.throttle = 0.25 if abs(heading_error) > 0.05 else 0.0
        return controls

    def _begin_execute(self, now, ball_pos, ball_vel, setup):
        self.state = STATE_EXECUTE
        self.execute_started = now
        self.execute_setup = setup
        self.pre_ball_position = ball_pos
        self.pre_ball_velocity = ball_vel
        self.execute_target = ball_pos - setup.approach_direction * CONTACT_CENTER_OFFSET
        self.execute_target = Vec3(
            self.execute_target.x, self.execute_target.y, geom.field.CAR_REST_Z
        )
        self.result = RESULT_UNVERIFIED

    def _execute_controls(self, car):
        controls = SimpleControllerState()
        car_loc = Vec3(car.physics.location)
        ori = Orientation(car.physics.rotation)
        local = relative_location(car_loc, ori, self.execute_target)
        heading_error = math.atan2(local.y, local.x)
        execute_distance = (self.execute_target - car_loc).flat().length()
        controls.steer = limit_to_safe_range(heading_error * navigation.STEER_GAIN)
        controls.throttle = 1.0
        controls.boost = (
            bool(getattr(car, "boost", 0) > 0)
            and execute_distance > 120.0
            and abs(heading_error) <= 0.60
        )
        self._boost_command = controls.boost
        return controls, {
            "state": STATE_EXECUTE,
            "target": (self.execute_target.x, self.execute_target.y, self.execute_target.z),
            "target_distance": execute_distance,
            "heading_error": heading_error,
            "execute_distance": execute_distance,
            "execute_ready": True,
            "velocity_toward_target": 0.0,
        }

    def _maybe_enable_navigation_boost(self, car, controls, telemetry):
        """Use boost for a long, aligned ground approach, never for a hard turn."""
        self._boost_command = False
        controls.boost = False
        if controls.throttle < 0.9 or controls.handbrake:
            return
        if getattr(car, "boost", 0) <= 0:
            return

        target_distance = telemetry.get("target_distance", float("inf"))
        heading_error = abs(telemetry.get("heading_error", float("inf")))
        if not math.isfinite(target_distance) or not math.isfinite(heading_error):
            return

        if (
            self.state == STATE_SETUP
            and target_distance > 600.0
            and heading_error <= 0.65
        ) or (
            self.state == STATE_STABILIZE
            and target_distance > STABILIZE_BOOST_MIN_DISTANCE
            and heading_error <= 0.45
        ):
            controls.boost = True
            self._boost_command = True

    def _direction_heading_error(self, car, direction):
        ori = Orientation(car.physics.rotation)
        forward_component = ori.forward.dot(direction)
        right_component = ori.right.dot(direction)
        return math.atan2(right_component, forward_component)

    def _classify_result(self, setup, ball_vel):
        post_planar_speed = ball_vel.flat().length()
        pre_planar_speed = self.pre_ball_velocity.flat().length()
        delta_v = ball_vel - self.pre_ball_velocity
        tangent_gain = delta_v.dot(self.execute_setup.expected_pinch_direction)
        tangent_speed = ball_vel.dot(self.execute_setup.expected_pinch_direction)

        # These labels are deliberately conservative.  Without a collision
        # event in the v4 packet, high along-wall acceleration is evidence of a
        # possible pinch, not proof of compression.
        if tangent_gain >= 500.0 and tangent_speed >= 800.0 and post_planar_speed >= 800.0:
            self.result = RESULT_POSSIBLE_PINCH
        elif post_planar_speed - pre_planar_speed >= 250.0:
            self.result = RESULT_NORMAL_CONTACT
        elif post_planar_speed - pre_planar_speed >= 100.0:
            self.result = RESULT_SOFT_CONTACT
        else:
            self.result = RESULT_MISS

        self._last_result_metrics = {
            "pre_ball_speed": pre_planar_speed,
            "post_ball_speed": post_planar_speed,
            "tangent_speed": tangent_speed,
            "tangent_gain": tangent_gain,
        }

    def _record_rejected(self, setup, reason):
        self.last_telemetry = {
            "state": self.state,
            "setup_viable": False if setup is None else bool(setup.viable),
            "setup_reason": reason,
            "ball_wall_gap": float("nan") if setup is None else setup.ball_wall_gap,
            "wall_velocity": self._last_wall_velocity,
            "ball_z": self._last_ball_z,
            "target_distance": float("nan") if setup is None else setup.target_distance,
            "heading_error": float("nan"),
            "execute_distance": float("nan"),
            "execute_ready": False,
            "prepositioned": False,
            "boost_command": False,
            "result": self.result,
        }

    def _record_telemetry(self, setup, tele, ball_vel, now):
        self.last_telemetry = dict(tele)
        self.last_telemetry.update({
            "state": self.state,
            "setup_viable": bool(setup.viable),
            "setup_reason": setup.reject_reason,
            "ball_wall_gap": setup.ball_wall_gap,
            "wall_velocity": self._last_wall_velocity,
            "ball_z": self._last_ball_z,
            "result": self.result,
            "prepositioned": self._prepositioned,
            "boost_command": self._boost_command,
            "ball_speed": ball_vel.flat().length(),
            "execute_elapsed": (
                float("nan") if self.execute_started is None else now - self.execute_started
            ),
        })
        if hasattr(self, "_last_result_metrics"):
            self.last_telemetry.update(self._last_result_metrics)

    def _record_verification(self, setup, ball_vel, now):
        tele = {
            "state": STATE_VERIFY,
            "target_distance": float("nan"),
            "heading_error": float("nan"),
            "execute_distance": float("nan"),
            "execute_ready": False,
            "velocity_toward_target": 0.0,
        }
        self._record_telemetry(setup, tele, ball_vel, now)

    def _reset_search(self):
        self.tracking_since = None
        self.last_target = None
        self.recovery_until = None
        self.execute_started = None
        self.verify_until = None
        self.execute_target = None
        self.execute_setup = None
        self.pre_ball_velocity = None
        self.pre_ball_position = None

    def _render(self, car, setup, tele):
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
            if self.execute_target is not None:
                r.draw_rect_3d(self.execute_target, 22, 22, True, r.orange(), centered=True)
            if self.creation_target is not None:
                r.draw_rect_3d(self.creation_target, 22, 22, True, r.orange(), centered=True)
            if car is not None:
                line_target = self.creation_target or setup.approach_point
                r.draw_line_3d(Vec3(car.physics.location), line_target, r.cyan())

        status = f"ExecuteTest {self.state} result={self.result}"
        if setup is None:
            status += " reason=no_setup"
        elif setup.viable:
            status += f" gap={setup.ball_wall_gap:.0f}"
        else:
            status += f" reason={setup.reject_reason} gap={setup.ball_wall_gap:.0f}"
        if tele is not None:
            status += f" dist={tele.get('target_distance', float('nan')):.0f}"
        r.draw_string_2d(20, 20, 1, 1, status, r.white() if setup and setup.viable else r.red())
        r.end_rendering()

    def _telemetry(self):
        if self.tick % TELEMETRY_EVERY_TICKS != 0:
            return
        t = self.last_telemetry
        print(
            f"[{self.__class__.__name__}] tick={self.tick} state={t.get('state', self.state)} "
            f"result={t.get('result', self.result)} "
            f"viable={t.get('setup_viable', False)} reason={t.get('setup_reason', '') or '-'} "
            f"gap={t.get('ball_wall_gap', float('nan')):.0f} "
            f"wall_vel={t.get('wall_velocity', float('nan')):.0f} "
            f"ball_z={t.get('ball_z', float('nan')):.0f} "
            f"dist={t.get('target_distance', float('nan')):.0f} "
            f"he_deg={math.degrees(t.get('heading_error', float('nan'))):.0f} "
            f"ready={t.get('execute_ready', False)} "
            f"preplan={t.get('prepositioned', False)} "
            f"boost={t.get('boost_command', False)} "
            f"exec_dist={t.get('execute_distance', float('nan')):.0f} "
            f"ball_spd={t.get('ball_speed', float('nan')):.0f} "
            f"tan_gain={t.get('tangent_gain', float('nan')):.0f}"
        )

