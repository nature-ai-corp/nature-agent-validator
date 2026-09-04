"""Target adapters -- the boundary between the Validator and a target system."""

from __future__ import annotations

from .base import AdapterResponse, TargetAdapter
from .registry import available_adapter_names, build_adapter
from .result import NormalizedResult
from .static import StaticAdapter

__all__ = [
    "AdapterResponse",
    "NormalizedResult",
    "StaticAdapter",
    "TargetAdapter",
    "available_adapter_names",
    "build_adapter",
]
