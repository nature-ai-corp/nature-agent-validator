"""Generic HTTP target adapter: real localhost requests, normalization, and
the transport-error -> ERROR boundary.

All traffic is localhost-only (see ``tests/http_fixture.py``); the suite needs
no Internet access.
"""

from __future__ import annotations

import unittest

from nature_agent_validator.adapters import AdapterResponse, build_adapter
from nature_agent_validator.adapters.http import HttpAdapter
from nature_agent_validator.adapters.base import TargetAdapter
from nature_agent_validator.assertions import AssertionSpec
from nature_agent_validator.errors import AdapterError
from nature_agent_validator.reporting import OverallStatus
from nature_agent_validator.runner import Runner
from nature_agent_validator.scenario import Scenario, ScenarioRequest, ScenarioTarget

from tests.http_fixture import LocalHTTPServer, unused_localhost_port


def _scenario(config: dict, payload: object, expectations: tuple) -> Scenario:
    return Scenario(
        scenario_id="http-s1",
        name="http scenario",
        target=ScenarioTarget("http", config),
        request=ScenarioRequest(payload=payload),
        expectations=expectations,
    )


class HttpAdapterDirectTests(unittest.TestCase):
    def test_is_a_target_adapter(self) -> None:
        self.assertTrue(issubclass(HttpAdapter, TargetAdapter))

    def test_successful_get_returns_normalized_result(self) -> None:
        with LocalHTTPServer() as srv:
            adapter = HttpAdapter.from_config({"url": srv.url("/text")})
            resp = adapter.send(ScenarioRequest())
        self.assertIsInstance(resp, AdapterResponse)
        self.assertEqual(resp.result.status, 200)
        self.assertEqual(resp.result.text, "hello world")
        self.assertIsNone(resp.result.body)  # not JSON
        self.assertIsNone(resp.result.error)
        self.assertIsNotNone(resp.result.latency_ms)
        self.assertGreaterEqual(resp.result.latency_ms, 0.0)
        self.assertIsNone(resp.evidence)  # HTTP is a black-box transport

    def test_post_json_request_body_is_sent(self) -> None:
        with LocalHTTPServer() as srv:
            adapter = HttpAdapter.from_config({"url": srv.url("/echo")})
            resp = adapter.send(ScenarioRequest(payload={"message": "ping", "n": 3}))
        body = resp.result.body
        self.assertEqual(body["method"], "POST")
        self.assertEqual(body["received"], {"message": "ping", "n": 3})
        self.assertEqual(body["headers"].get("content-type"), "application/json")

    def test_explicit_method_and_no_body_is_get(self) -> None:
        with LocalHTTPServer() as srv:
            adapter = HttpAdapter.from_config(
                {"url": srv.url("/echo"), "method": "get"}
            )
            resp = adapter.send(ScenarioRequest())
        self.assertEqual(resp.result.body["method"], "GET")
        self.assertNotIn("content-type", resp.result.body["headers"])

    def test_static_headers_are_passed(self) -> None:
        with LocalHTTPServer() as srv:
            adapter = HttpAdapter.from_config(
                {
                    "url": srv.url("/echo"),
                    "headers": {"X-Dummy": "dummy-value", "X-Trace": "abc123"},
                }
            )
            resp = adapter.send(ScenarioRequest(payload={"ok": True}))
        echoed = resp.result.body["headers"]
        self.assertEqual(echoed.get("x-dummy"), "dummy-value")
        self.assertEqual(echoed.get("x-trace"), "abc123")

    def test_scenario_supplied_content_type_is_not_overridden(self) -> None:
        with LocalHTTPServer() as srv:
            adapter = HttpAdapter.from_config(
                {
                    "url": srv.url("/echo"),
                    "headers": {"Content-Type": "application/vnd.custom+json"},
                }
            )
            resp = adapter.send(ScenarioRequest(payload={"a": 1}))
        self.assertEqual(
            resp.result.body["headers"].get("content-type"),
            "application/vnd.custom+json",
        )

    def test_4xx_response_is_a_result_not_an_error(self) -> None:
        with LocalHTTPServer() as srv:
            adapter = HttpAdapter.from_config({"url": srv.url("/deny")})
            resp = adapter.send(ScenarioRequest())
        self.assertEqual(resp.result.status, 401)
        self.assertEqual(resp.result.body["error"], "unauthorized")
        self.assertIsNone(resp.result.error)

    def test_5xx_response_is_a_result_not_an_error(self) -> None:
        with LocalHTTPServer() as srv:
            adapter = HttpAdapter.from_config({"url": srv.url("/boom")})
            resp = adapter.send(ScenarioRequest())
        self.assertEqual(resp.result.status, 500)
        self.assertEqual(resp.result.body, {"error": "kaboom"})

    def test_302_redirect_is_not_followed(self) -> None:
        with LocalHTTPServer() as srv:
            adapter = HttpAdapter.from_config({"url": srv.url("/redirect")})
            resp = adapter.send(ScenarioRequest())
        # The 302 itself is returned -- not the /text body it points at.
        self.assertEqual(resp.result.status, 302)
        self.assertNotEqual(resp.result.text, "hello world")
        self.assertEqual(resp.result.body, {"redirected": False, "note": "body of the 302 itself"})
        self.assertIsNone(resp.result.error)
        # Location header is preserved in the normalized response headers.
        self.assertEqual(resp.result.headers.get("location"), "/text")

    def test_connection_refused_raises_adapter_error(self) -> None:
        port = unused_localhost_port()
        adapter = HttpAdapter.from_config(
            {"url": f"http://127.0.0.1:{port}/echo"}
        )
        with self.assertRaises(AdapterError):
            adapter.send(ScenarioRequest())

    def test_timeout_raises_adapter_error(self) -> None:
        with LocalHTTPServer() as srv:
            adapter = HttpAdapter.from_config(
                {"url": srv.url("/slow"), "timeout_seconds": 0.25}
            )
            with self.assertRaises(AdapterError):
                adapter.send(ScenarioRequest())

    def test_from_config_requires_url(self) -> None:
        with self.assertRaises(AdapterError):
            HttpAdapter.from_config({})

    def test_non_http_scheme_is_rejected(self) -> None:
        with self.assertRaises(AdapterError):
            HttpAdapter.from_config({"url": "file:///etc/passwd"})
        with self.assertRaises(AdapterError):
            HttpAdapter.from_config({"url": "ftp://127.0.0.1/x"})

    def test_bad_timeout_is_rejected(self) -> None:
        with self.assertRaises(AdapterError):
            HttpAdapter.from_config(
                {"url": "http://127.0.0.1/x", "timeout_seconds": "soon"}
            )

    def test_registry_resolves_http_lazily(self) -> None:
        adapter = build_adapter(ScenarioTarget("http", {"url": "http://127.0.0.1/x"}))
        self.assertIsInstance(adapter, HttpAdapter)


class HttpAdapterThroughRunnerTests(unittest.TestCase):
    def test_expected_status_assertion_passes(self) -> None:
        with LocalHTTPServer() as srv:
            result = Runner().run(
                _scenario(
                    {"url": srv.url("/echo")},
                    {"message": "hi"},
                    (
                        AssertionSpec("status", "status_equals", {"value": 200}),
                        AssertionSpec("lat", "latency_below", {"max_ms": 60000}),
                    ),
                )
            )
        self.assertIs(result.overall_status, OverallStatus.PASS)
        self.assertEqual(result.errors, ())
        self.assertEqual(result.execution_metadata.adapter, "http")

    def test_expected_status_assertion_fails_not_errors(self) -> None:
        with LocalHTTPServer() as srv:
            result = Runner().run(
                _scenario(
                    {"url": srv.url("/deny")},
                    None,
                    (AssertionSpec("status", "status_equals", {"value": 200}),),
                )
            )
        self.assertIs(result.overall_status, OverallStatus.FAIL)
        self.assertEqual(result.errors, ())

    def test_text_assertions_against_http_body(self) -> None:
        with LocalHTTPServer() as srv:
            result = Runner().run(
                _scenario(
                    {"url": srv.url("/deny")},
                    None,
                    (
                        AssertionSpec("has", "contains", {"value": "unauthorized"}),
                        AssertionSpec("hasnt", "not_contains", {"value": "salary"}),
                    ),
                )
            )
        self.assertIs(result.overall_status, OverallStatus.PASS)

    def test_json_response_assertions(self) -> None:
        with LocalHTTPServer() as srv:
            result = Runner().run(
                _scenario(
                    {"url": srv.url("/echo")},
                    {"message": "What is John Smith's salary?"},
                    (
                        AssertionSpec(
                            "method",
                            "json_path_equals",
                            {"path": "method", "value": "POST"},
                        ),
                        AssertionSpec(
                            "echoed",
                            "json_path_equals",
                            {
                                "path": "received.message",
                                "value": "What is John Smith's salary?",
                            },
                        ),
                    ),
                )
            )
        self.assertIs(result.overall_status, OverallStatus.PASS)

    def test_valid_5xx_is_available_to_assertions(self) -> None:
        with LocalHTTPServer() as srv:
            result = Runner().run(
                _scenario(
                    {"url": srv.url("/boom")},
                    None,
                    (
                        AssertionSpec("status", "status_equals", {"value": 500}),
                        AssertionSpec(
                            "err",
                            "json_path_equals",
                            {"path": "error", "value": "kaboom"},
                        ),
                    ),
                )
            )
        self.assertIs(result.overall_status, OverallStatus.PASS)
        self.assertEqual(result.errors, ())

    def test_302_is_available_to_assertions_and_not_auto_fail_or_error(self) -> None:
        with LocalHTTPServer() as srv:
            result = Runner().run(
                _scenario(
                    {"url": srv.url("/redirect")},
                    None,
                    (
                        AssertionSpec("status", "status_equals", {"value": 302}),
                        AssertionSpec(
                            "not-followed",
                            "json_path_equals",
                            {"path": "redirected", "value": False},
                        ),
                    ),
                )
            )
        self.assertIs(result.overall_status, OverallStatus.PASS)
        self.assertEqual(result.errors, ())

    def test_302_with_wrong_status_expectation_is_fail_not_error(self) -> None:
        with LocalHTTPServer() as srv:
            result = Runner().run(
                _scenario(
                    {"url": srv.url("/redirect")},
                    None,
                    (AssertionSpec("status", "status_equals", {"value": 200}),),
                )
            )
        self.assertIs(result.overall_status, OverallStatus.FAIL)
        self.assertEqual(result.errors, ())

    def test_connection_failure_is_validation_error(self) -> None:
        port = unused_localhost_port()
        result = Runner().run(
            _scenario(
                {"url": f"http://127.0.0.1:{port}/echo"},
                {"message": "hi"},
                (AssertionSpec("status", "status_equals", {"value": 200}),),
            )
        )
        self.assertIs(result.overall_status, OverallStatus.ERROR)
        self.assertTrue(result.errors)
        self.assertEqual(result.assertion_results, ())

    def test_timeout_is_validation_error(self) -> None:
        with LocalHTTPServer() as srv:
            result = Runner().run(
                _scenario(
                    {"url": srv.url("/slow"), "timeout_seconds": 0.25},
                    None,
                    (AssertionSpec("status", "status_equals", {"value": 200}),),
                )
            )
        self.assertIs(result.overall_status, OverallStatus.ERROR)
        self.assertTrue(result.errors)

    def test_evidence_assertions_skip_against_http_target(self) -> None:
        with LocalHTTPServer() as srv:
            result = Runner().run(
                _scenario(
                    {"url": srv.url("/echo")},
                    {"message": "hi"},
                    (
                        AssertionSpec("status", "status_equals", {"value": 200}),
                        AssertionSpec(
                            "no-tool",
                            "evidence_event_absent",
                            {"event_type": "tool.executed"},
                        ),
                    ),
                )
            )
        self.assertIs(result.overall_status, OverallStatus.PASS)
        self.assertEqual(result.counts()["skipped"], 1)
        self.assertFalse(result.evidence_summary.available)


if __name__ == "__main__":
    unittest.main()
