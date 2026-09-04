"""The :class:`ValidationResult` and its supporting value objects.

``overall_status`` is one of:

* ``PASS``  -- every evaluated assertion passed (skipped ones don't count against)
* ``FAIL``  -- at least one assertion was evaluated and failed
* ``ERROR`` -- the Validator could not complete the run (adapter could not be
               built, adapter raised, an assertion definition was broken).
               ``ERROR`` is never used for an ordinary assertion failure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from nature_agent_validator.assertions.result import AssertionOutcome, AssertionResult

if TYPE_CHECKING:
    from nature_agent_validator.evidence import EvidenceRecord


class OverallStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class ExecutionMetadata:
    adapter: str
    started_at: datetime
    finished_at: datetime
    duration_ms: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "duration_ms": self.duration_ms,
        }


@dataclass(frozen=True, slots=True)
class EvidenceSummary:
    available: bool
    event_count: int = 0
    event_types: tuple[str, ...] = ()
    contract_version: str | None = None
    #: Namespaces the target declared it covers (Phase 2). Empty when evidence
    #: is unavailable or the target declared no coverage.
    coverage: tuple[str, ...] = ()

    @classmethod
    def from_record(cls, record: "EvidenceRecord | None") -> "EvidenceSummary":
        if record is None:
            return cls(available=False)
        return cls(
            available=True,
            event_count=len(record),
            event_types=record.event_types(),
            contract_version=record.contract_version,
            coverage=record.coverage,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "event_count": self.event_count,
            "event_types": list(self.event_types),
            "coverage": list(self.coverage),
            "contract_version": self.contract_version,
        }


@dataclass(frozen=True, slots=True)
class ValidationResult:
    scenario_id: str
    scenario_name: str
    overall_status: OverallStatus
    assertion_results: tuple[AssertionResult, ...] = ()
    execution_metadata: ExecutionMetadata | None = None
    evidence_summary: EvidenceSummary = field(
        default_factory=lambda: EvidenceSummary(available=False)
    )
    errors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "assertion_results", tuple(self.assertion_results)
        )
        object.__setattr__(self, "errors", tuple(self.errors))

    @property
    def passed(self) -> bool:
        return self.overall_status is OverallStatus.PASS

    def counts(self) -> dict[str, int]:
        c = {"pass": 0, "fail": 0, "skipped": 0}
        for r in self.assertion_results:
            if r.outcome is AssertionOutcome.PASS:
                c["pass"] += 1
            elif r.outcome is AssertionOutcome.FAIL:
                c["fail"] += 1
            else:
                c["skipped"] += 1
        return c

    def summary_line(self) -> str:
        c = self.counts()
        total = len(self.assertion_results)
        parts = [
            f"[{self.overall_status.value}]",
            self.scenario_id,
            f"-- {c['pass']}/{total} assertions passed",
        ]
        if c["skipped"]:
            parts.append(f"({c['skipped']} skipped)")
        if self.errors:
            parts.append(f"({len(self.errors)} error(s))")
        return " ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "scenario_name": self.scenario_name,
            "overall_status": self.overall_status.value,
            # PASS may still contain SKIPPED assertions -- the counts make that
            # explicit for consumers of the JSON report.
            "counts": self.counts(),
            "assertion_results": [r.to_dict() for r in self.assertion_results],
            "execution_metadata": (
                self.execution_metadata.to_dict()
                if self.execution_metadata is not None
                else None
            ),
            "evidence_summary": self.evidence_summary.to_dict(),
            "errors": list(self.errors),
        }


__all__ = [
    "EvidenceSummary",
    "ExecutionMetadata",
    "OverallStatus",
    "ValidationResult",
]
