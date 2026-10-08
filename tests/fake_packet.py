"""
Test helper: build a real rlbot GameTickPacket (the actual ctypes struct) and
populate the fields Stage 0 reads. Using the genuine struct -- not a mock --
means our tests exercise the same field types and layout the live game uses.
"""

from rlbot.utils.structures.game_data_struct import GameTickPacket


def make_packet(
    index: int = 0,
    num_cars: int = 1,
    seconds_elapsed: float = 0.0,
    is_round_active: bool = True,
    frame_num: int = 0,
    car_location=(0.0, 0.0, 17.01),
    car_velocity=(0.0, 0.0, 0.0),
    car_rotation=(0.0, 0.0, 0.0),   # (pitch, yaw, roll) in radians
    ball_location=(0.0, 0.0, 92.75),
    car_name: str = "PinchBot",
    car_team: int = 0,
    has_wheel_contact: bool = True,
) -> GameTickPacket:
    """Create a GameTickPacket with one or more cars populated."""
    packet = GameTickPacket()
    packet.num_cars = num_cars

    if 0 <= index < num_cars:
        car = packet.game_cars[index]
        car.physics.location.x, car.physics.location.y, car.physics.location.z = car_location
        car.physics.velocity.x, car.physics.velocity.y, car.physics.velocity.z = car_velocity
        car.physics.rotation.pitch, car.physics.rotation.yaw, car.physics.rotation.roll = car_rotation
        car.name = car_name           # c_wchar array accepts a python str directly
        car.team = car_team
        car.has_wheel_contact = has_wheel_contact

    ball = packet.game_ball
    ball.physics.location.x, ball.physics.location.y, ball.physics.location.z = ball_location

    info = packet.game_info
    info.seconds_elapsed = seconds_elapsed
    info.is_round_active = is_round_active
    info.frame_num = frame_num

    return packet
