"""Software checks for the zero-contact wall-pinch stabilization bot.

These tests prove packet handling, live setup selection, ground navigation to the
approach point, neutral handling for rejected setups, and recovery from a
measured convergence regression.  They do not prove physical Rocket League
arrival; that still requires the RLBot GUI procedure in README.md.
"""

import math
from pathlib import Path

import pytest
from rlbot.agents.base_agent import SimpleControllerState
from rlbot.agents.base_agent import BaseAgent
from rlbot.parsing.bot_config_bundle import get_bot_config_bundle
from rlbot.utils.class_importer import import_class_with_base

import wall_pinch_geometry as geom
from fake_packet import make_packet
from stabilize_test import (
    StabilizeTest,
    STATE_HOLD,
    STATE_RECOVER,
    STATE_SEARCH,
    STATE_SETUP,
    STATE_STABILIZE,
    STATE_WAIT,
)


def make_bot(index=0, team=0):
    bot = StabilizeTest("StabilizeTest", team, index)
    bot.initialize_agent()
    return bot


def viable_packet(**kwargs):
    values = {
        "seconds_elapsed": 0.0,
        "is_round_active": True,
        "ball_location": (3900.0, 500.0, 200.0),
        "ball_velocity": (0.0, 0.0, 0.0),
        "car_location": (0.0, 0.0, 17.01),
        "car_velocity": (0.0, 0.0, 0.0),
        "car_rotation": (0.0, 0.0, 0.0),
    }
    values.update(kwargs)
    return make_packet(**values)


def test_initialization_and_wait_state():
    bot = make_bot()
    assert bot.state == STATE_WAIT
    out = bot.get_output(viable_packet(is_round_active=False))
    assert isinstance(out, SimpleControllerState)
    assert bot.state == STATE_WAIT
    assert out.throttle == pytest.approx(0.0)
    assert out.steer == pytest.approx(0.0)
    assert bot.last_telemetry["setup_reason"] == "round_inactive"


def test_rlbot_cfg_imports_and_constructs():
    cfg = Path(__file__).parents[1] / "src" / "stabilize_test.cfg"
    bundle = get_bot_config_bundle(cfg)
    wrapper = import_class_with_base(bundle.python_file, BaseAgent)
    cls = wrapper.get_loaded_class()
    bot = cls("StabilizeTest", 0, 0)
    bot.initialize_agent()
    out = bot.get_output(viable_packet())
    assert isinstance(out, SimpleControllerState)


def test_viable_setup_drives_to_approach_point_not_contact_point():
    bot = make_bot(team=0)
    packet = viable_packet()
    out = bot.get_output(packet)

    setup = geom.compute_wall_pinch_setup(
        geom.Vec3(3900.0, 500.0, 200.0), geom.Vec3(0.0, 0.0, 0.0), team=0
    )
    assert setup.viable
    assert bot.state == STATE_STABILIZE
    assert isinstance(out, SimpleControllerState)
    assert out.throttle == pytest.approx(1.0)
    assert out.steer > 0.0  # approach point is forward-right from this start
    assert bot.last_telemetry["target"] == pytest.approx(
        (setup.approach_point.x, setup.approach_point.y, setup.approach_point.z)
    )
    assert bot.last_telemetry["target"] != pytest.approx(
        (setup.contact_point.x, setup.contact_point.y, setup.contact_point.z)
    )
    assert bot.last_telemetry["setup_viable"] is True
    assert bot.last_telemetry["ball_wall_gap"] == pytest.approx(103.25, abs=0.01)


def test_prepositions_for_ball_moving_into_wall_before_viable_gate():
    # Right-wall ball: +x velocity moves it toward x=+4096.  The strict
    # geometry gate still rejects this 400-uu gap, but SETUP may safely use the
    # finite approach point to start closing the distance early.
    ball_x = 4096.0 - 92.75 - 400.0
    bot = make_bot(team=0)
    out = bot.get_output(
        viable_packet(
            ball_location=(ball_x, 500.0, 200.0),
            ball_velocity=(300.0, 0.0, 0.0),
        )
    )
    assert bot.state == STATE_SETUP
    assert out.throttle == pytest.approx(1.0)
    assert bot.last_telemetry["setup_viable"] is False
    assert bot.last_telemetry["setup_reason"] == "ball_not_near_wall"
    assert bot.last_telemetry["wall_velocity"] == pytest.approx(-300.0)


def test_stationary_off_wall_ball_is_not_prepositioned():
    ball_x = 4096.0 - 92.75 - 400.0
    bot = make_bot(team=0)
    out = bot.get_output(
        viable_packet(
            ball_location=(ball_x, 500.0, 200.0),
            ball_velocity=(0.0, 0.0, 0.0),
        )
    )
    assert bot.state == STATE_SEARCH
    assert out.throttle == pytest.approx(0.0)
    assert bot.last_telemetry["setup_reason"] == "ball_not_near_wall"


def test_arrived_at_setup_holds_neutral_without_contact():
    setup = geom.compute_wall_pinch_setup(
        geom.Vec3(3900.0, 500.0, 200.0), geom.Vec3(0.0, 0.0, 0.0), team=0
    )
    bot = make_bot(team=0)
    out = bot.get_output(
        viable_packet(
            car_location=(setup.approach_point.x, setup.approach_point.y, setup.approach_point.z)
        )
    )
    assert bot.state == STATE_HOLD
    assert out.throttle == pytest.approx(0.0)
    assert out.steer == pytest.approx(0.0)
    assert bot.last_telemetry["target_distance"] < 0.001


def test_rejected_geometry_holds_still_and_reports_reason():
    bot = make_bot()
    out = bot.get_output(
        viable_packet(ball_location=(0.0, 0.0, 93.0), ball_velocity=(0.0, 0.0, 0.0))
    )
    assert bot.state == STATE_SEARCH
    assert out.throttle == pytest.approx(0.0)
    assert out.steer == pytest.approx(0.0)
    assert bot.last_telemetry["setup_reason"] == "ball_not_near_wall"
    assert bot.last_telemetry["setup_viable"] is False


def test_repeated_distance_regression_enters_neutral_recovery():
    bot = make_bot()
    for i, x in enumerate((0.0, -100.0, -200.0, -300.0, -400.0), start=0):
        out = bot.get_output(
            viable_packet(
                seconds_elapsed=i * 0.21,
                car_location=(x, 0.0, 17.01),
            )
        )

    assert bot.state == STATE_RECOVER
    assert out.throttle == pytest.approx(0.0)
    assert out.steer == pytest.approx(0.0)
    assert bot.last_telemetry["setup_reason"] == "progress_diverged"

    # The recovery window expires against game time, then a fresh viable setup
    # starts a new stabilization attempt rather than advancing to EXECUTE.
    out = bot.get_output(viable_packet(seconds_elapsed=1.30, car_location=(-400.0, 0.0, 17.01)))
    assert bot.state == STATE_STABILIZE
    assert out.throttle >= 0.0


def test_invalid_index_is_safe_and_neutral():
    bot = make_bot(index=2)
    out = bot.get_output(make_packet(index=0, num_cars=1, is_round_active=True))
    assert isinstance(out, SimpleControllerState)
    assert bot.state == STATE_SEARCH
    assert out.throttle == pytest.approx(0.0)
    assert out.steer == pytest.approx(0.0)


def test_controls_remain_finite_and_in_range():
    bot = make_bot()
    for i in range(30):
        out = bot.get_output(
            viable_packet(
                seconds_elapsed=i / 120.0,
                car_location=(i * 20.0, i * 5.0, 17.01),
                car_velocity=(300.0, 60.0, 0.0),
            )
        )
        assert -1.0 <= out.throttle <= 1.0
        assert -1.0 <= out.steer <= 1.0
        assert math.isfinite(out.throttle)
        assert math.isfinite(out.steer)
        assert out.boost is False
