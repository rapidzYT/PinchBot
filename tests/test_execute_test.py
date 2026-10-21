"""Software checks for the first intentional wall-contact attempt."""

import math
from pathlib import Path

import pytest
from rlbot.agents.base_agent import BaseAgent, SimpleControllerState
from rlbot.parsing.bot_config_bundle import get_bot_config_bundle
from rlbot.utils.class_importer import import_class_with_base

import wall_pinch_geometry as geom
from fake_packet import make_packet
from execute_test import (
    ExecuteTest,
    RESULT_POSSIBLE_PINCH,
    STATE_EXECUTE,
    STATE_RECOVER,
    STATE_SEARCH,
    STATE_SETUP,
    STATE_STABILIZE,
    STATE_VERIFY,
)


def make_bot(index=0, team=0):
    bot = ExecuteTest("ExecuteTest", team, index)
    bot.initialize_agent()
    return bot


def make_wall_packet(**kwargs):
    values = {
        "seconds_elapsed": 0.0,
        "is_round_active": True,
        "ball_location": (3900.0, 500.0, 200.0),
        "ball_velocity": (0.0, 0.0, 0.0),
        "car_location": (0.0, 0.0, 17.01),
        "car_velocity": (0.0, 0.0, 0.0),
        "car_rotation": (0.0, 0.0, 0.0),
        "has_wheel_contact": True,
    }
    values.update(kwargs)
    return make_packet(**values)


def test_cfg_imports_and_constructs():
    cfg = Path(__file__).parents[1] / "src" / "execute_test.cfg"
    bundle = get_bot_config_bundle(cfg)
    wrapper = import_class_with_base(bundle.python_file, BaseAgent)
    cls = wrapper.get_loaded_class()
    bot = cls("ExecuteTest", 0, 0)
    bot.initialize_agent()
    out = bot.get_output(make_wall_packet())
    assert isinstance(out, SimpleControllerState)


def test_far_or_invalid_setup_never_drives_at_ball():
    bot = make_bot()
    out = bot.get_output(
        make_wall_packet(ball_location=(0.0, 0.0, 93.0), ball_velocity=(0.0, 0.0, 0.0))
    )
    assert bot.state == STATE_SEARCH
    assert out.throttle == pytest.approx(0.0)
    assert out.steer == pytest.approx(0.0)
    assert bot.last_telemetry["setup_reason"] == "ball_not_near_wall"


def test_fast_wall_approach_starts_prepositioning_early():
    bot = make_bot()
    out = bot.get_output(
        make_wall_packet(
            ball_location=(2203.25, 500.0, 200.0),  # approximately 1800 uu from right wall
            ball_velocity=(800.0, 0.0, 0.0),        # moving toward the right wall
        )
    )
    assert bot.state == STATE_SETUP
    assert out.throttle != pytest.approx(0.0)
    assert bot.last_telemetry["setup_reason"] == "ball_not_near_wall"


def test_fast_wall_approach_uses_bounded_wall_impact_prediction():
    bot = make_bot()
    current_setup = geom.compute_wall_pinch_setup(
        geom.Vec3(2203.25, 500.0, 200.0), geom.Vec3(800.0, 0.0, 0.0), team=0
    )
    bot.get_output(
        make_wall_packet(
            ball_location=(2203.25, 500.0, 200.0),
            ball_velocity=(800.0, 0.0, 0.0),
        )
    )
    assert bot.last_telemetry["prepositioned"] is True
    assert bot.last_target.x > current_setup.approach_point.x + 1000.0
    assert abs(bot.last_target.x) < geom.field.SIDE_WALL_X


def test_viable_aligned_setup_enters_execute():
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
    assert bot.state == STATE_EXECUTE
    assert out.throttle == pytest.approx(1.0)
    assert out.boost is False
    assert bot.last_telemetry["execute_ready"] is True
    assert bot.last_telemetry["execute_distance"] > 250.0


def test_execute_uses_available_boost_for_long_contact_line():
    setup = geom.compute_wall_pinch_setup(
        geom.Vec3(3900.0, 500.0, 200.0), geom.Vec3(0.0, 0.0, 0.0), team=0
    )
    yaw = math.atan2(setup.approach_direction.y, setup.approach_direction.x)
    bot = make_bot()
    out = bot.get_output(
        make_wall_packet(
            car_location=(setup.approach_point.x, setup.approach_point.y, setup.approach_point.z),
            car_rotation=(0.0, yaw, 0.0),
            car_boost=40,
        )
    )
    assert bot.state == STATE_EXECUTE
    assert out.boost is True
    assert bot.last_telemetry["boost_command"] is True


def test_navigation_boost_waits_until_aligned_and_far():
    bot = make_bot()
    car = make_wall_packet(car_boost=40).game_cars[0]
    controls = SimpleControllerState(throttle=1.0)
    bot.state = STATE_SETUP
    bot._maybe_enable_navigation_boost(
        car, controls, {"target_distance": 1600.0, "heading_error": 0.2}
    )
    assert controls.boost is True

    bot.state = STATE_STABILIZE
    controls = SimpleControllerState(throttle=1.0)
    bot._maybe_enable_navigation_boost(
        car, controls, {"target_distance": 1000.0, "heading_error": 0.2}
    )
    assert controls.boost is False

    controls = SimpleControllerState(throttle=1.0)
    bot._maybe_enable_navigation_boost(
        car, controls, {"target_distance": 1600.0, "heading_error": 0.8}
    )
    assert controls.boost is False


def test_braking_arrival_can_enter_execute_before_perfect_stop():
    setup = geom.compute_wall_pinch_setup(
        geom.Vec3(3900.0, 500.0, 200.0), geom.Vec3(0.0, 0.0, 0.0), team=0
    )
    yaw = math.atan2(setup.approach_direction.y, setup.approach_direction.x)
    bot = make_bot()
    out = bot.get_output(
        make_wall_packet(
            car_location=(setup.approach_point.x, setup.approach_point.y, setup.approach_point.z),
            car_velocity=(100.0, 0.0, 0.0),
            car_rotation=(0.0, yaw, 0.0),
        )
    )
    assert bot.state == STATE_EXECUTE
    assert out.throttle == pytest.approx(1.0)
    assert bot.last_telemetry["execute_ready"] is True


def test_aligned_final_approach_can_enter_execute_before_arrival_radius():
    setup = geom.compute_wall_pinch_setup(
        geom.Vec3(3900.0, 500.0, 200.0), geom.Vec3(0.0, 0.0, 0.0), team=0
    )
    yaw = math.atan2(setup.approach_direction.y, setup.approach_direction.x)
    car_location = setup.approach_point - setup.approach_direction * 155.0
    bot = make_bot()
    out = bot.get_output(
        make_wall_packet(
            car_location=(car_location.x, car_location.y, car_location.z),
            car_rotation=(0.0, yaw, 0.0),
        )
    )
    assert bot.state == STATE_EXECUTE
    assert out.throttle == pytest.approx(1.0)
    assert bot.last_telemetry["execute_ready"] is True


def test_misaligned_setup_stabilizes_before_execute():
    setup = geom.compute_wall_pinch_setup(
        geom.Vec3(3900.0, 500.0, 200.0), geom.Vec3(0.0, 0.0, 0.0), team=0
    )
    bot = make_bot()
    out = bot.get_output(
        make_wall_packet(
            car_location=(setup.approach_point.x, setup.approach_point.y, setup.approach_point.z),
            car_rotation=(0.0, 0.0, 0.0),
        )
    )
    assert bot.state == STATE_STABILIZE
    assert out.throttle == pytest.approx(0.25)
    assert abs(out.steer) > 0.5
    assert bot.last_telemetry["execute_ready"] is False


def test_stabilization_timeout_enters_recovery():
    bot = make_bot()
    out = bot.get_output(make_wall_packet(seconds_elapsed=0.0))
    assert bot.state == STATE_STABILIZE
    assert out.throttle == pytest.approx(1.0)

    out = bot.get_output(make_wall_packet(seconds_elapsed=8.1))
    assert bot.state == STATE_RECOVER
    assert out.throttle == pytest.approx(0.0)
    assert bot.last_telemetry["setup_reason"] == "stabilize_timeout"


def test_contact_line_enters_verify_then_classifies_possible_pinch():
    setup = geom.compute_wall_pinch_setup(
        geom.Vec3(3900.0, 500.0, 200.0), geom.Vec3(0.0, 0.0, 0.0), team=0
    )
    yaw = math.atan2(setup.approach_direction.y, setup.approach_direction.x)
    bot = make_bot()
    bot.get_output(
        make_wall_packet(
            car_location=(setup.approach_point.x, setup.approach_point.y, setup.approach_point.z),
            car_rotation=(0.0, yaw, 0.0),
        )
    )
    execute_target = bot.execute_target

    # The car reaches the predicted contact-center line.  This is the first
    # intentional-contact path; output becomes neutral while VERIFY observes.
    out = bot.get_output(
        make_wall_packet(
            seconds_elapsed=0.25,
            car_location=(execute_target.x, execute_target.y, execute_target.z),
            car_rotation=(0.0, yaw, 0.0),
            ball_velocity=(0.0, 1000.0, 0.0),
        )
    )
    assert bot.state == STATE_VERIFY
    assert out.throttle == pytest.approx(0.0)

    out = bot.get_output(
        make_wall_packet(
            seconds_elapsed=0.60,
            car_location=(execute_target.x, execute_target.y, execute_target.z),
            car_rotation=(0.0, yaw, 0.0),
            ball_velocity=(0.0, 1000.0, 0.0),
        )
    )
    assert bot.state == STATE_RECOVER
    assert bot.result == RESULT_POSSIBLE_PINCH
    assert out.throttle == pytest.approx(0.0)


def test_execute_controls_are_finite_and_bounded():
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
    assert bot.state == STATE_EXECUTE
    assert -1.0 <= out.throttle <= 1.0
    assert -1.0 <= out.steer <= 1.0
    assert math.isfinite(out.throttle)
    assert math.isfinite(out.steer)


def test_execute_pulse_does_not_expire_before_stationary_car_can_reach_line():
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
            seconds_elapsed=0.50,
            car_location=(setup.approach_point.x, setup.approach_point.y, setup.approach_point.z),
            car_rotation=(0.0, yaw, 0.0),
        )
    )
    assert bot.state == STATE_EXECUTE
    assert out.throttle == pytest.approx(1.0)

