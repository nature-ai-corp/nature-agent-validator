"""Evidence Contract behaviour and round-tripping."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from nature_agent_validator.errors import EvidenceError
from nature_agent_validator.evidence import (
    EVIDENCE_CONTRACT_VERSION,
    EvidenceEvent,
    EvidenceRecord,
    evidence_namespace,
)


def _event(kind: str, **attrs: object) -> EvidenceEvent:
    return EvidenceEvent(
        event_id=kind,
        event_type=kind,
        timestamp=datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc),
        source="test",
        attributes=attrs,
    )


class EvidenceTests(unittest.TestCase):
    def test_record_queries(self) -> None:
        rec = EvidenceRecord(
            events=(
                _event("request.received"),
                _event("authorization.decision", decision="denied"),
                _event("response.generated"),
            )
        )
        self.assertEqual(len(rec), 3)
        self.assertEqual(
            rec.event_types(),
            ("request.received", "authorization.decision", "response.generated"),
        )
        self.assertTrue(rec.has_event_type("authorization.decision"))
        self.assertFalse(rec.has_event_type("tool.executed"))
        self.assertEqual(len(rec.of_type("authorization.decision")), 1)

    def test_default_contract_version(self) -> None:
        self.assertEqual(EvidenceRecord().contract_version, EVIDENCE_CONTRACT_VERSION)

    def test_event_attributes_read_only(self) -> None:
        ev = _event("x", a=1)
        with self.assertRaises(TypeError):
            ev.attributes["a"] = 2  # type: ignore[index]

    def test_round_trip(self) -> None:
        rec = EvidenceRecord(events=(_event("authorization.decision", decision="denied"),))
        self.assertEqual(EvidenceRecord.from_dict(rec.to_dict()), rec)

    def test_from_events_none(self) -> None:
        self.assertIsNone(EvidenceRecord.from_events(None))
        self.assertEqual(len(EvidenceRecord.from_events([])), 0)

    # -- Phase 2: coverage, namespaces, optional timestamp, malformed input ---

    def test_record_with_events_and_coverage(self) -> None:
        rec = EvidenceRecord(
            events=(_event("authorization.decision", decision="deny"),),
            coverage=("authorization", "tool"),
        )
        self.assertEqual(len(rec), 1)
        self.assertEqual(rec.coverage, ("authorization", "tool"))
        self.assertTrue(rec.covers("authorization"))
        self.assertTrue(rec.covers("tool"))
        self.assertFalse(rec.covers("knowledge"))

    def test_coverage_is_deduped_and_string_coerced(self) -> None:
        rec = EvidenceRecord(coverage=("tool", "tool", "authorization"))
        self.assertEqual(rec.coverage, ("tool", "authorization"))

    def test_coverage_not_inferred_from_events(self) -> None:
        rec = EvidenceRecord(events=(_event("tool.executed"),))
        self.assertFalse(rec.covers("tool"))  # events present, coverage empty

    def test_event_type_namespace_extraction(self) -> None:
        self.assertEqual(evidence_namespace("tool.executed"), "tool")
        self.assertEqual(evidence_namespace("authorization.decision"), "authorization")
        self.assertEqual(evidence_namespace("knowledge.accessed"), "knowledge")
        self.assertEqual(evidence_namespace("response"), "response")
        self.assertEqual(evidence_namespace("a.b.c"), "a")

    def test_coverage_round_trip(self) -> None:
        rec = EvidenceRecord(
            events=(_event("authorization.decision", decision="deny"),),
            coverage=("authorization", "tool"),
        )
        self.assertEqual(EvidenceRecord.from_dict(rec.to_dict()), rec)

    def test_timestamp_is_optional(self) -> None:
        ev = EvidenceEvent.from_dict(
            {"event_id": "e", "event_type": "response.generated"}
        )
        self.assertIsNone(ev.timestamp)
        self.assertIsNone(ev.to_dict()["timestamp"])

    def test_timestamp_accepts_z_suffix(self) -> None:
        ev = EvidenceEvent.from_dict(
            {
                "event_id": "e",
                "event_type": "response.generated",
                "timestamp": "2026-09-03T22:00:00Z",
            }
        )
        self.assertEqual(ev.timestamp, datetime(2026, 9, 3, 22, 0, tzinfo=timezone.utc))

    def test_malformed_evidence_raises_evidence_error(self) -> None:
        for bad in (
            "not-an-object",
            ["a", "list"],
            {"events": "not-a-list"},
            {"coverage": "not-a-list"},
            {"coverage": [1, 2]},
            {"events": [{"event_type": "x"}]},          # missing event_id
            {"events": [{"event_id": "e", "event_type": "x", "timestamp": "nope"}]},
            {"events": [{"event_id": "e", "event_type": "x", "attributes": []}]},
        ):
            with self.assertRaises(EvidenceError):
                EvidenceRecord.from_dict(bad)

    def test_from_events_rejects_non_list(self) -> None:
        with self.assertRaises(EvidenceError):
            EvidenceRecord.from_events("nope")


if __name__ == "__main__":
    unittest.main()
