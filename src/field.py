"""
Verified Rocket League field / object constants (Soccar), in unreal units (uu).

Sources (NOT memory):
  * RLBot wiki "Useful Game Values" -- field extents, ceiling, ball radius, goal size.
  * Installed rlbot 1.68 packet / observed car rest height.
These are the authoritative numbers the wall-pinch geometry derives from. Octane
hitbox dimensions are the widely-published approximate values and are labelled as
approximate; they are only used for standoffs/clearances, never for exact contact.
"""

# --- Field extents (walls are planes at these coordinates) ---
SIDE_WALL_X = 4096.0     # side walls at x = +/- SIDE_WALL_X (RIGHT = +, LEFT = -)
BACK_WALL_Y = 5120.0     # back walls / goal lines at y = +/- BACK_WALL_Y
CEILING_Z = 2044.0       # ceiling plane
FLOOR_Z = 0.0

# --- Goal (to avoid aiming a "wall" pinch into the open goal mouth) ---
GOAL_HALF_WIDTH = 892.755   # center-to-post
GOAL_HEIGHT = 642.775

# --- Ball ---
BALL_RADIUS = 92.75

# --- Octane car (approximate published hitbox; empirical) ---
CAR_REST_Z = 17.01       # resting height of the car's center on flat ground
OCTANE_LENGTH = 118.0    # approx
OCTANE_WIDTH = 84.2      # approx
OCTANE_HEIGHT = 36.16    # approx
CAR_HALF_LENGTH = OCTANE_LENGTH / 2.0  # ~59 uu, used for standoffs

# Team attack direction along y: team 0 (blue) attacks +y, team 1 (orange) attacks -y.
def attack_sign(team: int) -> float:
    """+1 if this team attacks toward +y, -1 toward -y."""
    return 1.0 if team == 0 else -1.0
