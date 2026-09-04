"""The :class:`Assertion` abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar, Mapping

from .context import AssertionContext
from .result import AssertionOutcome, AssertionResult
from .spec import AssertionSpec


class Assertion(ABC):
    """A single deterministic check over an :class:`AssertionContext`.

    Subclasses set the class variable ``type`` and implement :meth:`evaluate`.
    They are constructed from an :class:`AssertionSpec` and must be stateless
    beyond their configuration.
    """

    type: ClassVar[str] = ""

    def __init__(self, assertion_id: str, config: Mapping[str, Any]) -> None:
        self.assertion_id = assertion_id
        self.config: Mapping[str, Any] = dict(config)

    @classmethod
    def from_spec(cls, spec: AssertionSpec) -> "Assertion":
        return cls(spec.assertion_id, spec.config)

    @abstractmethod
    def evaluate(self, context: AssertionContext) -> AssertionResult:
        """Return a structured verdict. Must not raise for ordinary failure."""

    # -- helpers -----------------------------------------------------------

    def _outcome(
        self,
        outcome: AssertionOutcome,
        *,
        expected: Any = None,
        observed: Any = None,
        message: str = "",
    ) -> AssertionResult:
        return AssertionResult(
            assertion_id=self.assertion_id,
            type=self.type,
            outcome=outcome,
            expected=expected,
            observed=observed,
            message=message,
        )

    def _pass(self, **kw: Any) -> AssertionResult:
        return self._outcome(AssertionOutcome.PASS, **kw)

    def _fail(self, **kw: Any) -> AssertionResult:
        return self._outcome(AssertionOutcome.FAIL, **kw)

    def _skip(self, **kw: Any) -> AssertionResult:
        return self._outcome(AssertionOutcome.SKIPPED, **kw)

    def _require(self, key: str) -> Any:
        """Fetch a required config value or raise :class:`AssertionConfigError`."""
        from nature_agent_validator.errors import AssertionConfigError

        try:
            return self.config[key]
        except KeyError:
            raise AssertionConfigError(
                f"assertion {self.assertion_id!r} ({self.type}) requires "
                f"config key {key!r}"
            ) from None


__all__ = ["Assertion"]
