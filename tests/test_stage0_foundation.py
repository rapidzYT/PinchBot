"""
Stage 0 foundation -- software validation.

These tests prove the SOFTWARE contract of the foundation:
  * the bot imports and constructs with the real BaseAgent signature,
  * it always returns a SimpleControllerState with in-range values,
  * the deterministic IDLE -> THROTTLE -> STOP sequence is correct,
  * the sequence is anchored to the round going live,
  * it identifies its own car by self.index and survives an invalid index,
  * packet fields it reads have the types we expect (name is str, not bytes).

They do NOT prove the car physically moves in Rocket League -- that requires a
real RLBot GUI test (see README). Passing here is necessary, not sufficient.
"""

import math

import pytest
from rlbot.agents.base_agent import SimpleControllerState

from bot import (
    PinchBot,
    IDLE_SECONDS,
    THROTTLE_SECONDS,
    STATE_IDLE,
    STATE_THROTTLE,
    STATE_STOP,
)
from fake_packet import make_packet


def make_bot(index: int = 0, team: int = 0, name: str = "PinchBot") -> PinchBot:
    bot = PinchBot(name, team, index)
    bot.initialize_agent()
    return bot


# --- Construction / API contract ---------------------------------------------

def test_constructs_with_real_baseagent_signature():
    bot = make_bot(index=2, team=1, name="PinchBot")
    assert bot.name == "PinchBot"
    assert bot.index == 2
    assert bot.team == 1
    assert bot.tick == 0
    assert bot.sequence_start_time is None
    assert bot.state == STATE_IDLE


def test_team_and_index_are_independent():
    # self.team != self.index -- a classic bug source. Confirm they are distinct
    # and that the bot reads its car from game_cars[self.index], not [self.team].
    bot = make_bot(index=1, team=0, name="PinchBot")
    packet = make_packet(index=1, num_cars=2, is_round_active=True)
    packet.game_cars[1].physics.velocity.x = 123.0
    out = bot.get_output(packet)
    assert isinstance(out, SimpleControllerState)
    assert bot.index == 1 and bot.team == 0


def test_get_output_returns_simple_controller_state():
    bot = make_bot()
    out = bot.get_output(make_packet())
    assert isinstance(out, SimpleControllerState)


# --- Deterministic phase logic (anchor set manually to isolate boundaries) ----

@pytest.mark.parametrize(
    "elapsed, expected_state, expected_throttle",
    [
        (0.0, STATE_IDLE, 0.0),
        (IDLE_SECONDS - 0.01, STATE_IDLE, 0.0),
        (IDLE_SECONDS + 0.01, STATE_THROTTLE, 1.0),
        (IDLE_SECONDS + THROTTLE_SECONDS - 0.01, STATE_THROTTLE, 1.0),
        (IDLE_SECONDS + THROTTLE_SECONDS + 0.01, STATE_STOP, 0.0),
        (IDLE_SECONDS + THROTTLE_SECONDS + 10.0, STATE_STOP, 0.0),
    ],
)
def test_phase_boundaries(elapsed, expected_state, expected_throttle):
    bot = make_bot()
    bot.sequence_start_time = 100.0  # pretend the round went live at t=100
    packet = make_packet(seconds_elapsed=100.0 + elapsed, is_round_active=True)
    out = bot.get_output(packet)
    assert bot.state == expected_state
    assert out.throttle == pytest.approx(expected_throttle)
    assert out.steer == pytest.approx(0.0)  # Stage 0 is longitudinal only


# --- Anchoring to round-active ------------------------------------------------

def test_sequence_waits_until_round_active():
    bot = make_bot()
    # Round not active yet: hold still, do not anchor the clock.
    out = bot.get_output(make_packet(seconds_elapsed=50.0, is_round_active=False))
    assert bot.sequence_start_time is None
    assert out.throttle == pytest.approx(0.0)

    # Round goes live: anchor at this tick's game time, begin in IDLE.
    out = bot.get_output(make_packet(seconds_elapsed=50.0, is_round_active=True))
    assert bot.sequence_start_time == pytest.approx(50.0)
    assert bot.state == STATE_IDLE
    assert out.throttle == pytest.approx(0.0)


def test_full_sequence_over_time():
    bot = make_bot()
    t0 = 200.0
    # First active tick anchors + IDLE.
    assert bot.get_output(make_packet(seconds_elapsed=t0, is_round_active=True)).throttle == 0.0
    assert bot.state == STATE_IDLE
    # Into throttle window.
    assert bot.get_output(
        make_packet(seconds_elapsed=t0 + IDLE_SECONDS + 0.1, is_round_active=True)
    ).throttle == pytest.approx(1.0)
    assert bot.state == STATE_THROTTLE
    # Past throttle window -> stop.
    assert bot.get_output(
        make_packet(seconds_elapsed=t0 + IDLE_SECONDS + THROTTLE_SECONDS + 0.1, is_round_active=True)
    ).throttle == pytest.approx(0.0)
    assert bot.state == STATE_STOP


# --- Robustness ---------------------------------------------------------------

def test_invalid_index_is_safe_and_neutral():
    # self.index beyond num_cars: must not raise, must return neutral controls.
    bot = make_bot(index=5)
    out = bot.get_output(make_packet(index=0, num_cars=1, is_round_active=True))
    assert isinstance(out, SimpleControllerState)
    assert out.throttle == pytest.approx(0.0)
    assert out.steer == pytest.approx(0.0)
    assert bot.sequence_start_time is None  # never anchored without a valid car


def test_controls_always_in_range_across_sequence():
    bot = make_bot()
    t0 = 0.0
    for i in range(200):
        out = bot.get_output(
            make_packet(seconds_elapsed=t0 + i * 0.1, is_round_active=True)
        )
        assert -1.0 <= out.throttle <= 1.0
        assert -1.0 <= out.steer <= 1.0
        for v in (out.throttle, out.steer):
            assert math.isfinite(v)


# --- Packet compatibility -----------------------------------------------------

def test_car_name_is_str_not_bytes():
    # PlayerInfo.name is a c_wchar array -> python str. Guards against the
    # classic ".decode() on a str" bug.
    packet = make_packet(car_name="PinchBot")
    name = packet.game_cars[0].name
    assert isinstance(name, str)
    assert name == "PinchBot"


def test_team_field_is_int_like():
    packet = make_packet(car_team=1)
    assert int(packet.game_cars[0].team) == 1
