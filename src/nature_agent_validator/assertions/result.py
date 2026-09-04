"""The structured result of evaluating a single assertion."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class AssertionOutcome(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    #: The assertion could not be evaluated because required inputs were absent
    #: (e.g. an evidence assertion against a black-box target). A skipped
    #: assertion never makes a scenario FAIL. See principle P0-3.
    SKIPPED = "SKIPPED"


@dataclass(frozen=True, slots=True)
class AssertionResult:
    #: ``outcome`` is the authoritative state of an assertion result. ``passed``
    #: is a derived convenience only and is tri-state: a SKIPPED assertion is
    #: neither passed nor failed.
    assertion_id: str
    type: str
    outcome: AssertionOutcome
    expected: Any = None
    observed: Any = None
    message: str = ""

    @property
    def passed(self) -> bool | None:
        """PASS -> ``True``, FAIL -> ``False``, SKIPPED -> ``None``.

        SKIPPED must never behave or serialize as a failure; callers that need
        a strict verdict should read :attr:`outcome` instead.
        """
        if self.outcome is AssertionOutcome.SKIPPED:
            return None
        return self.outcome is AssertionOutcome.PASS

    @property
    def skipped(self) -> bool:
        return self.outcome is AssertionOutcome.SKIPPED

    def to_dict(self) -> dict[str, Any]:
        return {
            "assertion_id": self.assertion_id,
            "type": self.type,
            "outcome": self.outcome.value,
            # tri-state: true / false / null (null == SKIPPED, not a failure)
            "passed": self.passed,
            "expected": self.expected,
            "observed": self.observed,
            "message": self.message,
        }


__all__ = ["AssertionOutcome", "AssertionResult"]
