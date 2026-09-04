"""ValidationResult / supporting value objects."""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone

from nature_agent_validator.assertions import AssertionOutcome, AssertionResult
from nature_agent_validator.evidence import EvidenceEvent, EvidenceRecord
from nature_agent_validator.reporting import (
    EvidenceSummary,
    ExecutionMetadata,
    OverallStatus,
    ValidationResult,
)


class ReportingTests(unittest.TestCase):
    def test_overall_status_values(self) -> None:
        self.assertEqual(
            {s.value for s in OverallStatus}, {"PASS", "FAIL", "ERROR"}
        )

    def test_evidence_summary_from_record(self) -> None:
        self.assertFalse(EvidenceSummary.from_record(None).available)
        rec = EvidenceRecord(
            events=(
                EvidenceEvent("e", "response.generated", datetime(2026, 9, 3, tzinfo=timezone.utc)),
            )
        )
        summary = EvidenceSummary.from_record(rec)
        self.assertTrue(summary.available)
        self.assertEqual(summary.event_count, 1)
        self.assertEqual(summary.event_types, ("response.generated",))

    def test_validation_result_to_dict_is_json_serializable(self) -> None:
        now = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)
        result = ValidationResult(
            scenario_id="s1",
            scenario_name="s1",
            overall_status=OverallStatus.PASS,
            assertion_results=(
                AssertionResult("a", "contains", AssertionOutcome.PASS, "x", "x", ""),
            ),
            execution_metadata=ExecutionMetadata("static", now, now, 1.0),
            evidence_summary=EvidenceSummary(available=False),
        )
        payload = json.dumps(result.to_dict())
        self.assertIn('"overall_status": "PASS"', payload)
        self.assertEqual(result.counts(), {"pass": 1, "fail": 0, "skipped": 0})
        self.assertIn("[PASS]", result.summary_line())


if __name__ == "__main__":
    unittest.main()
