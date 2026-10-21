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
