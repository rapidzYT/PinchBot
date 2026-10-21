"""
Pytest configuration.

RLBot loads the bot by inserting the bot file's own directory (src/) onto
sys.path and importing it by module name. We replicate that here so tests
import `bot` and its future sibling modules exactly the way the framework does.
"""

import os
import sys

SRC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)
