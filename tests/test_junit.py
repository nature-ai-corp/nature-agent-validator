"""Phase 4: JUnit XML export of a SuiteResult, and the validate-suite CLI flags.

Deterministic and offline. Unit tests build ``SuiteResult`` directly; CLI
tests build suites in temporary directories with ``StaticAdapter`` scenarios.
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
from pathlib import Path

from nature_agent_validator.assertions import AssertionSpec
from nature_agent_validator.assertions.result import AssertionOutcome, AssertionResult
from nature_agent_validator.cli.main import EXIT_ERROR, EXIT_FAIL, EXIT_OK, main
from nature_agent_validator.reporting import (
    EvidenceSummary,
    ExecutionMetadata,
    OverallStatus,
    ValidationResult,
)
from nature_agent_validator.reporting.junit import suite_result_to_junit_xml
from nature_agent_validator.scenario import Scenario, ScenarioRequest, ScenarioTarget
from nature_agent_validator.scenario.serialization import scenario_to_dict
from nature_agent_validator.suite import ScenarioSuite, SuiteResult, SuiteRunner

_T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
_MD = ExecutionMetadata(adapter="static", started_at=_T0, finished_at=_T0, duration_ms=12.5)


# --------------------------------------------------------------------------- #
# builders
# --------------------------------------------------------------------------- #

def _ar(aid: str, outcome: AssertionOutcome, message: str = "") -> AssertionResult:
    return AssertionResult(aid, "contains", outcome, message=message)


def _vr(
    sid: str,
    status: OverallStatus,
    *,
    assertions: tuple[AssertionResult, ...] = (),
    errors: tuple[str, ...] = (),
    name: str | None = None,
    md: ExecutionMetadata | None = _MD,
) -> ValidationResult:
    return ValidationResult(
        scenario_id=sid,
        scenario_name=name if name is not None else f"{sid} name",
        overall_status=status,
        assertion_results=assertions,
        execution_metadata=md,
        evidence_summary=EvidenceSummary(available=False),
        errors=errors,
    )


def _pass_vr(sid: str = "p") -> ValidationResult:
    return _vr(sid, OverallStatus.PASS, assertions=(_ar("a", AssertionOutcome.PASS),))


def _fail_vr(sid: str = "f") -> ValidationResult:
    return _vr(
        sid,
        OverallStatus.FAIL,
        assertions=(
            _ar("a", AssertionOutcome.PASS),
            _ar("b", AssertionOutcome.FAIL, "status 500 != expected 200"),
        ),
    )


def _error_vr(sid: str = "e") -> ValidationResult:
    return _vr(
        sid,
        OverallStatus.ERROR,
        errors=("adapter send failed: AdapterError('transport down')",),
    )


def _pass_with_skip_vr(sid: str = "s") -> ValidationResult:
    return _vr(
        sid,
        OverallStatus.PASS,
        assertions=(
            _ar("a", AssertionOutcome.PASS),
            _ar("b", AssertionOutcome.PASS),
            _ar("c", AssertionOutcome.PASS),
            _ar("d", AssertionOutcome.SKIPPED, "namespace not covered"),
        ),
    )


def _suite(*results: ValidationResult, name: str = "demo") -> SuiteResult:
    return SuiteResult(name=name, results=results)


# --------------------------------------------------------------------------- #
# StaticAdapter scenario builders for CLI tests
# --------------------------------------------------------------------------- #

def _pass_scenario(sid: str) -> Scenario:
    return Scenario(
        scenario_id=sid, name=f"{sid} name",
        target=ScenarioTarget("static", {"status": 200, "body": {"answer": "ok"}}),
        request=ScenarioRequest(),
        expectations=(AssertionSpec("s", "status_equals", {"value": 200}),),
    )


def _fail_scenario(sid: str) -> Scenario:
    return Scenario(
        scenario_id=sid, name=f"{sid} name",
        target=ScenarioTarget("static", {"status": 500, "body": {"answer": "boom"}}),
        request=ScenarioRequest(),
        expectations=(AssertionSpec("s", "status_equals", {"value": 200}),),
    )


def _error_scenario(sid: str) -> Scenario:
    return Scenario(
        scenario_id=sid, name=f"{sid} name",
        target=ScenarioTarget("static", {"status": 200}),
        request=ScenarioRequest(),
        expectations=(AssertionSpec("bad", "no_such_type", {}),),
    )


def _write(tmp: str, scenarios: dict[str, Scenario]) -> str:
    d = Path(tmp)
    for fn, sc in scenarios.items():
        (d / fn).write_text(json.dumps(scenario_to_dict(sc)), encoding="utf-8")
    return str(d)


# --------------------------------------------------------------------------- #
# reporter unit tests
# --------------------------------------------------------------------------- #

class JUnitReporterTests(unittest.TestCase):
    def test_parses_with_stdlib(self) -> None:  # req 1
        xml = suite_result_to_junit_xml(_suite(_pass_vr(), _fail_vr()))
        root = ET.fromstring(xml)
        self.assertEqual(root.tag, "testsuite")

    def test_one_scenario_one_testcase(self) -> None:  # req 2
        root = ET.fromstring(
            suite_result_to_junit_xml(_suite(_pass_vr("a"), _fail_vr("b"), _error_vr("c")))
        )
        self.assertEqual(len(root.findall("testcase")), 3)

    def test_tests_count_equals_scenario_count(self) -> None:  # req 3
        root = ET.fromstring(
            suite_result_to_junit_xml(_suite(_pass_vr(), _pass_vr("x"), _fail_vr()))
        )
        self.assertEqual(root.get("tests"), "3")

    def test_pass_testcase_has_no_failure_error_skipped(self) -> None:  # req 4
        root = ET.fromstring(suite_result_to_junit_xml(_suite(_pass_vr("a"))))
        tc = root.find("testcase")
        self.assertIsNone(tc.find("failure"))
        self.assertIsNone(tc.find("error"))
        self.assertIsNone(tc.find("skipped"))

    def test_fail_testcase_has_one_failure(self) -> None:  # req 5
        root = ET.fromstring(suite_result_to_junit_xml(_suite(_fail_vr("f"))))
        tc = root.find("testcase")
        self.assertEqual(len(tc.findall("failure")), 1)
        self.assertIsNone(tc.find("error"))
        self.assertIsNone(tc.find("skipped"))

    def test_error_testcase_has_one_error(self) -> None:  # req 6
        root = ET.fromstring(suite_result_to_junit_xml(_suite(_error_vr("e"))))
        tc = root.find("testcase")
        self.assertEqual(len(tc.findall("error")), 1)
        self.assertIsNone(tc.find("failure"))
        self.assertIsNone(tc.find("skipped"))

    def test_assertion_skipped_does_not_create_testcase_skipped(self) -> None:  # req 7, 11
        root = ET.fromstring(suite_result_to_junit_xml(_suite(_pass_with_skip_vr("s"))))
        tc = root.find("testcase")
        self.assertIsNone(tc.find("skipped"))
        self.assertIsNone(tc.find("failure"))
        self.assertIsNone(tc.find("error"))  # still a passing testcase

    def test_testsuite_skipped_is_zero_with_skipped_assertions(self) -> None:  # req 8
        root = ET.fromstring(
            suite_result_to_junit_xml(_suite(_pass_with_skip_vr(), _pass_with_skip_vr("s2")))
        )
        self.assertEqual(root.get("skipped"), "0")

    def test_testsuite_failures_equals_scenario_fail_count(self) -> None:  # req 9
        root = ET.fromstring(
            suite_result_to_junit_xml(_suite(_pass_vr(), _fail_vr("f1"), _fail_vr("f2"), _error_vr()))
        )
        self.assertEqual(root.get("failures"), "2")

    def test_testsuite_errors_equals_scenario_error_count(self) -> None:  # req 10
        root = ET.fromstring(
            suite_result_to_junit_xml(_suite(_fail_vr(), _error_vr("e1"), _error_vr("e2")))
        )
        self.assertEqual(root.get("errors"), "2")

    def test_scenario_ordering_preserved(self) -> None:  # req 12
        root = ET.fromstring(
            suite_result_to_junit_xml(
                _suite(_pass_vr("first"), _fail_vr("second"), _pass_vr("third"))
            )
        )
        props = [tc.find("properties/property[@name='scenario_id']").get("value")
                 for tc in root.findall("testcase")]
        self.assertEqual(props, ["first", "second", "third"])

    def test_suite_name_maps_to_classname_and_testsuite_name(self) -> None:  # req 13
        root = ET.fromstring(suite_result_to_junit_xml(_suite(_pass_vr(), name="my-suite")))
        self.assertEqual(root.get("name"), "my-suite")
        self.assertEqual(root.find("testcase").get("classname"), "my-suite")

    def test_scenario_identity_preserved(self) -> None:  # req 14
        root = ET.fromstring(
            suite_result_to_junit_xml(_suite(_vr("scn-42", OverallStatus.PASS, name="Human Name")))
        )
        tc = root.find("testcase")
        self.assertEqual(tc.get("name"), "Human Name")
        self.assertEqual(
            tc.find("properties/property[@name='scenario_id']").get("value"), "scn-42"
        )

    def test_scenario_identity_falls_back_to_id_when_no_name(self) -> None:  # req 14
        root = ET.fromstring(
            suite_result_to_junit_xml(_suite(_vr("only-id", OverallStatus.PASS, name="")))
        )
        self.assertEqual(root.find("testcase").get("name"), "only-id")

    def test_failure_diagnostics_are_concise(self) -> None:  # req 15
        root = ET.fromstring(suite_result_to_junit_xml(_suite(_fail_vr("f"))))
        failure = root.find("testcase/failure")
        self.assertEqual(failure.get("message"), "1 assertion(s) failed")
        self.assertIn("[contains] b: status 500 != expected 200", failure.text)
        self.assertLess(len(failure.text), 500)

    def test_error_diagnostics_are_concise(self) -> None:  # req 16
        root = ET.fromstring(suite_result_to_junit_xml(_suite(_error_vr("e"))))
        error = root.find("testcase/error")
        self.assertEqual(error.get("message"), "scenario execution could not complete")
        self.assertIn("transport down", error.text)
        self.assertLess(len(error.text), 500)

    def test_xml_escaping(self) -> None:  # req 17
        vr = _vr(
            's&<>"',
            OverallStatus.FAIL,
            name='name & <tag> "q\'',
            assertions=(_ar("x", AssertionOutcome.FAIL, 'bad & <chars> "here"'),),
        )
        xml = suite_result_to_junit_xml(_suite(vr, name='suite & <x>'))
        self.assertNotIn("<tag>", xml)  # raw markup must be escaped
        self.assertIn("&amp;", xml)
        root = ET.fromstring(xml)  # still parses
        tc = root.find("testcase")
        self.assertEqual(tc.get("name"), 'name & <tag> "q\'')
        self.assertIn('bad & <chars> "here"', tc.find("failure").text)

    def test_deterministic_for_same_suite_result(self) -> None:  # req 18
        sr = _suite(_pass_vr("a"), _fail_vr("b"), _error_vr("c"), _pass_with_skip_vr("d"))
        self.assertEqual(suite_result_to_junit_xml(sr), suite_result_to_junit_xml(sr))

    def test_no_wallclock_timestamp_or_random_id(self) -> None:  # req 19
        xml = suite_result_to_junit_xml(_suite(_pass_vr(), _fail_vr()))
        self.assertNotIn("timestamp", xml)
        self.assertNotIn("hostname", xml)
        self.assertNotIn("2026-01-01", xml)  # no ISO datetime leaked from ExecutionMetadata
        # 'time' is a duration (allowed by the handoff), not a clock value
        self.assertRegex(xml, r'time="\d+\.\d{3}"')

    def test_time_omitted_when_no_execution_metadata(self) -> None:  # req 13 (timing)
        root = ET.fromstring(
            suite_result_to_junit_xml(_suite(_vr("nomd", OverallStatus.PASS, md=None)))
        )
        self.assertIsNone(root.find("testcase").get("time"))
        self.assertIsNone(root.get("time"))

    # -- security / redaction ------------------------------------------------ #

    def test_does_not_emit_assertion_observed_body(self) -> None:
        # a target that echoed a credential into its response body
        leaky = AssertionResult(
            "leak", "contains", AssertionOutcome.FAIL,
            expected="text contains 'ok'",
            observed='{"headers":{"authorization":"Bearer sk-SECRET-TOKEN"},"cookie":"sid=abc"}',
            message="'ok' not found in response text",
        )
        xml = suite_result_to_junit_xml(_suite(_vr("x", OverallStatus.FAIL, assertions=(leaky,))))
        for secret in ("sk-SECRET-TOKEN", "Bearer", "authorization", "Cookie", "cookie", "sid=abc"):
            self.assertNotIn(secret, xml)
        # the safe normalized message is still present
        self.assertIn("'ok' not found in response text", xml)

    def test_evidence_payload_not_dumped(self) -> None:
        vr = _vr("ev", OverallStatus.PASS, assertions=(_ar("a", AssertionOutcome.PASS),))
        xml = suite_result_to_junit_xml(_suite(vr))
        self.assertNotIn("attributes", xml)
        self.assertNotIn("Bearer", xml)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

class JUnitCliTests(unittest.TestCase):
    def test_junit_stdout_contains_xml_only(self) -> None:  # req 20
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, {"a.json": _pass_scenario("a"), "b.json": _pass_scenario("b")})
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = main(["validate-suite", path, "--junit"])
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(err.getvalue(), "")
        body = out.getvalue()
        self.assertTrue(body.lstrip().startswith("<?xml"))
        ET.fromstring(body)  # parses
        self.assertNotIn("[PASS] suite", body)  # no human text mixed in

    def test_junit_file_output_writes_valid_utf8_xml(self) -> None:  # req 21
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, {"a.json": _pass_scenario("a")})
            target = Path(tmp) / "report.xml"
            out = io.StringIO()
            with redirect_stdout(out):
                code = main(["validate-suite", path, "--junit-output", str(target)])
            self.assertEqual(code, EXIT_OK)
            raw = target.read_bytes()
            raw.decode("utf-8")  # valid UTF-8
            root = ET.fromstring(raw)
            self.assertEqual(root.tag, "testsuite")
            self.assertIn("[PASS] suite", out.getvalue())  # human summary preserved on stdout

    def test_junit_file_output_preserves_fail_exit(self) -> None:  # req 22
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, {"a.json": _pass_scenario("a"), "b.json": _fail_scenario("b")})
            target = Path(tmp) / "r.xml"
            with redirect_stdout(io.StringIO()):
                code = main(["validate-suite", path, "--junit-output", str(target)])
            self.assertEqual(code, EXIT_FAIL)
            self.assertEqual(ET.fromstring(target.read_bytes()).get("failures"), "1")

    def test_cli_pass_exit_0(self) -> None:  # req 23
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, {"a.json": _pass_scenario("a")})
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["validate-suite", path, "--junit"]), EXIT_OK)

    def test_cli_fail_exit_1(self) -> None:  # req 24
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, {"a.json": _fail_scenario("a")})
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["validate-suite", path, "--junit"]), EXIT_FAIL)

    def test_cli_error_exit_2(self) -> None:  # req 25
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, {"a.json": _error_scenario("a")})
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["validate-suite", path, "--junit"]), EXIT_ERROR)

    def test_report_write_failure_does_not_return_success(self) -> None:  # req 26
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, {"a.json": _pass_scenario("a")})  # suite would PASS
            bad = str(Path(tmp) / "missing-subdir" / "r.xml")
            err = io.StringIO()
            with redirect_stdout(io.StringIO()), redirect_stderr(err):
                code = main(["validate-suite", path, "--junit-output", bad])
        self.assertEqual(code, EXIT_ERROR)  # not EXIT_OK
        self.assertIn("could not write JUnit report", err.getvalue())

    def test_json_output_unchanged(self) -> None:  # req 27
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, {"a.json": _pass_scenario("a"), "b.json": _fail_scenario("b")})
            out = io.StringIO()
            with redirect_stdout(out):
                code = main(["validate-suite", path, "--json"])
        self.assertEqual(code, EXIT_FAIL)
        payload = json.loads(out.getvalue())
        self.assertEqual(
            set(payload), {"suite", "overall_status", "total_scenarios",
                           "scenario_counts", "assertion_counts", "results"},
        )
        self.assertEqual([r["scenario_id"] for r in payload["results"]], ["a", "b"])

    def test_conflicting_machine_output_flags_rejected(self) -> None:  # req 28
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, {"a.json": _pass_scenario("a")})
            for combo in (
                ["--json", "--junit"],
                ["--junit", "--junit-output", "x.xml"],
                ["--json", "--junit-output", "x.xml"],
            ):
                with self.assertRaises(SystemExit) as ctx, redirect_stderr(io.StringIO()):
                    main(["validate-suite", path, *combo])
                self.assertEqual(ctx.exception.code, 2)  # argparse usage error

    def test_existing_human_output_intact(self) -> None:  # req 29
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, {"a.json": _pass_scenario("a"), "b.json": _fail_scenario("b")})
            out = io.StringIO()
            with redirect_stdout(out):
                code = main(["validate-suite", path])
        self.assertEqual(code, EXIT_FAIL)
        text = out.getvalue()
        self.assertIn("[FAIL] suite", text)
        self.assertIn("2 scenario(s): 1 pass, 1 fail, 0 error", text)
        self.assertNotIn("<?xml", text)

    def test_junit_output_utf8_non_ascii_name(self) -> None:  # req 21 (encoding)
        sc = _pass_scenario("u")
        sc = Scenario(
            scenario_id="u", name="refusé — déni",
            target=sc.target, request=sc.request, expectations=sc.expectations,
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, {"u.json": sc})
            target = Path(tmp) / "u.xml"
            with redirect_stdout(io.StringIO()):
                main(["validate-suite", path, "--junit-output", str(target)])
            root = ET.fromstring(target.read_bytes())
            self.assertEqual(root.find("testcase").get("name"), "refusé — déni")


if __name__ == "__main__":
    unittest.main()
