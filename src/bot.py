"""
PinchBot -- Stage 0 foundation.

Purpose of this stage
---------------------
Prove the entire RLBot pipeline end to end, with the smallest possible bot:

    RLBot GUI
      -> loads pinch_bot.cfg
      -> launches this python file
      -> initialize_agent() runs
      -> get_output(packet) receives a real GameTickPacket every tick
      -> the bot identifies its OWN car via self.index
      -> returns a SimpleControllerState
      -> Rocket League applies that controller input
      -> the car physically moves

Deterministic test sequence (longitudinal only; steer is 0 the whole time):

    IDLE     throttle 0   -- briefly do nothing so the starting state is visible
    THROTTLE throttle 1   -- hold full forward; the car should clearly accelerate
    STOP     throttle 0   -- release throttle, coast to a stop, then hold still

Timing is anchored to real game time (GameInfo.seconds_elapsed) measured from
the first tick where the round is active. That makes the sequence:
  * start exactly when play begins (not during the kickoff countdown), and
  * independent of how often the framework happens to call get_output().

This file intentionally contains NO pinch logic and NO navigation. It is the
frozen foundation that every later checkpoint builds on. See README.md.

API note (verified against rlbot 1.68.0):
  * BaseAgent.__init__(self, name, team, index) -- the framework constructs us.
  * self.index is the authoritative index into packet.game_cars.
  * PlayerInfo.name is a c_wchar array, i.e. already a python str -- never
    call .decode() on it.
"""

from rlbot.agents.base_agent import BaseAgent, SimpleControllerState
from rlbot.utils.structures.game_data_struct import GameTickPacket

# --- Stage 0 sequence timing, in seconds of real game time. ---
IDLE_SECONDS = 1.0        # do nothing first, so the initial rest state is observable
THROTTLE_SECONDS = 1.5    # hold full throttle long enough to clearly accelerate
# After IDLE + THROTTLE the bot enters STOP and stays there (one-shot test).

STATE_IDLE = "IDLE"
STATE_THROTTLE = "THROTTLE"
STATE_STOP = "STOP"

# Telemetry cadence: print roughly this often (in ticks), never every frame.
TELEMETRY_EVERY_TICKS = 30


class PinchBot(BaseAgent):
    def initialize_agent(self):
        # Called once, after the config is fully loaded. No packet exists yet,
        # so anything that needs live data is set up lazily in get_output().
        self.tick = 0
        self.sequence_start_time = None  # real game time of the first active tick
        self.state = STATE_IDLE
        self.logger.info(
            f"PinchBot Stage 0 initialized (name={self.name!r}, "
            f"index={self.index}, team={self.team})."
        )

    def get_output(self, packet: GameTickPacket) -> SimpleControllerState:
        self.tick += 1

        # --- Identify our own car. self.index is authoritative; validate it
        # against the live packet before indexing (the packet may not be fully
        # populated on the very first ticks). This is a real condition, so we
        # hold still rather than guess -- we do NOT swallow it silently. ---
        if self.index < 0 or self.index >= packet.num_cars:
            controls = SimpleControllerState()
            self._telemetry(packet, car=None, controls=controls, note="no_valid_car")
            return controls

        car = packet.game_cars[self.index]
        info = packet.game_info

        # --- Anchor the sequence clock to the first tick where play is live. ---
        if self.sequence_start_time is None:
            if info.is_round_active:
                self.sequence_start_time = info.seconds_elapsed
            else:
                # Waiting for kickoff countdown to finish. Hold still (safe).
                controls = SimpleControllerState()
                self._telemetry(packet, car, controls, note="waiting_for_round")
                return controls

        elapsed = info.seconds_elapsed - self.sequence_start_time

        # --- Deterministic phase selection purely from elapsed game time. ---
        if elapsed < IDLE_SECONDS:
            self.state = STATE_IDLE
            throttle = 0.0
        elif elapsed < IDLE_SECONDS + THROTTLE_SECONDS:
            self.state = STATE_THROTTLE
            throttle = 1.0
        else:
            self.state = STATE_STOP
            throttle = 0.0

        controls = SimpleControllerState()
        controls.throttle = throttle
        controls.steer = 0.0

        self._telemetry(packet, car, controls, note=f"elapsed={elapsed:.2f}")
        return controls

    # --- Concise telemetry, emitted about every TELEMETRY_EVERY_TICKS ticks. ---
    def _telemetry(self, packet, car, controls, note=""):
        if self.tick % TELEMETRY_EVERY_TICKS != 0:
            return
        info = packet.game_info
        if car is not None:
            p = car.physics.location
            v = car.physics.velocity
            car_pos = f"({p.x:.0f},{p.y:.0f},{p.z:.0f})"
            car_vel = f"({v.x:.0f},{v.y:.0f},{v.z:.0f})"
            car_name = car.name  # already a str (c_wchar array) -- no .decode()
        else:
            car_pos = car_vel = car_name = "n/a"
        b = packet.game_ball.physics.location
        ball_pos = f"({b.x:.0f},{b.y:.0f},{b.z:.0f})"
        print(
            f"[PinchBot] tick={self.tick} state={self.state} "
            f"t={info.seconds_elapsed:.2f} round_active={info.is_round_active} "
            f"name={car_name} car_pos={car_pos} car_vel={car_vel} "
            f"ball_pos={ball_pos} throttle={controls.throttle:.1f} "
            f"steer={controls.steer:.1f} {note}"
        )
