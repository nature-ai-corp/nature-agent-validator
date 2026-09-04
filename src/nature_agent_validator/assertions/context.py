"""Everything an assertion is allowed to look at.

Assertions are pure judgments over this context: the normalized target result
plus optional evidence. They must not perform I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nature_agent_validator.adapters.result import NormalizedResult
    from nature_agent_validator.evidence import EvidenceRecord


@dataclass(frozen=True, slots=True)
class AssertionContext:
    result: "NormalizedResult"
    evidence: "EvidenceRecord | None" = None

    @property
    def has_evidence(self) -> bool:
        return self.evidence is not None


__all__ = ["AssertionContext"]
