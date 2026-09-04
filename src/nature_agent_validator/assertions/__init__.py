"""Assertion abstraction, result types, and the built-in deterministic checks.

Importing this package records every built-in assertion type in a private
table. Phase 0 exposes no public registration API; the only supported entry
point is the :func:`build_assertion` factory.
"""

from __future__ import annotations

from .base import Assertion
from .context import AssertionContext
from .registry import build_assertion
from .result import AssertionOutcome, AssertionResult
from .spec import AssertionSpec

# Side-effect import: populates the internal table with built-in assertion types.
from . import builtin as _builtin  # noqa: E402,F401

__all__ = [
    "Assertion",
    "AssertionContext",
    "AssertionOutcome",
    "AssertionResult",
    "AssertionSpec",
    "build_assertion",
]
