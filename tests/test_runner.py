"""End-to-end runner behaviour: PASS / FAIL / ERROR and skip handling."""

from __future__ import annotations

import unittest

from nature_agent_validator.adapters import AdapterResponse, NormalizedResult, TargetAdapter
from nature_agent_validator.assertions import AssertionSpec
from nature_agent_validator.reporting import OverallStatus
from nature_agent_validator.runner import Runner
from nature_agent_validator.scenario import Scenario, ScenarioRequest, ScenarioTarget


def _scenario(config: dict, expectations: tuple[AssertionSpec, ...]) -> Scenario:
    return Scenario(
        scenario_id="s1",
        name="s1",
        target=ScenarioTarget("static", config),
        request=ScenarioRequest(payload={"message": "hi"}),
        expectations=expectations,
    )


class RunnerTests(unittest.TestCase):
    def test_pass(self) -> None:
        result = Runner().run(
            _scenario(
                {"status": 200, "body": {"answer": "not authorized"}, "latency_ms": 5.0},
                (
                    AssertionSpec("s", "status_equals", {"value": 200}),
                    AssertionSpec("t", "contains", {"value": "not authorized"}),
                    AssertionSpec("l", "latency_below", {"max_ms": 1000}),
                ),
            )
        )
        self.assertIs(result.overall_status, OverallStatus.PASS)
        self.assertTrue(result.passed)
        self.assertEqual(result.counts(), {"pass": 3, "fail": 0, "skipped": 0})
        self.assertIsNotNone(result.execution_metadata)

    def test_fail_does_not_become_error(self) -> None:
        result = Runner().run(
            _scenario(
                {"status": 500, "text": "boom"},
                (AssertionSpec("s", "status_equals", {"value": 200}),),
            )
        )
        self.assertIs(result.overall_status, OverallStatus.FAIL)
        self.assertEqual(result.errors, ())

    def test_broken_assertion_definition_is_error_not_fail(self) -> None:
        result = Runner().run(
            _scenario(
                {"status": 200, "text": "x"},
                (AssertionSpec("bad", "no_such_type", {}),),
            )
        )
        self.assertIs(result.overall_status, OverallStatus.ERROR)
        self.assertTrue(result.errors)

    def test_adapter_send_exception_is_error(self) -> None:
        class Boom(TargetAdapter):
            name = "boom"

            def send(self, request):  # noqa: ANN001, ANN201
                raise RuntimeError("transport down")

        result = Runner().run(
            _scenario({}, (AssertionSpec("s", "status_equals", {"value": 200}),)),
            adapter=Boom(),
        )
        self.assertIs(result.overall_status, OverallStatus.ERROR)
        self.assertTrue(any("transport down" in e for e in result.errors))
        self.assertEqual(result.assertion_results, ())

    def test_unknown_adapter_is_error(self) -> None:
        result = Runner().run(
            Scenario(
                scenario_id="s",
                name="s",
                target=ScenarioTarget("no-such-adapter", {}),
                request=ScenarioRequest(),
                expectations=(),
            )
        )
        self.assertIs(result.overall_status, OverallStatus.ERROR)

    def test_evidence_assertions_skipped_on_blackbox_still_pass(self) -> None:
        result = Runner().run(
            _scenario(
                {"status": 200, "body": {"answer": "not authorized"}},
                (
                    AssertionSpec("t", "contains", {"value": "not authorized"}),
                    AssertionSpec("ev", "evidence_event_absent", {"event_type": "tool.executed"}),
                ),
            )
        )
        self.assertIs(result.overall_status, OverallStatus.PASS)
        self.assertEqual(result.counts()["skipped"], 1)
        self.assertFalse(result.evidence_summary.available)
        skipped = next(r for r in result.assertion_results if r.skipped)
        self.assertIsNone(skipped.passed)
        self.assertIsNone(skipped.to_dict()["passed"])

    def test_run_returns_transport_error_result_as_fail(self) -> None:
        # adapter returns a result carrying a transport error -> assertions judge it
        result = Runner().run(
            _scenario(
                {"status": None, "text": "", "error": "connection refused"},
                (AssertionSpec("s", "status_equals", {"value": 200}),),
            )
        )
        self.assertIs(result.overall_status, OverallStatus.FAIL)


if __name__ == "__main__":
    unittest.main()
