"""Phase 3: scenario suites, directory discovery, batch validation, CLI.

Everything is deterministic and offline: scenarios use ``StaticAdapter`` and
suites are built in temporary directories.
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

from nature_agent_validator.assertions import AssertionSpec
from nature_agent_validator.cli.main import EXIT_ERROR, EXIT_FAIL, EXIT_OK, main
from nature_agent_validator.errors import ScenarioError
from nature_agent_validator.reporting import OverallStatus, ValidationResult
from nature_agent_validator.runner import Runner
from nature_agent_validator.scenario import Scenario, ScenarioRequest, ScenarioTarget
from nature_agent_validator.scenario.serialization import scenario_to_dict
from nature_agent_validator.suite import (
    ScenarioSuite,
    SuiteResult,
    SuiteRunner,
    load_suite,
)

from tests import EXAMPLES_DIR


# --------------------------------------------------------------------------- #
# scenario builders (StaticAdapter, fully deterministic)
# --------------------------------------------------------------------------- #

def _pass_scenario(sid: str = "s-pass") -> Scenario:
    return Scenario(
        scenario_id=sid,
        name=f"{sid} name",
        target=ScenarioTarget("static", {"status": 200, "body": {"answer": "ok"}}),
        request=ScenarioRequest(payload={"m": "hi"}),
        expectations=(
            AssertionSpec("s", "status_equals", {"value": 200}),
            AssertionSpec("t", "contains", {"value": "ok"}),
        ),
    )


def _fail_scenario(sid: str = "s-fail") -> Scenario:
    return Scenario(
        scenario_id=sid,
        name=f"{sid} name",
        target=ScenarioTarget("static", {"status": 500, "body": {"answer": "boom"}}),
        request=ScenarioRequest(payload={"m": "hi"}),
        expectations=(AssertionSpec("s", "status_equals", {"value": 200}),),
    )


def _error_scenario(sid: str = "s-error") -> Scenario:
    # unknown assertion type -> broken definition -> ERROR (not FAIL)
    return Scenario(
        scenario_id=sid,
        name=f"{sid} name",
        target=ScenarioTarget("static", {"status": 200, "text": "x"}),
        request=ScenarioRequest(),
        expectations=(AssertionSpec("bad", "no_such_assertion_type", {}),),
    )


def _blackbox_skip_scenario(sid: str = "s-skip") -> Scenario:
    return Scenario(
        scenario_id=sid,
        name=f"{sid} name",
        target=ScenarioTarget("static", {"status": 200, "body": {"answer": "ok"}}),
        request=ScenarioRequest(),
        expectations=(
            AssertionSpec("t", "contains", {"value": "ok"}),
            AssertionSpec("ev", "evidence_event_not_exists", {"event_type": "tool.executed"}),
        ),
    )


def _evidence_scenario(sid: str = "s-ev") -> Scenario:
    return Scenario(
        scenario_id=sid,
        name=f"{sid} name",
        target=ScenarioTarget(
            "static",
            {
                "status": 200,
                "body": {"answer": "ok"},
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
            },
        ),
        request=ScenarioRequest(),
        expectations=(
            AssertionSpec("a", "evidence_event_exists",
                          {"event_type": "authorization.decision", "attributes": {"decision": "deny"}}),
            AssertionSpec("n", "evidence_event_not_exists", {"event_type": "tool.executed"}),
        ),
    )


def _write_suite(directory: Path, scenarios: dict[str, Scenario]) -> Path:
    for filename, scenario in scenarios.items():
        (directory / filename).write_text(
            json.dumps(scenario_to_dict(scenario)), encoding="utf-8"
        )
    return directory


# --------------------------------------------------------------------------- #
# ScenarioSuite
# --------------------------------------------------------------------------- #

class ScenarioSuiteTests(unittest.TestCase):
    def test_preserves_scenario_order(self) -> None:  # req 1
        scns = (_pass_scenario("a"), _fail_scenario("b"), _pass_scenario("c"))
        suite = ScenarioSuite(name="s", scenarios=scns)
        self.assertEqual([s.scenario_id for s in suite], ["a", "b", "c"])
        self.assertEqual(len(suite), 3)
        self.assertIsInstance(suite.scenarios, tuple)


# --------------------------------------------------------------------------- #
# directory discovery
# --------------------------------------------------------------------------- #

class DiscoveryTests(unittest.TestCase):
    def test_finds_json_files(self) -> None:  # req 2
        with tempfile.TemporaryDirectory() as tmp:
            d = _write_suite(Path(tmp), {
                "one.json": _pass_scenario("one"),
                "two.json": _pass_scenario("two"),
            })
            suite = load_suite(d)
            self.assertEqual({s.scenario_id for s in suite}, {"one", "two"})

    def test_discovery_order_is_lexical(self) -> None:  # req 3
        with tempfile.TemporaryDirectory() as tmp:
            d = _write_suite(Path(tmp), {
                "20_b.json": _pass_scenario("b"),
                "10_a.json": _pass_scenario("a"),
                "30_c.json": _pass_scenario("c"),
            })
            suite = load_suite(d)
            self.assertEqual([s.scenario_id for s in suite], ["a", "b", "c"])

    def test_non_json_files_ignored(self) -> None:  # req 4
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _write_suite(d, {"keep.json": _pass_scenario("keep")})
            (d / "notes.md").write_text("ignore me", encoding="utf-8")
            (d / "data.txt").write_text("{}", encoding="utf-8")
            (d / "scenario.json.bak").write_text("{}", encoding="utf-8")
            suite = load_suite(d)
            self.assertEqual([s.scenario_id for s in suite], ["keep"])

    def test_subdirectories_not_traversed(self) -> None:  # req 5
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _write_suite(d, {"top.json": _pass_scenario("top")})
            sub = d / "nested"
            sub.mkdir()
            _write_suite(sub, {"deep.json": _pass_scenario("deep")})
            # a subdirectory literally named "*.json" must also be skipped
            (d / "trap.json").mkdir()
            suite = load_suite(d)
            self.assertEqual([s.scenario_id for s in suite], ["top"])

    def test_malformed_json_is_loading_error(self) -> None:  # req 6
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _write_suite(d, {"good.json": _pass_scenario("good")})
            (d / "bad.json").write_text("{ not valid json", encoding="utf-8")
            with self.assertRaises(ScenarioError):
                load_suite(d)

    def test_invalid_scenario_is_loading_error(self) -> None:  # req 7
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _write_suite(d, {"good.json": _pass_scenario("good")})
            (d / "invalid.json").write_text(
                json.dumps({"name": "no id", "target": {"adapter": "static"}}),
                encoding="utf-8",
            )
            with self.assertRaises(ScenarioError):
                load_suite(d)

    def test_non_directory_path_is_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "single.json"
            f.write_text(json.dumps(scenario_to_dict(_pass_scenario())), encoding="utf-8")
            with self.assertRaises(ScenarioError):
                load_suite(f)

    def test_empty_directory_is_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ScenarioError):
                load_suite(tmp)


# --------------------------------------------------------------------------- #
# SuiteRunner delegation + sequential execution
# --------------------------------------------------------------------------- #

class SuiteRunnerTests(unittest.TestCase):
    def test_delegates_to_existing_runner(self) -> None:  # req 8
        seen: list[str] = []
        real = Runner()

        class RecordingRunner:
            def run(self, scenario: Scenario) -> ValidationResult:
                seen.append(scenario.scenario_id)
                return real.run(scenario)

        suite = ScenarioSuite("s", (_pass_scenario("x"), _fail_scenario("y")))
        result = SuiteRunner(runner=RecordingRunner()).run(suite)
        self.assertEqual(seen, ["x", "y"])  # exactly one Runner.run per scenario
        self.assertIsInstance(result, SuiteResult)
        self.assertEqual(len(result.results), 2)

    def test_all_scenarios_executed_in_order(self) -> None:  # req 9
        suite = ScenarioSuite(
            "s", (_pass_scenario("a"), _fail_scenario("b"), _pass_scenario("c"))
        )
        result = SuiteRunner().run(suite)
        self.assertEqual(
            [r.scenario_id for r in result.results], ["a", "b", "c"]
        )

    def test_fail_does_not_stop_the_suite(self) -> None:
        # no fail-fast: scenario after the FAIL still runs
        suite = ScenarioSuite("s", (_fail_scenario("a"), _pass_scenario("b")))
        result = SuiteRunner().run(suite)
        self.assertEqual([r.overall_status for r in result.results],
                         [OverallStatus.FAIL, OverallStatus.PASS])


# --------------------------------------------------------------------------- #
# SuiteResult aggregation
# --------------------------------------------------------------------------- #

class SuiteResultTests(unittest.TestCase):
    def _run(self, *scenarios: Scenario) -> SuiteResult:
        return SuiteRunner().run(ScenarioSuite("s", scenarios))

    def test_all_pass_suite_is_pass(self) -> None:  # req 10
        r = self._run(_pass_scenario("a"), _pass_scenario("b"))
        self.assertIs(r.overall_status, OverallStatus.PASS)

    def test_any_fail_no_error_is_fail(self) -> None:  # req 11
        r = self._run(_pass_scenario("a"), _fail_scenario("b"))
        self.assertIs(r.overall_status, OverallStatus.FAIL)

    def test_any_error_is_error(self) -> None:  # req 12
        r = self._run(_pass_scenario("a"), _error_scenario("b"))
        self.assertIs(r.overall_status, OverallStatus.ERROR)

    def test_error_outranks_fail(self) -> None:  # req 13
        r = self._run(_fail_scenario("a"), _error_scenario("b"), _pass_scenario("c"))
        self.assertIs(r.overall_status, OverallStatus.ERROR)

    def test_pass_with_skipped_assertion_stays_pass(self) -> None:  # req 14
        r = self._run(_blackbox_skip_scenario("a"))
        self.assertIs(r.overall_status, OverallStatus.PASS)
        self.assertEqual(r.scenario_counts(), {"pass": 1, "fail": 0, "error": 0})
        self.assertEqual(r.assertion_counts()["skipped"], 1)

    def test_assertion_counts_aggregate(self) -> None:  # req 15
        # pass: 2 pass ; fail: 0 pass + 1 fail ; skip: 1 pass + 1 skip ; ev: 2 pass
        r = self._run(
            _pass_scenario("a"),
            _fail_scenario("b"),
            _blackbox_skip_scenario("c"),
            _evidence_scenario("d"),
        )
        self.assertEqual(
            r.assertion_counts(), {"pass": 2 + 0 + 1 + 2, "fail": 1, "skipped": 1}
        )

    def test_scenario_counts_aggregate(self) -> None:  # req 16
        r = self._run(
            _pass_scenario("a"), _pass_scenario("b"),
            _fail_scenario("c"),
            _error_scenario("d"),
        )
        self.assertEqual(r.scenario_counts(), {"pass": 2, "fail": 1, "error": 1})
        self.assertEqual(r.total, 4)

    def test_blackbox_skip_semantics_survive_suite(self) -> None:  # req 22
        r = self._run(_blackbox_skip_scenario("a"))
        vr = r.results[0]
        self.assertIs(vr.overall_status, OverallStatus.PASS)
        outcomes = [ar.outcome.value for ar in vr.assertion_results]
        self.assertIn("SKIPPED", outcomes)
        self.assertFalse(vr.evidence_summary.available)

    def test_evidence_scenario_works_in_suite(self) -> None:  # req 23
        r = self._run(_evidence_scenario("a"))
        self.assertIs(r.overall_status, OverallStatus.PASS)
        self.assertEqual(r.assertion_counts(), {"pass": 2, "fail": 0, "skipped": 0})
        self.assertTrue(r.results[0].evidence_summary.available)

    def test_to_dict_has_ordered_results_and_counts(self) -> None:  # req 18
        r = self._run(_pass_scenario("a"), _fail_scenario("b"), _pass_scenario("c"))
        d = r.to_dict()
        self.assertEqual(d["overall_status"], "FAIL")
        self.assertEqual(d["total_scenarios"], 3)
        self.assertEqual(d["scenario_counts"], {"pass": 2, "fail": 1, "error": 0})
        self.assertIn("assertion_counts", d)
        self.assertEqual([x["scenario_id"] for x in d["results"]], ["a", "b", "c"])
        json.dumps(d)  # serializable

    def test_summary_lines_show_counts(self) -> None:  # req 17
        r = self._run(_pass_scenario("a"), _fail_scenario("b"))
        text = "\n".join(r.summary_lines())
        self.assertIn("[FAIL]", text)
        self.assertIn("2 scenario(s): 1 pass, 1 fail, 0 error", text)
        self.assertIn("assertions:", text)
        self.assertIn("- [PASS] a", text)
        self.assertIn("- [FAIL] b", text)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

class SuiteCliTests(unittest.TestCase):
    def _dir(self, tmp: str, scenarios: dict[str, Scenario]) -> str:
        return str(_write_suite(Path(tmp), scenarios))

    def test_cli_pass_exit_0(self) -> None:  # req 19
        with tempfile.TemporaryDirectory() as tmp:
            path = self._dir(tmp, {"a.json": _pass_scenario("a"), "b.json": _pass_scenario("b")})
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = main(["validate-suite", path])
        self.assertEqual(code, EXIT_OK, buf.getvalue())
        self.assertIn("[PASS] suite", buf.getvalue())

    def test_cli_fail_exit_1(self) -> None:  # req 20
        with tempfile.TemporaryDirectory() as tmp:
            path = self._dir(tmp, {"a.json": _pass_scenario("a"), "b.json": _fail_scenario("b")})
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = main(["validate-suite", path])
        self.assertEqual(code, EXIT_FAIL, buf.getvalue())
        self.assertIn("[FAIL] suite", buf.getvalue())

    def test_cli_error_exit_2(self) -> None:  # req 21
        with tempfile.TemporaryDirectory() as tmp:
            path = self._dir(tmp, {"a.json": _pass_scenario("a"), "b.json": _error_scenario("b")})
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = main(["validate-suite", path])
        self.assertEqual(code, EXIT_ERROR, buf.getvalue())
        self.assertIn("[ERROR] suite", buf.getvalue())

    def test_cli_loading_error_exit_2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "ok.json").write_text(json.dumps(scenario_to_dict(_pass_scenario())), encoding="utf-8")
            (d / "broken.json").write_text("{ nope", encoding="utf-8")
            err = io.StringIO()
            with redirect_stderr(err):
                code = main(["validate-suite", str(d)])
        self.assertEqual(code, EXIT_ERROR)
        self.assertIn("error:", err.getvalue())

    def test_cli_json_output_ordered(self) -> None:  # req 18 (CLI)
        with tempfile.TemporaryDirectory() as tmp:
            path = self._dir(tmp, {
                "1.json": _pass_scenario("one"),
                "2.json": _fail_scenario("two"),
                "3.json": _pass_scenario("three"),
            })
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = main(["validate-suite", path, "--json"])
        self.assertEqual(code, EXIT_FAIL)
        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["overall_status"], "FAIL")
        self.assertEqual(
            [r["scenario_id"] for r in payload["results"]], ["one", "two", "three"]
        )
        self.assertEqual(payload["scenario_counts"], {"pass": 2, "fail": 1, "error": 0})

    def test_cli_on_shipped_example_suite(self) -> None:
        suite_dir = EXAMPLES_DIR / "suite"
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["validate-suite", str(suite_dir)])
        # the shipped example suite intentionally contains one FAIL scenario
        self.assertEqual(code, EXIT_FAIL, buf.getvalue())
        out = buf.getvalue()
        self.assertIn("4 scenario(s): 3 pass, 1 fail, 0 error", out)
        self.assertIn("1 skipped", out)


if __name__ == "__main__":
    unittest.main()
