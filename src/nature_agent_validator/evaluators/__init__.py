"""Evaluator Provider -- the *future* extension boundary for semantic checks.

Phase 0 ships **no** evaluator implementation and requires none. This module
exists only to fix the interface so that deterministic validation (the MVP
foundation) and any later semantic evaluation share one contract.

Principles (see ``docs/product-boundary.md``):

* P0-1  No-model-first -- the core Validator works with nothing from this module.
* P0-2  Model optional -- an evaluator model may plug in here later, but no
        evaluator model may ever become a required core dependency.

No third-party evaluator (DeepEval, Claude, OpenAI, DeepSeek, ...) is imported
or integrated here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class EvaluationRequest:
    """Inputs handed to an evaluator for one semantic judgment."""

    scenario_id: str
    #: Natural-language description of what "good" looks like.
    criterion: str
    #: The observed agent output under evaluation.
    observed_text: str
    #: Optional supporting material (request payload, evidence summary, ...).
    context: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "context", MappingProxyType(dict(self.context)))


@dataclass(frozen=True, slots=True)
class EvaluationVerdict:
    """An evaluator's answer for one :class:`EvaluationRequest`."""

    passed: bool
    score: float | None = None
    rationale: str = ""
    #: Identifier of the provider that produced this verdict.
    provider: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "score": self.score,
            "rationale": self.rationale,
            "provider": self.provider,
        }


@runtime_checkable
class EvaluatorProvider(Protocol):
    """Anything that can turn an :class:`EvaluationRequest` into a verdict."""

    name: str

    def evaluate(self, request: EvaluationRequest) -> EvaluationVerdict: ...


__all__ = [
    "EvaluationRequest",
    "EvaluationVerdict",
    "EvaluatorProvider",
]
