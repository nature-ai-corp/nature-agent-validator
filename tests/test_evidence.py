"""Evidence Contract behaviour and round-tripping."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from nature_agent_validator.evidence import (
    EVIDENCE_CONTRACT_VERSION,
    EvidenceEvent,
    EvidenceRecord,
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


if __name__ == "__main__":
    unittest.main()
