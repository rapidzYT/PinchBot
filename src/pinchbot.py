"""Integrated PinchBot setup controller.

This is the main bot loaded by ``pinch_bot.cfg``. It reuses the tested live
wall-pinch SEARCH/SETUP/STABILIZE pipeline, including early pre-positioning,
bounded wall-impact prediction, and conditional boost. Intentional contact is
disabled here until this combined setup behavior is physically reliable.

The original ``bot.py`` remains the frozen Stage 0 foundation regression.
"""

from execute_test import ExecuteTest


class PinchBot(ExecuteTest):
    """Create and hold live pinch setups; do not execute the pinch yet."""

    ALLOW_EXECUTE = False
    CREATE_SETUP = True
