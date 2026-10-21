"""Integrated PinchBot goal-directed wall-pinch controller.

This is the main bot loaded by ``pinch_bot.cfg``. It reuses the tested live
wall-pinch SEARCH/SETUP/STABILIZE pipeline, including early pre-positioning,
bounded wall-impact prediction, and conditional boost. It then attempts one
bounded goal-directed contact and verifies the ball response.

The original ``bot.py`` remains the frozen Stage 0 foundation regression.
"""

from execute_test import ExecuteTest


class PinchBot(ExecuteTest):
    """Create a goal-directed wall setup and attempt one verified pinch."""

    ALLOW_EXECUTE = True
    CREATE_SETUP = True
    GOAL_DIRECTED = True
