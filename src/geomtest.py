"""
GeomTest -- Stage 2 physical INSPECTION bot (wall-pinch geometry).

ZERO intentional ball contact. This bot NEVER drives -- it returns a neutral
controller every tick and simply RENDERS the computed side-wall pinch setup so we
can visually confirm the geometry agrees with the live field:

  * the selected wall (white segment),
  * the ball (cyan),
  * the contact point on the ball facing the car (red),
  * the desired car setup/approach point (lime) and the approach vector
    (lime line approach_point -> contact_point),
  * the expected pinch/exit direction (yellow line from the ball),
  * the car's own forward direction (orange line),
  * a status string with the selected wall and, if the setup is rejected, WHY.

Move the ball near a side wall to see a viable setup; move it to midfield to see
the explicit rejection reason. The car stays put the whole time.
"""

from rlbot.agents.base_agent import BaseAgent, SimpleControllerState
from rlbot.utils.structures.game_data_struct import GameTickPacket

from util.vec import Vec3
import wall_pinch_geometry as geom

TELEMETRY_EVERY_TICKS = 30


class GeomTest(BaseAgent):
    def initialize_agent(self):
        self.tick = 0
        self.logger.info(
            f"GeomTest initialized (name={self.name!r}, index={self.index}, team={self.team}). "
            f"RENDER ONLY -- the car will not move."
        )

    def get_output(self, packet: GameTickPacket) -> SimpleControllerState:
        self.tick += 1
        neutral = SimpleControllerState()  # zero everything: no contact, ever

        if self.index < 0 or self.index >= packet.num_cars:
            return neutral

        car = packet.game_cars[self.index]
        ball_pos = Vec3(packet.game_ball.physics.location)
        ball_vel = Vec3(packet.game_ball.physics.velocity)

        setup = geom.compute_wall_pinch_setup(ball_pos, ball_vel, self.team)

        self._render(car, setup)
        self._telemetry(setup)
        return neutral

    def _render(self, car, setup):
        r = self.renderer
        if r is None:
            return
        car_loc = Vec3(car.physics.location)

        r.begin_rendering()

        # Selected wall: a segment of the wall plane near the ball.
        if setup.wall:
            wall_x = geom.field.SIDE_WALL_X if setup.wall == geom.WALL_RIGHT else -geom.field.SIDE_WALL_X
            y0 = setup.ball_pos.y - 600.0
            y1 = setup.ball_pos.y + 600.0
            r.draw_line_3d(Vec3(wall_x, y0, 20.0), Vec3(wall_x, y1, 20.0), r.white())

        # Ball, contact point, setup/approach point.
        r.draw_rect_3d(setup.ball_pos, 30, 30, True, r.cyan(), centered=True)
        r.draw_rect_3d(setup.contact_point, 20, 20, True, r.red(), centered=True)
        r.draw_rect_3d(setup.approach_point, 24, 24, True, r.lime(), centered=True)

        # Approach vector (the drive-in line) and expected exit direction.
        r.draw_line_3d(setup.approach_point, setup.contact_point, r.lime())
        r.draw_line_3d(setup.ball_pos, setup.ball_pos + setup.expected_pinch_direction * 400.0, r.yellow())

        # Car forward vector, for frame reference.
        from util.orientation import Orientation
        fwd = Orientation(car.physics.rotation).forward
        r.draw_line_3d(car_loc, car_loc + fwd * 300.0, r.orange())

        status = (f"GeomTest wall={setup.wall or '-'} "
                  f"{'VIABLE' if setup.viable else 'REJECT:' + setup.reject_reason} "
                  f"gap={setup.ball_wall_gap:.0f} dist={setup.target_distance:.0f}")
        r.draw_string_2d(20, 20, 1, 1, status, r.white() if setup.viable else r.red())

        r.end_rendering()

    def _telemetry(self, setup):
        if self.tick % TELEMETRY_EVERY_TICKS != 0:
            return
        b, c, a = setup.ball_pos, setup.contact_point, setup.approach_point
        n, t, p = setup.wall_normal, setup.wall_tangent, setup.expected_pinch_direction
        print(
            f"[GeomTest] tick={self.tick} "
            f"{'VIABLE' if setup.viable else 'REJECT=' + setup.reject_reason} "
            f"wall={setup.wall or '-'} "
            f"ball=({b.x:.0f},{b.y:.0f},{b.z:.0f}) gap={setup.ball_wall_gap:.0f} "
            f"normal=({n.x:.0f},{n.y:.0f},{n.z:.0f}) tangent=({t.x:.0f},{t.y:.0f},{t.z:.0f}) "
            f"contact=({c.x:.0f},{c.y:.0f},{c.z:.0f}) "
            f"approach=({a.x:.0f},{a.y:.0f},{a.z:.0f}) dist={setup.target_distance:.0f} "
            f"pinch_dir=({p.x:.1f},{p.y:.1f},{p.z:.1f})"
        )
