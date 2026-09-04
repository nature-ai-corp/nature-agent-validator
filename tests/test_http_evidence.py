"""Phase 2 evidence input path: HTTP extraction + StaticAdapter, localhost only.

* HTTP evidence extraction is opt-in via ``target.config.evidence_field`` and
  vendor-neutral (a top-level JSON key holding ``{coverage, events}``).
* A present-but-malformed evidence field is an ERROR, never silent black-box.
* Without ``evidence_field`` the HTTP adapter stays a black-box validator.
"""

from __future__ import annotations

import unittest

from nature_agent_validator.adapters import StaticAdapter
from nature_agent_validator.adapters.http import HttpAdapter
from nature_agent_validator.assertions import AssertionSpec
from nature_agent_validator.errors import AdapterError, EvidenceError
from nature_agent_validator.evidence import EvidenceRecord
from nature_agent_validator.reporting import OverallStatus
from nature_agent_validator.runner import Runner
from nature_agent_validator.scenario import Scenario, ScenarioRequest, ScenarioTarget

from tests.http_fixture import LocalHTTPServer


def _http_scenario(config: dict, expectations: tuple) -> Scenario:
    return Scenario(
        scenario_id="http-ev",
        name="http evidence",
        target=ScenarioTarget("http", config),
        request=ScenarioRequest(payload={"message": "hi"}),
        expectations=expectations,
    )


class HttpEvidenceExtractionTests(unittest.TestCase):
    def test_extracts_evidence_from_configured_field(self) -> None:  # req 13
        with LocalHTTPServer() as srv:
            adapter = HttpAdapter.from_config(
                {"url": srv.url("/evidence"), "evidence_field": "evidence"}
            )
            resp = adapter.send(ScenarioRequest())
        self.assertIsInstance(resp.evidence, EvidenceRecord)
        self.assertEqual(resp.evidence.coverage, ("authorization", "tool", "response"))
        self.assertTrue(resp.evidence.has_event_type("authorization.decision"))
        # event carried no timestamp -> optional
        self.assertIsNone(resp.evidence.of_type("authorization.decision")[0].timestamp)

    def test_evidence_enabled_scenario_runs_end_to_end(self) -> None:  # req 13 (runner)
        with LocalHTTPServer() as srv:
            result = Runner().run(
                _http_scenario(
                    {"url": srv.url("/evidence"), "evidence_field": "evidence"},
                    (
                        AssertionSpec("status", "status_equals", {"value": 200}),
                        AssertionSpec(
                            "authz",
                            "evidence_event_exists",
                            {"event_type": "authorization.decision", "attributes": {"decision": "deny"}},
                        ),
                        AssertionSpec(
                            "no-tool",
                            "evidence_event_not_exists",
                            {"event_type": "tool.executed", "attributes": {"tool_name": "payroll.read"}},
                        ),
                    ),
                )
            )
        self.assertIs(result.overall_status, OverallStatus.PASS)
        self.assertTrue(result.evidence_summary.available)
        self.assertEqual(
            result.evidence_summary.coverage, ("authorization", "tool", "response")
        )
        self.assertEqual(result.evidence_summary.event_count, 2)
        self.assertEqual(result.counts(), {"pass": 3, "fail": 0, "skipped": 0})

    def test_malformed_evidence_is_error(self) -> None:  # req 14
        with LocalHTTPServer() as srv:
            adapter = HttpAdapter.from_config(
                {"url": srv.url("/evidence-malformed"), "evidence_field": "evidence"}
            )
            with self.assertRaises(AdapterError):
                adapter.send(ScenarioRequest())

    def test_malformed_evidence_via_runner_is_error(self) -> None:  # req 14 (runner)
        with LocalHTTPServer() as srv:
            result = Runner().run(
                _http_scenario(
                    {"url": srv.url("/evidence-malformed"), "evidence_field": "evidence"},
                    (AssertionSpec("s", "status_equals", {"value": 200}),),
                )
            )
        self.assertIs(result.overall_status, OverallStatus.ERROR)
        self.assertTrue(any("malformed" in e for e in result.errors))
        self.assertEqual(result.assertion_results, ())

    def test_without_evidence_field_is_blackbox(self) -> None:  # req 15
        with LocalHTTPServer() as srv:
            adapter = HttpAdapter.from_config({"url": srv.url("/evidence")})
            resp = adapter.send(ScenarioRequest())
        self.assertIsNone(resp.evidence)  # evidence present in body but not opted-in

    def test_configured_field_absent_from_body_is_blackbox(self) -> None:  # req 15
        with LocalHTTPServer() as srv:
            adapter = HttpAdapter.from_config(
                {"url": srv.url("/echo"), "evidence_field": "evidence"}
            )
            resp = adapter.send(ScenarioRequest(payload={"m": 1}))
        self.assertIsNone(resp.evidence)  # /echo body has no "evidence" key

    def test_non_json_body_with_evidence_field_is_blackbox(self) -> None:
        with LocalHTTPServer() as srv:
            adapter = HttpAdapter.from_config(
                {"url": srv.url("/text"), "evidence_field": "evidence"}
            )
            resp = adapter.send(ScenarioRequest())
        self.assertIsNone(resp.evidence)

    def test_evidence_field_must_be_a_string(self) -> None:
        with self.assertRaises(AdapterError):
            HttpAdapter.from_config(
                {"url": "http://127.0.0.1/x", "evidence_field": ["evidence"]}
            )

    def test_blackbox_scenario_skips_evidence_assertions(self) -> None:  # req 15
        with LocalHTTPServer() as srv:
            result = Runner().run(
                _http_scenario(
                    {"url": srv.url("/evidence")},  # no evidence_field
                    (
                        AssertionSpec("status", "status_equals", {"value": 200}),
                        AssertionSpec(
                            "authz", "evidence_event_exists",
                            {"event_type": "authorization.decision"},
                        ),
                    ),
                )
            )
        self.assertIs(result.overall_status, OverallStatus.PASS)
        self.assertEqual(result.counts()["skipped"], 1)
        self.assertFalse(result.evidence_summary.available)


class StaticAdapterEvidenceTests(unittest.TestCase):
    def test_dict_evidence_path_with_coverage(self) -> None:  # req 16
        adapter = StaticAdapter.from_config(
            {
                "status": 200,
                "body": {"answer": "no"},
                "evidence": {
                    "coverage": ["authorization", "tool"],
                    "events": [
                        {
                            "event_id": "e1",
                            "event_type": "authorization.decision",
                            "attributes": {"decision": "deny"},
                        }
                    ],
                },
            }
        )
        rec = adapter.send(ScenarioRequest()).evidence
        self.assertIsInstance(rec, EvidenceRecord)
        self.assertEqual(rec.coverage, ("authorization", "tool"))
        self.assertTrue(rec.has_event_type("authorization.decision"))

    def test_legacy_list_evidence_still_supported(self) -> None:
        adapter = StaticAdapter.from_config(
            {
                "status": 200,
                "evidence": [
                    {
                        "event_id": "e1",
                        "event_type": "authorization.decision",
                        "timestamp": "2026-09-03T12:00:00+00:00",
                        "attributes": {"decision": "deny"},
                    }
                ],
            }
        )
        rec = adapter.send(ScenarioRequest()).evidence
        self.assertIsInstance(rec, EvidenceRecord)
        self.assertEqual(rec.coverage, ())  # no coverage in the legacy form

    def test_malformed_static_evidence_raises(self) -> None:  # req 14 (static path)
        with self.assertRaises(EvidenceError):
            StaticAdapter.from_config(
                {"status": 200, "evidence": {"events": "not-a-list"}}
            )

    def test_malformed_static_evidence_is_runner_error(self) -> None:
        scenario = Scenario(
            scenario_id="s",
            name="s",
            target=ScenarioTarget(
                "static", {"status": 200, "evidence": {"events": [{"event_type": "x"}]}}
            ),
            request=ScenarioRequest(),
            expectations=(AssertionSpec("s", "status_equals", {"value": 200}),),
        )
        result = Runner().run(scenario)
        self.assertIs(result.overall_status, OverallStatus.ERROR)


if __name__ == "__main__":
    unittest.main()
