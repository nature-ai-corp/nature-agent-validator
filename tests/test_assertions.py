"""Every built-in assertion: a passing case, a failing case, and skip semantics."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from nature_agent_validator.assertions import (
    AssertionContext,
    AssertionOutcome,
    AssertionSpec,
    build_assertion,
)
# Internal table -- Phase 0 exposes no public registration/introspection API.
from nature_agent_validator.assertions.registry import _known_types
from nature_agent_validator.adapters import NormalizedResult
from nature_agent_validator.errors import AssertionConfigError, UnknownAssertionType
from nature_agent_validator.evidence import EvidenceEvent, EvidenceRecord


def _ctx(*, evidence: EvidenceRecord | None = None, **result_kw: object) -> AssertionContext:
    return AssertionContext(result=NormalizedResult(**result_kw), evidence=evidence)


def _run(kind: str, config: dict, ctx: AssertionContext) -> AssertionOutcome:
    return build_assertion(AssertionSpec("a", kind, config)).evaluate(ctx).outcome


class BuiltinAssertionTests(unittest.TestCase):
    def test_all_builtin_types_registered(self) -> None:
        self.assertEqual(
            set(_known_types()),
            {
                "status_equals",
                "equals",
                "contains",
                "not_contains",
                "regex_match",
                "json_path_equals",
                "latency_below",
                "evidence_event_exists",
                "evidence_event_not_exists",
            },
        )

    def test_status_equals(self) -> None:
        self.assertEqual(_run("status_equals", {"value": 200}, _ctx(status=200)), AssertionOutcome.PASS)
        self.assertEqual(_run("status_equals", {"value": 200}, _ctx(status=403)), AssertionOutcome.FAIL)

    def test_equals_with_and_without_path(self) -> None:
        ctx = _ctx(body={"answer": "no"})
        self.assertEqual(_run("equals", {"value": "no", "path": "answer"}, ctx), AssertionOutcome.PASS)
        self.assertEqual(_run("equals", {"value": "yes", "path": "answer"}, ctx), AssertionOutcome.FAIL)
        self.assertEqual(_run("equals", {"value": {"answer": "no"}}, ctx), AssertionOutcome.PASS)
        self.assertEqual(_run("equals", {"value": 1, "path": "missing"}, ctx), AssertionOutcome.FAIL)

    def test_contains_and_not_contains(self) -> None:
        ctx = _ctx(text="I am not authorized to help with that")
        self.assertEqual(_run("contains", {"value": "not authorized"}, ctx), AssertionOutcome.PASS)
        self.assertEqual(_run("contains", {"value": "$"}, ctx), AssertionOutcome.FAIL)
        self.assertEqual(_run("not_contains", {"value": "$"}, ctx), AssertionOutcome.PASS)
        self.assertEqual(_run("not_contains", {"value": "authorized"}, ctx), AssertionOutcome.FAIL)

    def test_regex_match(self) -> None:
        ctx = _ctx(text="order 12345 confirmed")
        self.assertEqual(_run("regex_match", {"pattern": r"order \d+"}, ctx), AssertionOutcome.PASS)
        self.assertEqual(_run("regex_match", {"pattern": r"^refund"}, ctx), AssertionOutcome.FAIL)

    def test_regex_invalid_pattern_is_config_error(self) -> None:
        with self.assertRaises(AssertionConfigError):
            build_assertion(AssertionSpec("a", "regex_match", {"pattern": "("})).evaluate(_ctx(text="x"))

    def test_json_path_equals(self) -> None:
        ctx = _ctx(body={"items": [{"id": 7}, {"id": 8}]})
        self.assertEqual(_run("json_path_equals", {"path": "items.1.id", "value": 8}, ctx), AssertionOutcome.PASS)
        self.assertEqual(_run("json_path_equals", {"path": "items.0.id", "value": 8}, ctx), AssertionOutcome.FAIL)
        self.assertEqual(_run("json_path_equals", {"path": "items.9.id", "value": 8}, ctx), AssertionOutcome.FAIL)

    def test_latency_below(self) -> None:
        self.assertEqual(_run("latency_below", {"max_ms": 1000}, _ctx(latency_ms=250.0)), AssertionOutcome.PASS)
        self.assertEqual(_run("latency_below", {"max_ms": 100}, _ctx(latency_ms=250.0)), AssertionOutcome.FAIL)
        self.assertEqual(_run("latency_below", {"max_ms": 100}, _ctx(latency_ms=None)), AssertionOutcome.FAIL)

    def test_missing_required_config_is_config_error(self) -> None:
        with self.assertRaises(AssertionConfigError):
            build_assertion(AssertionSpec("a", "contains", {})).evaluate(_ctx(text="x"))

    def test_unknown_assertion_type(self) -> None:
        with self.assertRaises(UnknownAssertionType):
            build_assertion(AssertionSpec("a", "does_not_exist", {}))

    # -- evidence assertions ------------------------------------------------

    def _evidence(self) -> EvidenceRecord:
        return EvidenceRecord(
            events=(
                EvidenceEvent(
                    "e1",
                    "authorization.decision",
                    datetime(2026, 9, 3, tzinfo=timezone.utc),
                    "authz",
                    {"decision": "deny"},
                ),
            ),
            coverage=("authorization", "tool"),
        )

    def test_evidence_exists(self) -> None:
        ctx = _ctx(evidence=self._evidence())
        self.assertEqual(
            _run("evidence_event_exists", {"event_type": "authorization.decision", "attributes": {"decision": "deny"}}, ctx),
            AssertionOutcome.PASS,
        )
        # covered namespace ('tool'), no matching event -> FAIL, not SKIP
        self.assertEqual(
            _run("evidence_event_exists", {"event_type": "tool.executed"}, ctx),
            AssertionOutcome.FAIL,
        )

    def test_evidence_not_exists(self) -> None:
        ctx = _ctx(evidence=self._evidence())
        self.assertEqual(
            _run("evidence_event_not_exists", {"event_type": "tool.executed", "attributes": {"tool_name": "payroll.read"}}, ctx),
            AssertionOutcome.PASS,
        )
        self.assertEqual(
            _run("evidence_event_not_exists", {"event_type": "authorization.decision"}, ctx),
            AssertionOutcome.FAIL,
        )

    def test_evidence_assertions_skip_when_no_evidence(self) -> None:
        ctx = _ctx(evidence=None)
        self.assertEqual(
            _run("evidence_event_exists", {"event_type": "authorization.decision"}, ctx),
            AssertionOutcome.SKIPPED,
        )
        self.assertEqual(
            _run("evidence_event_not_exists", {"event_type": "tool.executed"}, ctx),
            AssertionOutcome.SKIPPED,
        )

    def test_evidence_assertions_skip_when_namespace_not_covered(self) -> None:
        # evidence exists but 'knowledge' is not in declared coverage
        ctx = _ctx(evidence=self._evidence())
        self.assertEqual(
            _run("evidence_event_exists", {"event_type": "knowledge.accessed"}, ctx),
            AssertionOutcome.SKIPPED,
        )
        self.assertEqual(
            _run("evidence_event_not_exists", {"event_type": "knowledge.accessed"}, ctx),
            AssertionOutcome.SKIPPED,
        )

    def test_outcome_is_authoritative_and_passed_is_tri_state(self) -> None:
        from nature_agent_validator.assertions import AssertionResult

        def mk(outcome: AssertionOutcome) -> AssertionResult:
            return AssertionResult("a", "contains", outcome)

        self.assertIs(mk(AssertionOutcome.PASS).passed, True)
        self.assertIs(mk(AssertionOutcome.FAIL).passed, False)
        self.assertIsNone(mk(AssertionOutcome.SKIPPED).passed)

        # SKIPPED must not serialize as a failure.
        skipped = mk(AssertionOutcome.SKIPPED).to_dict()
        self.assertEqual(skipped["outcome"], "SKIPPED")
        self.assertIsNone(skipped["passed"])
        self.assertNotEqual(skipped["passed"], False)


if __name__ == "__main__":
    unittest.main()
