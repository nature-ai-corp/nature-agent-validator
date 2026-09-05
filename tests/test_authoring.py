"""Phase 6 -- scenario authoring & developer UX.

Covers the frozen acceptance groups:

* generated starter acceptance (§10)
* static-check security acceptance (§11)
* describe acceptance (§12)
* assertion-catalog drift (§9 / §12)

plus the ``nav scenario`` CLI dispatch and exit codes.
"""

from __future__ import annotations

import io
import json
import os
import socket
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from nature_agent_validator import authoring
from nature_agent_validator.adapters import available_adapter_names
from nature_agent_validator.assertions import known_assertion_types
from nature_agent_validator.cli.main import EXIT_ERROR, EXIT_OK, main
from nature_agent_validator.configuration import load_environment
from nature_agent_validator.errors import ScenarioError
from nature_agent_validator.scenario.serialization import load_scenario


def _run(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


# --------------------------------------------------------------------------- #
# §10 -- generated starter acceptance
# --------------------------------------------------------------------------- #


class ScenarioInitTests(unittest.TestCase):
    def test_init_creates_a_file(self) -> None:
        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "salary-denied.json"
            code, out, _ = _run(["scenario", "init", str(dest)])
            self.assertEqual(code, EXIT_OK, out)
            self.assertTrue(dest.is_file())

    def test_generated_file_is_deterministic(self) -> None:
        with TemporaryDirectory() as a, TemporaryDirectory() as b:
            pa = Path(a) / "salary-denied.json"
            pb = Path(b) / "salary-denied.json"
            authoring.init_scenario_file(pa)
            authoring.init_scenario_file(pb)
            self.assertEqual(pa.read_bytes(), pb.read_bytes())
            text = pa.read_text(encoding="utf-8")
            self.assertNotIn("\r", text)
            self.assertTrue(text.endswith("}\n"))
            self.assertIn('\n  "scenario_id"', text)  # 2-space indent

    def test_generated_file_parses_through_authoritative_loader(self) -> None:
        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "hello-agent.json"
            authoring.init_scenario_file(dest)
            scenario = load_scenario(dest)  # the runtime loader, unchanged
            self.assertEqual(scenario.scenario_id, "hello-agent")
            self.assertEqual(scenario.target.adapter, "http")

    def test_generated_file_passes_scenario_check(self) -> None:
        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "hello-agent.json"
            authoring.init_scenario_file(dest)
            self.assertEqual(authoring.check_scenario_file(dest), [])
            code, out, _ = _run(["scenario", "check", str(dest)])
            self.assertEqual(code, EXIT_OK, out)

    def test_second_init_to_same_path_fails_exit_2_and_keeps_contents(self) -> None:
        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "hello-agent.json"
            authoring.init_scenario_file(dest)
            original = dest.read_bytes()
            code, _, err = _run(["scenario", "init", str(dest)])
            self.assertEqual(code, EXIT_ERROR)
            self.assertIn("refusing to overwrite", err)
            self.assertEqual(dest.read_bytes(), original)

    def test_init_helper_raises_scenario_error_on_existing_file(self) -> None:
        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "x.json"
            dest.write_text("keep me", encoding="utf-8")
            with self.assertRaises(ScenarioError):
                authoring.init_scenario_file(dest)
            self.assertEqual(dest.read_text(encoding="utf-8"), "keep me")

    def test_init_missing_parent_directory_is_exit_2(self) -> None:
        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "no" / "such" / "dir" / "s.json"
            code, _, err = _run(["scenario", "init", str(dest)])
            self.assertEqual(code, EXIT_ERROR)
            self.assertIn("could not write", err)

    def test_generated_file_contains_no_credential_or_secret_material(self) -> None:
        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "hello-agent.json"
            authoring.init_scenario_file(dest)
            text = dest.read_text(encoding="utf-8")
            lowered = text.lower()
            for needle in (
                "secret",
                "token",
                "password",
                "authorization",
                "api_key",
                "apikey",
                "x-api-key",
                "bearer",
            ):
                self.assertNotIn(needle, lowered, needle)
            self.assertNotIn("${", text)
            data = json.loads(text)
            self.assertNotIn("secret_headers", data["target"]["config"])
            self.assertNotIn("headers", data["target"]["config"])

    def test_generated_file_does_not_depend_on_environment_variables(self) -> None:
        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "hello-agent.json"
            authoring.init_scenario_file(dest)
            data = json.loads(dest.read_text(encoding="utf-8"))
            # No secret-header references => nothing is read from os.environ,
            # so the check result cannot depend on the environment.
            self.assertNotIn("secret_headers", json.dumps(data))
            with mock.patch.dict(os.environ, {}, clear=True):
                self.assertEqual(authoring.check_scenario_file(dest), [])

    def test_filename_derives_id_and_name(self) -> None:
        self.assertEqual(
            authoring.build_starter_scenario(Path("/x/salary-denied.json"))[
                "scenario_id"
            ],
            "salary-denied",
        )
        self.assertEqual(
            authoring.build_starter_scenario(Path("/x/salary-denied.json"))["name"],
            "Salary Denied",
        )


# --------------------------------------------------------------------------- #
# §11 -- static-check security acceptance
# --------------------------------------------------------------------------- #


_HTTP_SCENARIO = {
    "scenario_id": "sec",
    "name": "security check",
    "target": {
        "adapter": "http",
        "config": {"url": "http://127.0.0.1:9/agent", "method": "POST"},
    },
    "request": {"payload": {"message": "hi"}},
    "expectations": [
        {"assertion_id": "s", "type": "status_equals", "config": {"value": 200}},
        {"assertion_id": "c", "type": "contains", "config": {"value": "ok"}},
    ],
}


def _write(tmp: str, name: str, body: dict) -> Path:
    p = Path(tmp) / name
    p.write_text(json.dumps(body), encoding="utf-8")
    return p


class ScenarioCheckSecurityTests(unittest.TestCase):
    def test_check_does_not_invoke_httpadapter_send(self) -> None:
        from nature_agent_validator.adapters.http import HttpAdapter

        with TemporaryDirectory() as tmp:
            path = _write(tmp, "s.json", _HTTP_SCENARIO)
            with mock.patch.object(
                HttpAdapter, "send", side_effect=AssertionError("send called")
            ) as sent:
                self.assertEqual(authoring.check_scenario_file(path), [])
            sent.assert_not_called()

    def test_check_opens_no_socket(self) -> None:
        with TemporaryDirectory() as tmp:
            path = _write(tmp, "s.json", _HTTP_SCENARIO)
            with mock.patch.object(
                socket, "socket", side_effect=AssertionError("socket opened")
            ):
                self.assertEqual(authoring.check_scenario_file(path), [])

    def test_check_resolves_no_secret_headers(self) -> None:
        body = json.loads(json.dumps(_HTTP_SCENARIO))
        body["target"]["config"]["secret_headers"] = [
            {"header": "Authorization", "env": "NAV_P6_DEFINITELY_UNSET", "prefix": "Bearer "}
        ]
        self.assertNotIn("NAV_P6_DEFINITELY_UNSET", os.environ)
        with TemporaryDirectory() as tmp:
            path = _write(tmp, "s.json", body)
            # An unset secret env var is a *runtime* ERROR; a static check must
            # not resolve it, so the scenario still checks clean.
            self.assertEqual(authoring.check_scenario_file(path), [])

    def test_check_does_not_modify_the_scenario_file(self) -> None:
        with TemporaryDirectory() as tmp:
            path = _write(tmp, "s.json", _HTTP_SCENARIO)
            before = path.read_bytes()
            listing = sorted(os.listdir(tmp))
            authoring.check_scenario_file(path)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(sorted(os.listdir(tmp)), listing)  # wrote nothing

    def test_valid_scenario_returns_zero_diagnostics(self) -> None:
        with TemporaryDirectory() as tmp:
            path = _write(tmp, "s.json", _HTTP_SCENARIO)
            self.assertEqual(authoring.check_scenario_file(path), [])

    def test_invalid_structure_returns_diagnostic_exit_2(self) -> None:
        bad = {"scenario_id": "x", "target": {"adapter": "static"}}
        with TemporaryDirectory() as tmp:
            path = _write(tmp, "s.json", bad)
            diags = authoring.check_scenario_file(path)
            self.assertTrue(diags)
            self.assertIn("name", diags[0])
            code, _, err = _run(["scenario", "check", str(path)])
            self.assertEqual(code, EXIT_ERROR)
            self.assertIn("name", err)

    def test_malformed_json_gives_useful_diagnostic_exit_2(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.json"
            path.write_text('{ "scenario_id": ', encoding="utf-8")
            diags = authoring.check_scenario_file(path)
            self.assertEqual(len(diags), 1)
            self.assertIn("invalid JSON", diags[0])
            self.assertRegex(diags[0], r"line \d+ column \d+")
            code, _, err = _run(["scenario", "check", str(path)])
            self.assertEqual(code, EXIT_ERROR)

    def test_unknown_assertion_type_is_clearly_reported(self) -> None:
        body = json.loads(json.dumps(_HTTP_SCENARIO))
        body["expectations"] = [
            {"assertion_id": "a", "type": "totally_made_up", "config": {}}
        ]
        with TemporaryDirectory() as tmp:
            path = _write(tmp, "s.json", body)
            diags = authoring.check_scenario_file(path)
            self.assertEqual(len(diags), 1)
            self.assertIn("expectations[0].type", diags[0])
            self.assertIn("unknown assertion type", diags[0])
            self.assertIn("totally_made_up", diags[0])

    def test_representative_type_failures_are_reported(self) -> None:
        body = json.loads(json.dumps(_HTTP_SCENARIO))
        body["target"]["config"] = {}  # http adapter: url required
        body["expectations"] = [
            {"assertion_id": "a", "type": "status_equals", "config": {"value": "x"}},
            {"assertion_id": "b", "type": "regex_match", "config": {}},
            {"assertion_id": "c", "type": "json_path_equals", "config": {"path": "a"}},
        ]
        with TemporaryDirectory() as tmp:
            path = _write(tmp, "s.json", body)
            diags = authoring.check_scenario_file(path)
            joined = "\n".join(diags)
            self.assertIn("target: http adapter requires 'url'", joined)
            self.assertIn("expectations[0] (status_equals)", joined)
            self.assertIn("must be an integer", joined)
            self.assertIn("expectations[1] (regex_match)", joined)
            self.assertIn("expectations[2] (json_path_equals)", joined)

    def test_check_of_valid_scenario_cli_exit_0(self) -> None:
        with TemporaryDirectory() as tmp:
            path = _write(tmp, "s.json", _HTTP_SCENARIO)
            code, out, _ = _run(["scenario", "check", str(path)])
            self.assertEqual(code, EXIT_OK, out)
            self.assertIn("valid", out)


# --------------------------------------------------------------------------- #
# §12 -- describe acceptance
# --------------------------------------------------------------------------- #


class ScenarioDescribeTests(unittest.TestCase):
    def test_describe_succeeds_and_reflects_current_structure(self) -> None:
        code, out, _ = _run(["scenario", "describe"])
        self.assertEqual(code, EXIT_OK)
        for field in (
            "scenario_id",
            "name",
            "target",
            "request",
            "expectations",
            "metadata",
        ):
            self.assertIn(field, out)

    def test_describe_mentions_every_available_adapter(self) -> None:
        _, out, _ = _run(["scenario", "describe"])
        for adapter in available_adapter_names():
            self.assertIn(adapter, out)
        self.assertIn("http", out)
        self.assertIn("static", out)

    def test_describe_marks_environment_config_as_separate_runtime_config(
        self,
    ) -> None:
        _, out, _ = _run(["scenario", "describe"])
        self.assertIn("--environment", out)
        self.assertIn("EnvironmentConfig", out)
        # framed as separate from the scenario
        self.assertRegex(out, r"[Ss]eparate")

    def test_describe_assertions_succeeds(self) -> None:
        code, out, _ = _run(["scenario", "describe", "assertions"])
        self.assertEqual(code, EXIT_OK)
        self.assertTrue(out.strip())

    def test_describe_assertions_lists_every_supported_type(self) -> None:
        _, out, _ = _run(["scenario", "describe", "assertions"])
        for name in known_assertion_types():
            self.assertIn(name, out, name)

    def test_describe_assertions_separates_response_and_evidence(self) -> None:
        _, out, _ = _run(["scenario", "describe", "assertions"])
        self.assertIn("Response", out)
        self.assertIn("Evidence assertions", out)
        # the evidence section comes after the response section
        self.assertLess(out.index("Response"), out.index("Evidence assertions"))

    def test_describe_assertions_states_evidence_semantics(self) -> None:
        _, out, _ = _run(["scenario", "describe", "assertions"])
        self.assertIn("SKIPPED", out)
        self.assertIn(
            "absence of evidence is not evidence of absence", out.lower()
        )

    def test_describe_topic_choices_are_constrained(self) -> None:
        # argparse rejects an unknown topic (exit 2 from argparse itself)
        with self.assertRaises(SystemExit):
            _run(["scenario", "describe", "nonsense"])


# --------------------------------------------------------------------------- #
# §9 / §12 -- the catalog cannot silently drift
# --------------------------------------------------------------------------- #


class AssertionCatalogDriftTests(unittest.TestCase):
    def test_catalog_matches_the_live_registry_exactly(self) -> None:
        self.assertEqual(
            set(authoring.catalog_assertion_names()),
            set(known_assertion_types()),
            "authoring.ASSERTION_CATALOG has drifted from the assertion "
            "registry -- add/remove the AssertionDoc row to match",
        )

    def test_every_catalog_type_is_buildable(self) -> None:
        from nature_agent_validator.assertions import AssertionSpec, build_assertion

        for name in authoring.catalog_assertion_names():
            build_assertion(AssertionSpec("probe", name, {}))

    def test_each_catalog_row_has_a_known_category(self) -> None:
        for doc in authoring.ASSERTION_CATALOG:
            self.assertIn(doc.category, {"response", "evidence"})


# --------------------------------------------------------------------------- #
# CLI dispatch
# --------------------------------------------------------------------------- #


class ScenarioCliDispatchTests(unittest.TestCase):
    def test_scenario_requires_a_subcommand(self) -> None:
        with self.assertRaises(SystemExit):
            _run(["scenario"])

    def test_full_first_run_flow(self) -> None:
        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "hello-agent.json"
            self.assertEqual(_run(["scenario", "init", str(dest)])[0], EXIT_OK)
            self.assertEqual(_run(["scenario", "check", str(dest)])[0], EXIT_OK)

    def test_check_missing_file_is_exit_2(self) -> None:
        code, _, err = _run(["scenario", "check", "/no/such/scenario.json"])
        self.assertEqual(code, EXIT_ERROR)
        self.assertIn("invalid", err)


# --------------------------------------------------------------------------- #
# Alpha 2A -- `nav scenario init --url/--method`
# --------------------------------------------------------------------------- #


class ScenarioInitUrlMethodTests(unittest.TestCase):
    def test_omitting_flags_reproduces_prior_starter_exactly(self) -> None:
        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "hello-agent.json"
            authoring.init_scenario_file(dest)
            data = json.loads(dest.read_text(encoding="utf-8"))
        self.assertEqual(
            data["target"]["config"]["url"], "http://127.0.0.1:8080/agent"
        )
        self.assertEqual(data["target"]["config"]["method"], "POST")

    def test_url_override_is_applied_and_still_checks_valid(self) -> None:
        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "agent.json"
            authoring.init_scenario_file(dest, url="https://agent.example.com/chat")
            data = json.loads(dest.read_text(encoding="utf-8"))
            self.assertEqual(
                data["target"]["config"]["url"], "https://agent.example.com/chat"
            )
            self.assertEqual(authoring.check_scenario_file(dest), [])

    def test_method_override_is_applied(self) -> None:
        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "agent.json"
            authoring.init_scenario_file(dest, method="GET")
            data = json.loads(dest.read_text(encoding="utf-8"))
        self.assertEqual(data["target"]["config"]["method"], "GET")

    def test_cli_scenario_init_accepts_url_and_method(self) -> None:
        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "agent.json"
            code, out, _ = _run(
                [
                    "scenario",
                    "init",
                    str(dest),
                    "--url",
                    "https://agent.example.com/chat",
                    "--method",
                    "GET",
                ]
            )
            self.assertEqual(code, EXIT_OK, out)
            data = json.loads(dest.read_text(encoding="utf-8"))
        self.assertEqual(
            data["target"]["config"]["url"], "https://agent.example.com/chat"
        )
        self.assertEqual(data["target"]["config"]["method"], "GET")


# --------------------------------------------------------------------------- #
# Alpha 2A -- environment authoring: init
# --------------------------------------------------------------------------- #


class EnvironmentInitTests(unittest.TestCase):
    def test_init_creates_a_file(self) -> None:
        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "staging.json"
            code, out, _ = _run(["environment", "init", str(dest)])
            self.assertEqual(code, EXIT_OK, out)
            self.assertTrue(dest.is_file())

    def test_generated_file_is_deterministic(self) -> None:
        with TemporaryDirectory() as a, TemporaryDirectory() as b:
            pa = Path(a) / "staging.json"
            pb = Path(b) / "staging.json"
            authoring.init_environment_file(pa)
            authoring.init_environment_file(pb)
            self.assertEqual(pa.read_bytes(), pb.read_bytes())
            text = pa.read_text(encoding="utf-8")
            self.assertNotIn("\r", text)
            self.assertTrue(text.endswith("}\n"))
            self.assertIn('\n  "name"', text)  # 2-space indent

    def test_generated_file_passes_environment_check(self) -> None:
        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "staging.json"
            authoring.init_environment_file(dest)
            self.assertEqual(authoring.check_environment_file(dest), [])
            code, out, _ = _run(["environment", "check", str(dest)])
            self.assertEqual(code, EXIT_OK, out)

    def test_generated_file_loads_through_the_authoritative_loader(self) -> None:
        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "staging.json"
            authoring.init_environment_file(dest)
            env = load_environment(dest)  # the runtime loader, unchanged
            self.assertEqual(env.name, "staging")
            self.assertTrue(env.has_target_overrides)

    def test_second_init_to_same_path_fails_exit_2_and_keeps_contents(self) -> None:
        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "staging.json"
            authoring.init_environment_file(dest)
            original = dest.read_bytes()
            code, _, err = _run(["environment", "init", str(dest)])
            self.assertEqual(code, EXIT_ERROR)
            self.assertIn("refusing to overwrite", err)
            self.assertEqual(dest.read_bytes(), original)

    def test_init_helper_raises_scenario_error_on_existing_file(self) -> None:
        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "x.json"
            dest.write_text("keep me", encoding="utf-8")
            with self.assertRaises(ScenarioError):
                authoring.init_environment_file(dest)
            self.assertEqual(dest.read_text(encoding="utf-8"), "keep me")

    def test_init_missing_parent_directory_is_exit_2(self) -> None:
        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "no" / "such" / "dir" / "e.json"
            code, _, err = _run(["environment", "init", str(dest)])
            self.assertEqual(code, EXIT_ERROR)
            self.assertIn("could not write", err)

    def test_url_override_is_applied(self) -> None:
        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "staging.json"
            authoring.init_environment_file(
                dest, url="https://agent.example.com/chat"
            )
            data = json.loads(dest.read_text(encoding="utf-8"))
        self.assertEqual(data["target"]["url"], "https://agent.example.com/chat")

    def test_generated_config_has_no_real_secret_value(self) -> None:
        """The only "secret" material is a reference -- an env-var name plus a
        literal prefix -- never a resolved value."""
        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "staging.json"
            authoring.init_environment_file(dest)
            data = json.loads(dest.read_text(encoding="utf-8"))
        secret = data["target"]["secret_headers"]["Authorization"]
        self.assertEqual(set(secret), {"env", "prefix"})
        self.assertRegex(secret["env"], r"^[A-Za-z_][A-Za-z0-9_]*$")

    def test_generated_file_does_not_depend_on_environment_variables(self) -> None:
        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "staging.json"
            authoring.init_environment_file(dest)
            with mock.patch.dict(os.environ, {}, clear=True):
                self.assertEqual(authoring.check_environment_file(dest), [])


# --------------------------------------------------------------------------- #
# Alpha 2A -- environment authoring: check (security acceptance)
# --------------------------------------------------------------------------- #


class EnvironmentCheckSecurityTests(unittest.TestCase):
    def test_check_does_not_invoke_httpadapter_send(self) -> None:
        from nature_agent_validator.adapters.http import HttpAdapter

        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "staging.json"
            authoring.init_environment_file(dest)
            with mock.patch.object(
                HttpAdapter, "send", side_effect=AssertionError("send called")
            ) as sent:
                self.assertEqual(authoring.check_environment_file(dest), [])
            sent.assert_not_called()

    def test_check_opens_no_socket(self) -> None:
        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "staging.json"
            authoring.init_environment_file(dest)
            with mock.patch.object(
                socket, "socket", side_effect=AssertionError("socket opened")
            ):
                self.assertEqual(authoring.check_environment_file(dest), [])

    def test_check_resolves_no_secret_env_var(self) -> None:
        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "staging.json"
            authoring.init_environment_file(dest)
            data = json.loads(dest.read_text(encoding="utf-8"))
            env_name = data["target"]["secret_headers"]["Authorization"]["env"]
            self.assertNotIn(env_name, os.environ)
            # An unset secret env var is a *runtime* concern; a static check
            # must never resolve it, so the config still checks clean.
            with mock.patch.dict(os.environ, {}, clear=True):
                self.assertEqual(authoring.check_environment_file(dest), [])

    def test_check_does_not_modify_the_environment_file(self) -> None:
        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "staging.json"
            authoring.init_environment_file(dest)
            before = dest.read_bytes()
            listing = sorted(os.listdir(tmp))
            authoring.check_environment_file(dest)
            self.assertEqual(dest.read_bytes(), before)
            self.assertEqual(sorted(os.listdir(tmp)), listing)  # wrote nothing

    def test_valid_environment_returns_zero_diagnostics(self) -> None:
        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "staging.json"
            authoring.init_environment_file(dest)
            self.assertEqual(authoring.check_environment_file(dest), [])

    def test_invalid_environment_returns_diagnostic(self) -> None:
        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "bad.json"
            dest.write_text(json.dumps({"target": {}}), encoding="utf-8")
            diags = authoring.check_environment_file(dest)
            self.assertTrue(diags)
            self.assertIn("name", diags[0])
            code, _, err = _run(["environment", "check", str(dest)])
            self.assertEqual(code, EXIT_ERROR)
            self.assertIn("invalid", err)

    def test_malformed_json_gives_a_diagnostic(self) -> None:
        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "bad.json"
            dest.write_text("{ not json", encoding="utf-8")
            diags = authoring.check_environment_file(dest)
            self.assertEqual(len(diags), 1)
            self.assertIn("invalid JSON", diags[0])

    def test_unknown_field_is_clearly_reported(self) -> None:
        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "bad.json"
            dest.write_text(
                json.dumps({"name": "x", "bogus": 1}), encoding="utf-8"
            )
            diags = authoring.check_environment_file(dest)
            self.assertEqual(len(diags), 1)
            self.assertIn("bogus", diags[0])


# --------------------------------------------------------------------------- #
# Alpha 2A -- environment authoring: describe
# --------------------------------------------------------------------------- #


class EnvironmentDescribeTests(unittest.TestCase):
    def test_describe_succeeds_and_shows_a_concrete_example(self) -> None:
        code, out, _ = _run(["environment", "describe"])
        self.assertEqual(code, EXIT_OK)
        self.assertIn('"secret_headers"', out)
        self.assertIn('"AGENT_TOKEN"', out)

    def test_describe_mentions_every_load_environment_field(self) -> None:
        _, out, _ = _run(["environment", "describe"])
        for field in (
            "name",
            "target.url",
            "target.timeout",
            "target.headers",
            "target.secret_headers",
        ):
            self.assertIn(field, out, field)

    def test_described_fields_are_jointly_accepted_by_the_authoritative_loader(
        self,
    ) -> None:
        """Drift guard: every field name describe_environment() documents is
        one load_environment() actually accepts, proven by round-tripping a
        config that uses all of them -- not by importing configuration's
        private field-set constants."""
        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "all-fields.json"
            dest.write_text(
                json.dumps(
                    {
                        "name": "x",
                        "target": {
                            "url": "http://127.0.0.1:9/x",
                            "timeout": 5,
                            "headers": {"X-Test": "1"},
                            "secret_headers": {
                                "Authorization": {
                                    "env": "X_TOKEN",
                                    "prefix": "Bearer ",
                                }
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(authoring.check_environment_file(dest), [])

    def test_describe_states_static_auth_and_401_403_are_results(self) -> None:
        _, out, _ = _run(["environment", "describe"])
        self.assertIn("Static authentication", out)
        self.assertIn("401", out)
        self.assertIn("403", out)
        self.assertIn("result", out.lower())

    def test_describe_does_not_claim_dynamic_session_auth_support(self) -> None:
        _, out, _ = _run(["environment", "describe"])
        self.assertIn("Not supported", out)
        self.assertIn("session", out.lower())


# --------------------------------------------------------------------------- #
# Alpha 2A -- `nav environment` CLI dispatch
# --------------------------------------------------------------------------- #


class EnvironmentCliDispatchTests(unittest.TestCase):
    def test_environment_requires_a_subcommand(self) -> None:
        with self.assertRaises(SystemExit):
            _run(["environment"])

    def test_full_first_run_flow(self) -> None:
        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "staging.json"
            self.assertEqual(_run(["environment", "init", str(dest)])[0], EXIT_OK)
            self.assertEqual(_run(["environment", "check", str(dest)])[0], EXIT_OK)

    def test_check_missing_file_is_exit_2(self) -> None:
        code, _, err = _run(["environment", "check", "/no/such/environment.json"])
        self.assertEqual(code, EXIT_ERROR)
        self.assertIn("invalid", err)


if __name__ == "__main__":
    unittest.main()
