"""Software checks for the integrated PinchBot setup-only controller."""

import math
from pathlib import Path

import pytest
from rlbot.agents.base_agent import BaseAgent, SimpleControllerState
from rlbot.parsing.bot_config_bundle import get_bot_config_bundle
from rlbot.utils.class_importer import import_class_with_base

import wall_pinch_geometry as geom
from fake_packet import make_packet
from pinchbot import PinchBot


def make_wall_packet(**kwargs):
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


def make_bot():
    bot = PinchBot("PinchBot", 0, 0)
    bot.initialize_agent()
    return bot


def test_main_cfg_loads_integrated_setup_bot():
    cfg = Path(__file__).parents[1] / "src" / "pinch_bot.cfg"
    bundle = get_bot_config_bundle(cfg)
    wrapper = import_class_with_base(bundle.python_file, BaseAgent)
    cls = wrapper.get_loaded_class()
    bot = cls("PinchBot", 0, 0)
    bot.initialize_agent()
    assert isinstance(bot, PinchBot)
    assert bot.ALLOW_EXECUTE is False
    assert isinstance(bot.get_output(make_wall_packet()), SimpleControllerState)


def test_integrated_bot_holds_ready_setup_without_contact():
    setup = geom.compute_wall_pinch_setup(
        geom.Vec3(3900.0, 500.0, 200.0), geom.Vec3(0.0, 0.0, 0.0), team=0
    )
    yaw = math.atan2(setup.approach_direction.y, setup.approach_direction.x)
    bot = make_bot()
    out = bot.get_output(
        make_wall_packet(
            car_location=(setup.approach_point.x, setup.approach_point.y, setup.approach_point.z),
            car_rotation=(0.0, yaw, 0.0),
        )
    )
    assert bot.state == "STABILIZE"
    assert bot.last_telemetry["setup_viable"] is True
    assert bot.last_telemetry["execute_ready"] is True
    assert bot.execute_target is None
    assert out.throttle == pytest.approx(0.0)
    assert out.steer == pytest.approx(0.0)


def test_integrated_bot_creates_setup_from_midfield():
    bot = make_bot()
    out = bot.get_output(
        make_wall_packet(
            ball_location=(0.0, 0.0, 93.0),
            ball_velocity=(0.0, 0.0, 0.0),
            car_location=(-1200.0, 0.0, 17.01),
            car_rotation=(0.0, 0.0, 0.0),
        )
    )
    assert bot.state == "CREATE_SETUP"
    assert bot.creation_target is not None
    assert bot.last_telemetry["setup_viable"] is False
    assert bot.last_telemetry["state"] == "CREATE_SETUP"
    assert out.throttle != pytest.approx(0.0)


def test_integrated_bot_pushes_toward_selected_wall_when_behind_ball():
    bot = make_bot()
    out = bot.get_output(
        make_wall_packet(
            ball_location=(0.0, 0.0, 93.0),
            ball_velocity=(0.0, 0.0, 0.0),
            car_location=(-180.0, 0.0, 17.01),
            car_rotation=(0.0, 0.0, 0.0),
            car_boost=40,
        )
    )
    assert bot.state == "CREATE_SETUP"
    assert out.throttle == pytest.approx(1.0)
    assert out.boost is True
    assert bot.last_telemetry["handbrake"] is False


def test_integrated_bot_latches_wall_direction_during_one_setup_attempt():
    setup = geom.compute_wall_pinch_setup(
        geom.Vec3(3900.0, 500.0, 200.0), geom.Vec3(0.0, 1000.0, 0.0), team=0
    )
    yaw = math.atan2(setup.approach_direction.y, setup.approach_direction.x)
    bot = make_bot()
    bot.get_output(
        make_wall_packet(
            ball_velocity=(0.0, 1000.0, 0.0),
            car_location=(setup.approach_point.x, setup.approach_point.y, setup.approach_point.z),
            car_rotation=(0.0, yaw, 0.0),
        )
    )
    first_target = bot.last_target
    bot.get_output(
        make_wall_packet(
            ball_velocity=(0.0, -1000.0, 0.0),
            car_location=(setup.approach_point.x, setup.approach_point.y, setup.approach_point.z),
            car_rotation=(0.0, yaw, 0.0),
        )
    )
    assert bot.state == "STABILIZE"
    assert bot.last_target.y == pytest.approx(first_target.y)
    assert bot.last_telemetry["tangent_latched"] is True


def test_integrated_bot_pauses_before_recreating_a_lost_setup():
    setup = geom.compute_wall_pinch_setup(
        geom.Vec3(3900.0, 500.0, 200.0), geom.Vec3(0.0, 0.0, 0.0), team=0
    )
    yaw = math.atan2(setup.approach_direction.y, setup.approach_direction.x)
    bot = make_bot()
    bot.get_output(
        make_wall_packet(
            seconds_elapsed=0.0,
            car_location=(setup.approach_point.x, setup.approach_point.y, setup.approach_point.z),
            car_rotation=(0.0, yaw, 0.0),
        )
    )
    out = bot.get_output(
        make_wall_packet(
            seconds_elapsed=0.1,
            ball_location=(0.0, 0.0, 93.0),
            car_location=(setup.approach_point.x, setup.approach_point.y, setup.approach_point.z),
            car_rotation=(0.0, yaw, 0.0),
        )
    )
    assert bot.state == "SEARCH"
    assert bot.last_telemetry["setup_reason"] == "setup_lost_recovery"
    assert out.throttle == pytest.approx(0.0)


def test_integrated_bot_disables_powerslide_near_moving_ball():
    bot = make_bot()
    out = bot.get_output(
        make_wall_packet(
            ball_location=(0.0, 0.0, 93.0),
            car_location=(-20.0, 0.0, 17.01),
            car_velocity=(0.0, 500.0, 0.0),
            car_rotation=(0.0, math.pi / 2.0, 0.0),
        )
    )
    assert bot.state == "CREATE_SETUP"
    assert bot.last_telemetry["creation_slide_guard"] is True
    assert out.handbrake is False


def test_integrated_bot_disables_powerslide_near_live_setup_point():
    setup = geom.compute_wall_pinch_setup(
        geom.Vec3(3900.0, 500.0, 200.0), geom.Vec3(0.0, 0.0, 0.0), team=0
    )
    bot = make_bot()
    out = bot.get_output(
        make_wall_packet(
            car_location=(setup.approach_point.x, setup.approach_point.y - 400.0, setup.approach_point.z),
            car_velocity=(500.0, 0.0, 0.0),
            car_rotation=(0.0, 0.0, 0.0),
        )
    )
    assert bot.state == "STABILIZE"
    assert bot.last_telemetry["stabilize_slide_guard"] is True
    assert out.handbrake is False
