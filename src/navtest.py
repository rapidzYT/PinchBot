"""
NavTest -- Checkpoint 1 physical test bot (generic navigation).

This is a SEPARATE bot from the frozen Stage 0 foundation (bot.py). It exercises
the generic navigation controller (navigation.drive_to_target) by driving to a
live target and stopping cleanly, so we can physically confirm turning, driving,
slowing, and arrival without circling or blind reversing.

Target: the ball's position projected to the ground. We pass arrival_radius =
BALL_STANDOFF so the car stops JUST SHORT of the ball instead of bumping it --
this is pure navigation, no intentional ball contact. Move the ball around in
free play to test arrival from any angle and distance.
"""

import math

from rlbot.agents.base_agent import BaseAgent, SimpleControllerState
from rlbot.utils.structures.game_data_struct import GameTickPacket

from util.vec import Vec3
import navigation

TELEMETRY_EVERY_TICKS = 30

# Stop short of the ball: ball radius + half a car length + a small margin, so the
# car arrives next to the ball rather than driving through it.
BALL_RADIUS = 92.75
CAR_HALF_LENGTH = 59.0          # ~half an Octane's length (~118 uu)
STANDOFF_MARGIN = 50.0
BALL_STANDOFF = BALL_RADIUS + CAR_HALF_LENGTH + STANDOFF_MARGIN  # ~202 uu


class NavTest(BaseAgent):
    def initialize_agent(self):
        self.tick = 0
        self.logger.info(
            f"NavTest initialized (name={self.name!r}, index={self.index}, team={self.team})."
        )

    def get_output(self, packet: GameTickPacket) -> SimpleControllerState:
        self.tick += 1

        if self.index < 0 or self.index >= packet.num_cars:
            return SimpleControllerState()

        if not packet.game_info.is_round_active:
            return SimpleControllerState()  # hold during kickoff pause / replays / goal resets

        car = packet.game_cars[self.index]
        ball = packet.game_ball.physics.location
        # Target = ball on the ground plane, held at the car's height for clean ground geometry.
        target = Vec3(ball.x, ball.y, car.physics.location.z)

        controls, tele = navigation.drive_to_target(car, target, arrival_radius=BALL_STANDOFF)

        self._render(car, target, tele)
        self._telemetry(packet, tele)
        return controls

    def _render(self, car, target, tele):
        # Debug overlay: line car->target, a marker at the target, and a status line.
        # Rendering is cosmetic; if the renderer isn't available yet we simply skip it.
        # We do NOT wrap this in a broad try/except -- a genuine rendering error should
        # surface during development rather than be silently swallowed.
        r = self.renderer
        if r is None:
            return
        car_loc = Vec3(car.physics.location)
        r.begin_rendering()
        r.draw_line_3d(car_loc, target, r.lime())
        r.draw_rect_3d(target, 20, 20, True, r.cyan(), centered=True)
        r.draw_string_2d(
            20, 20, 1, 1,
            f"NavTest {tele['state']} dist={tele['target_distance']:.0f} "
            f"he={math.degrees(tele['heading_error']):.0f}deg "
            f"thr={tele['throttle']:.1f} steer={tele['steer']:.2f}",
            r.white(),
        )
        r.end_rendering()

    def _telemetry(self, packet, tele):
        if self.tick % TELEMETRY_EVERY_TICKS != 0:
            return
        cp, cv, cf, tg = tele["car_pos"], tele["car_vel"], tele["car_forward"], tele["target"]
        b = packet.game_ball.physics.location
        print(
            f"[NavTest] tick={self.tick} state={tele['state']} "
            f"car_pos=({cp[0]:.0f},{cp[1]:.0f},{cp[2]:.0f}) "
            f"car_vel=({cv[0]:.0f},{cv[1]:.0f},{cv[2]:.0f}) "
            f"car_fwd=({cf[0]:.2f},{cf[1]:.2f},{cf[2]:.2f}) "
            f"ball=({b.x:.0f},{b.y:.0f},{b.z:.0f}) "
            f"target=({tg[0]:.0f},{tg[1]:.0f},{tg[2]:.0f}) "
            f"dist={tele['target_distance']:.0f} "
            f"he_deg={math.degrees(tele['heading_error']):.0f} "
            f"vel_to_tgt={tele['velocity_toward_target']:.0f} "
            f"des_spd={tele['desired_speed']:.0f} "
            f"thr={tele['throttle']:.2f} steer={tele['steer']:.2f}"
        )
