"""NATURE Agent Validator -- a standalone agent validation framework.

It answers one question: **"Did the Agent behave as expected?"**

The core engine is deterministic. It requires no LLM, no evaluator model, no
network access, and no container runtime. If a target environment exposes
structured evidence, validation depth increases -- but it is the *same* engine,
not a second mode.

See ``docs/product-boundary.md`` for what this project is and is not, and
``docs/architecture.md`` for the component boundaries.
"""

from __future__ import annotations

from nature_agent_validator.adapters import (
    AdapterResponse,
    NormalizedResult,
    StaticAdapter,
    TargetAdapter,
)
from nature_agent_validator.assertions import (
    Assertion,
    AssertionContext,
    AssertionOutcome,
    AssertionResult,
    AssertionSpec,
    build_assertion,
)
from nature_agent_validator.errors import (
    AdapterError,
    AssertionConfigError,
    NatureValidatorError,
    ScenarioError,
    UnknownAssertionType,
)
from nature_agent_validator.evaluators import (
    EvaluationRequest,
    EvaluationVerdict,
    EvaluatorProvider,
)
from nature_agent_validator.evidence import (
    EVIDENCE_CONTRACT_VERSION,
    EvidenceEvent,
    EvidenceRecord,
)
from nature_agent_validator.reporting import (
    EvidenceSummary,
    ExecutionMetadata,
    OverallStatus,
    ValidationResult,
)
from nature_agent_validator.runner import Runner
from nature_agent_validator.scenario import Scenario, ScenarioRequest, ScenarioTarget

__version__ = "0.0.1"

__all__ = [
    "__version__",
    # scenario
    "Scenario",
    "ScenarioRequest",
    "ScenarioTarget",
    # adapters
    "AdapterResponse",
    "NormalizedResult",
    "StaticAdapter",
    "TargetAdapter",
    # assertions
    "Assertion",
    "AssertionContext",
    "AssertionOutcome",
    "AssertionResult",
    "AssertionSpec",
    "build_assertion",
    # evidence
    "EVIDENCE_CONTRACT_VERSION",
    "EvidenceEvent",
    "EvidenceRecord",
    # evaluators
    "EvaluationRequest",
    "EvaluationVerdict",
    "EvaluatorProvider",
    # reporting
    "EvidenceSummary",
    "ExecutionMetadata",
    "OverallStatus",
    "ValidationResult",
    # runner
    "Runner",
    # errors
    "NatureValidatorError",
    "ScenarioError",
    "AdapterError",
    "AssertionConfigError",
    "UnknownAssertionType",
]
