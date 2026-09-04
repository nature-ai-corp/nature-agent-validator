"""Exception hierarchy for NATURE Agent Validator.

Validator-side failures (bad configuration, adapter transport errors, broken
assertion definitions) are represented as exceptions and surface in a
``ValidationResult`` as ``ERROR`` -- they are never reported as a failed
assertion. See ``docs/architecture.md`` (Outcome model).
"""

from __future__ import annotations


class NatureValidatorError(Exception):
    """Base class for every error raised by this package."""


class ScenarioError(NatureValidatorError):
    """A scenario could not be parsed, loaded, or is structurally invalid."""


class AdapterError(NatureValidatorError):
    """A target adapter could not be built or failed to produce a response."""


class AssertionConfigError(NatureValidatorError):
    """An assertion specification is missing required configuration or is malformed."""


class UnknownAssertionType(NatureValidatorError):
    """No assertion implementation is registered for the requested type name."""


class EvidenceError(NatureValidatorError):
    """Optional evidence supplied by a target could not be parsed or is
    structurally invalid.

    Malformed optional evidence is never silently downgraded to "no evidence":
    it is surfaced (as ``ERROR`` via the runner) so it cannot be mistaken for
    trusted evidence.
    """


__all__ = [
    "NatureValidatorError",
    "ScenarioError",
    "AdapterError",
    "AssertionConfigError",
    "UnknownAssertionType",
    "EvidenceError",
]
