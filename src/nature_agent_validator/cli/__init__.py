"""Command-line interface for NATURE Agent Validator.

Phase 0 implements a single command -- ``nav validate`` -- enough to prove the
package end to end. Command surface and naming are not frozen.
"""

from __future__ import annotations

from .main import main

__all__ = ["main"]
