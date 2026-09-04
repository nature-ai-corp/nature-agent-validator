"""Coverage-aware evidence assertions: evidence_event_exists /
evidence_event_not_exists.

The mandatory rule (Phase 2 handoff s5/s7): absence of an event only supports a
negative PASS when the event type's namespace is in the record's declared
coverage. Missing evidence, or an uncovered namespace, is SKIPPED for both the
positive and the negative assertion.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from nature_agent_validator.assertions import (
    AssertionContext,
    AssertionOutcome,
    AssertionSpec,
    build_assertion,
)
from nature_agent_validator.adapters import NormalizedResult
from nature_agent_validator.evidence import EvidenceEvent, EvidenceRecord

_TS = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)


def _event(event_type: str, **attrs: object) -> EvidenceEvent:
    return EvidenceEvent(event_type, event_type, _TS, "test", attrs)


def _ctx(record: EvidenceRecord | None) -> AssertionContext:
    return AssertionContext(result=NormalizedResult(status=200), evidence=record)


def _outcome(kind: str, config: dict, ctx: AssertionContext) -> AssertionOutcome:
    return build_assertion(AssertionSpec("a", kind, config)).evaluate(ctx).outcome


# A record that covers 'authorization' and 'tool', with one authz deny event.
def _record() -> EvidenceRecord:
    return EvidenceRecord(
        events=(
            _event("authorization.decision", decision="deny", permission="payroll.read"),
        ),
        coverage=("authorization", "tool"),
    )


class EvidenceExistsTests(unittest.TestCase):
    def test_pass_when_covered_and_present(self) -> None:  # req 3
        self.assertEqual(
            _outcome(
                "evidence_event_exists",
                {"event_type": "authorization.decision", "attributes": {"decision": "deny"}},
                _ctx(_record()),
            ),
            AssertionOutcome.PASS,
        )

    def test_fail_when_covered_and_absent(self) -> None:  # req 4
        self.assertEqual(
            _outcome(
                "evidence_event_exists",
                {"event_type": "tool.executed"},
                _ctx(_record()),
            ),
            AssertionOutcome.FAIL,
        )

    def test_skipped_when_no_evidence(self) -> None:  # req 5
        self.assertEqual(
            _outcome(
                "evidence_event_exists",
                {"event_type": "authorization.decision"},
                _ctx(None),
            ),
            AssertionOutcome.SKIPPED,
        )

    def test_skipped_when_namespace_not_covered(self) -> None:  # req 6
        self.assertEqual(
            _outcome(
                "evidence_event_exists",
                {"event_type": "knowledge.accessed"},
                _ctx(_record()),
            ),
            AssertionOutcome.SKIPPED,
        )


class EvidenceNotExistsTests(unittest.TestCase):
    def test_pass_when_covered_and_absent(self) -> None:  # req 7
        self.assertEqual(
            _outcome(
                "evidence_event_not_exists",
                {"event_type": "tool.executed", "attributes": {"tool_name": "payroll.read"}},
                _ctx(_record()),
            ),
            AssertionOutcome.PASS,
        )

    def test_fail_when_covered_and_matching_event_exists(self) -> None:  # req 8
        self.assertEqual(
            _outcome(
                "evidence_event_not_exists",
                {"event_type": "authorization.decision", "attributes": {"decision": "deny"}},
                _ctx(_record()),
            ),
            AssertionOutcome.FAIL,
        )

    def test_skipped_when_no_evidence(self) -> None:  # req 9
        self.assertEqual(
            _outcome(
                "evidence_event_not_exists",
                {"event_type": "tool.executed"},
                _ctx(None),
            ),
            AssertionOutcome.SKIPPED,
        )

    def test_skipped_when_namespace_not_covered(self) -> None:  # req 10
        # 'knowledge' not covered -> cannot conclude "did not access knowledge"
        self.assertEqual(
            _outcome(
                "evidence_event_not_exists",
                {"event_type": "knowledge.accessed"},
                _ctx(_record()),
            ),
            AssertionOutcome.SKIPPED,
        )


class EvidenceMatchingTests(unittest.TestCase):
    def test_exact_attribute_filtering(self) -> None:  # req 11
        ctx = _ctx(_record())
        # subset match on the given keys -> PASS
        self.assertEqual(
            _outcome(
                "evidence_event_exists",
                {
                    "event_type": "authorization.decision",
                    "attributes": {"decision": "deny", "permission": "payroll.read"},
                },
                ctx,
            ),
            AssertionOutcome.PASS,
        )
        # one attribute value differs -> no match -> FAIL (namespace covered)
        self.assertEqual(
            _outcome(
                "evidence_event_exists",
                {"event_type": "authorization.decision", "attributes": {"decision": "allow"}},
                ctx,
            ),
            AssertionOutcome.FAIL,
        )
        # extra required attribute the event does not carry -> no match -> FAIL
        self.assertEqual(
            _outcome(
                "evidence_event_exists",
                {
                    "event_type": "authorization.decision",
                    "attributes": {"decision": "deny", "permission": "other"},
                },
                ctx,
            ),
            AssertionOutcome.FAIL,
        )

    def test_unrelated_events_do_not_satisfy_assertion(self) -> None:  # req 12
        rec = EvidenceRecord(
            events=(_event("authorization.decision", decision="deny"),),
            coverage=("authorization", "tool"),
        )
        # a covered-but-absent tool.executed: exists -> FAIL, not_exists -> PASS
        self.assertEqual(
            _outcome("evidence_event_exists", {"event_type": "tool.executed"}, _ctx(rec)),
            AssertionOutcome.FAIL,
        )
        self.assertEqual(
            _outcome("evidence_event_not_exists", {"event_type": "tool.executed"}, _ctx(rec)),
            AssertionOutcome.PASS,
        )

    def test_skipped_passed_is_none(self) -> None:
        result = build_assertion(
            AssertionSpec("a", "evidence_event_exists", {"event_type": "x.y"})
        ).evaluate(_ctx(None))
        self.assertIs(result.outcome, AssertionOutcome.SKIPPED)
        self.assertIsNone(result.passed)
        self.assertIsNone(result.to_dict()["passed"])


if __name__ == "__main__":
    unittest.main()
