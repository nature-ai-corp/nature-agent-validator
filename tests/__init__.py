"""Test suite for NATURE Agent Validator.

Adds ``src/`` to ``sys.path`` so ``python -m unittest`` works whether or not the
package has been installed (``pip install -e .``).
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"
