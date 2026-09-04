"""Phase 5: environment configuration and secret-safe HTTP authentication.

Deterministic and offline. Localhost fixture servers only; secrets are injected
through a patched ``os.environ`` and asserted absent from every output.
"""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
import xml.etree.ElementTree as ET
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest import mock

from nature_agent_validator.assertions import AssertionSpec
from nature_agent_validator.cli.main import EXIT_ERROR, EXIT_FAIL, EXIT_OK, main
from nature_agent_validator.configuration import (
    EnvironmentConfig,
    SecretHeaderRef,
    apply_environment,
    load_environment,
)
from nature_agent_validator.errors import ConfigurationError
from nature_agent_validator.reporting import OverallStatus
from nature_agent_validator.runner import Runner
from nature_agent_validator.scenario import Scenario, ScenarioRequest, ScenarioTarget
from nature_agent_validator.scenario.serialization import scenario_to_dict

from tests.http_fixture import LocalHTTPServer

# An unmistakable value that must never leak into any output. (Section 37.)
SECRET = "NATURE_PHASE5_SECRET_DO_NOT_LEAK_7f92c1e4a1b5"
SECRET_ENV = "NATURE_PHASE5_AGENT_TOKEN"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _write_env(directory: Path, body: dict, name: str = "env.json") -> Path:
    path = directory / name
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


def _http_scenario(
    *,
    url: str = "http://127.0.0.1:9/unused",
    method: str | None = None,
    headers: dict | None = None,
    payload=None,
    evidence_field: str | None = None,
    expectations=(),
    sid: str = "s1",
) -> Scenario:
    config: dict = {"url": url}
    if method is not None:
        config["method"] = method
    if headers is not None:
        config["headers"] = headers
    if evidence_field is not None:
        config["evidence_field"] = evidence_field
    return Scenario(
        scenario_id=sid,
        name=f"{sid} name",
        target=ScenarioTarget("http", config),
        request=ScenarioRequest(payload=payload),
        expectations=tuple(expectations),
    )


def _ok_expectations() -> tuple[AssertionSpec, ...]:
    return (
        AssertionSpec("status", "status_equals", {"value": 200}),
        AssertionSpec("body", "json_path_equals", {"path": "answer", "value": "ok"}),
    )


def _bearer_env_body(url: str) -> dict:
    return {
        "name": "staging",
        "target": {
            "url": url,
            "secret_headers": {"Authorization": {"env": SECRET_ENV, "prefix": "Bearer "}},
        },
    }


# --------------------------------------------------------------------------- #
# load_environment: validation rules  (section 27)
# --------------------------------------------------------------------------- #

class LoadEnvironmentTests(unittest.TestCase):
    def _load(self, body: dict):
        with tempfile.TemporaryDirectory() as tmp:
            return load_environment(_write_env(Path(tmp), body))

    def test_valid_environment_loads(self) -> None:  # req 1
        env = self._load({
            "name": "staging",
            "target": {
                "url": "https://staging.example.com/chat",
                "timeout": 10,
                "headers": {"X-Environment": "staging"},
                "secret_headers": {"Authorization": {"env": "AGENT_TOKEN", "prefix": "Bearer "}},
            },
        })
        self.assertIsInstance(env, EnvironmentConfig)
        self.assertEqual(env.name, "staging")
        self.assertEqual(env.url, "https://staging.example.com/chat")
        self.assertEqual(env.timeout, 10.0)
        self.assertEqual(dict(env.headers), {"X-Environment": "staging"})
        self.assertEqual(env.secret_headers["Authorization"], SecretHeaderRef("AGENT_TOKEN", "Bearer "))

    def test_name_required(self) -> None:  # req 2
        with self.assertRaises(ConfigurationError):
            self._load({"target": {}})

    def test_empty_name_rejected(self) -> None:  # req 3
        with self.assertRaises(ConfigurationError):
            self._load({"name": ""})
        with self.assertRaises(ConfigurationError):
            self._load({"name": "   "})

    def test_unknown_root_field_rejected(self) -> None:  # req 4
        with self.assertRaises(ConfigurationError):
            self._load({"name": "x", "extra": 1})

    def test_unknown_target_field_rejected(self) -> None:  # req 5
        with self.assertRaises(ConfigurationError):
            self._load({"name": "x", "target": {"base_url": "http://x"}})

    def test_invalid_json_rejected(self) -> None:  # req 6
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bad.json"
            p.write_text("{ not json", encoding="utf-8")
            with self.assertRaises(ConfigurationError):
                load_environment(p)

    def test_missing_file_rejected(self) -> None:  # req 7
        with self.assertRaises(ConfigurationError):
            load_environment("/no/such/environment/file.json")

    def test_non_file_path_rejected(self) -> None:  # req 7
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ConfigurationError):
                load_environment(tmp)  # a directory

    def test_invalid_root_type_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "a.json"
            p.write_text("[1, 2, 3]", encoding="utf-8")
            with self.assertRaises(ConfigurationError):
                load_environment(p)

    def test_invalid_url_type_rejected(self) -> None:  # req 8
        with self.assertRaises(ConfigurationError):
            self._load({"name": "x", "target": {"url": 123}})

    def test_invalid_timeout_rejected(self) -> None:  # req 9
        with self.assertRaises(ConfigurationError):
            self._load({"name": "x", "target": {"timeout": "soon"}})
        with self.assertRaises(ConfigurationError):
            self._load({"name": "x", "target": {"timeout": [1]}})

    def test_timeout_numeric_accepted(self) -> None:  # req 9
        self.assertEqual(self._load({"name": "x", "target": {"timeout": 7}}).timeout, 7.0)
        self.assertEqual(self._load({"name": "x", "target": {"timeout": 2.5}}).timeout, 2.5)

    def test_normal_headers_load(self) -> None:  # req 10
        env = self._load({"name": "x", "target": {"headers": {"A": "1", "B": "2"}}})
        self.assertEqual(dict(env.headers), {"A": "1", "B": "2"})

    def test_invalid_headers_rejected(self) -> None:
        with self.assertRaises(ConfigurationError):
            self._load({"name": "x", "target": {"headers": ["A", "B"]}})
        with self.assertRaises(ConfigurationError):
            self._load({"name": "x", "target": {"headers": {"A": 1}}})
        with self.assertRaises(ConfigurationError):
            self._load({"name": "x", "target": {"headers": {"": "v"}}})

    def test_secret_headers_load(self) -> None:  # req 11
        env = self._load({
            "name": "x",
            "target": {"secret_headers": {"X-API-Key": {"env": "AGENT_API_KEY"}}},
        })
        self.assertEqual(env.secret_headers["X-API-Key"], SecretHeaderRef("AGENT_API_KEY", ""))

    def test_secret_header_env_required(self) -> None:  # req 12
        with self.assertRaises(ConfigurationError):
            self._load({"name": "x", "target": {"secret_headers": {"Authorization": {"prefix": "Bearer "}}}})

    def test_invalid_env_variable_name_rejected(self) -> None:  # req 13
        for bad in ("1BAD", "has-dash", "has.dot", "${VAR}", "has space", ""):
            with self.assertRaises(ConfigurationError):
                self._load({"name": "x", "target": {"secret_headers": {"H": {"env": bad}}}})

    def test_valid_env_variable_names_accepted(self) -> None:  # req 13
        for good in ("AGENT_TOKEN", "STAGING_API_KEY", "NATURE_SECRET_1", "_x", "a"):
            env = self._load({"name": "x", "target": {"secret_headers": {"H": {"env": good}}}})
            self.assertEqual(env.secret_headers["H"].env, good)

    def test_unknown_secret_ref_field_rejected(self) -> None:  # req 14
        with self.assertRaises(ConfigurationError):
            self._load({"name": "x", "target": {"secret_headers": {"H": {"env": "V", "suffix": "!"}}}})

    def test_prefix_defaults_to_empty(self) -> None:  # req 15
        env = self._load({"name": "x", "target": {"secret_headers": {"H": {"env": "V"}}}})
        self.assertEqual(env.secret_headers["H"].prefix, "")

    def test_prefix_bearer_works(self) -> None:  # req 16
        env = self._load({"name": "x", "target": {"secret_headers": {"H": {"env": "V", "prefix": "Bearer "}}}})
        self.assertEqual(env.secret_headers["H"].prefix, "Bearer ")

    def test_secret_header_case_insensitive_duplicate_rejected(self) -> None:  # req 26
        with self.assertRaises(ConfigurationError):
            self._load({
                "name": "x",
                "target": {"secret_headers": {
                    "Authorization": {"env": "A"}, "authorization": {"env": "B"},
                }},
            })

    def test_invalid_prefix_type_rejected(self) -> None:
        with self.assertRaises(ConfigurationError):
            self._load({"name": "x", "target": {"secret_headers": {"H": {"env": "V", "prefix": 7}}}})


# --------------------------------------------------------------------------- #
# apply_environment: override rules, immutability, HTTP-only  (sections 6-14, 21-22)
# --------------------------------------------------------------------------- #

class ApplyEnvironmentTests(unittest.TestCase):
    def test_url_override_exact(self) -> None:  # req 27
        scn = _http_scenario(url="http://old/chat")
        env = EnvironmentConfig(name="e", url="https://new.example.com/chat")
        eff = apply_environment(scn, env)
        self.assertEqual(eff.target.config["url"], "https://new.example.com/chat")

    def test_timeout_override(self) -> None:  # req 28
        eff = apply_environment(_http_scenario(), EnvironmentConfig(name="e", url="http://x/y", timeout=15.0))
        self.assertEqual(eff.target.config["timeout_seconds"], 15.0)

    def test_scenario_normal_headers_preserved(self) -> None:  # req 21
        scn = _http_scenario(headers={"X-Keep": "yes"})
        eff = apply_environment(scn, EnvironmentConfig(name="e", headers={"X-Add": "1"}))
        self.assertEqual(eff.target.config["headers"], {"X-Keep": "yes", "X-Add": "1"})

    def test_environment_headers_added(self) -> None:  # req 22
        eff = apply_environment(_http_scenario(), EnvironmentConfig(name="e", headers={"X-Env": "v"}))
        self.assertEqual(eff.target.config["headers"], {"X-Env": "v"})

    def test_environment_header_overrides_case_insensitively(self) -> None:  # req 23
        scn = _http_scenario(headers={"X-Tenant": "local"})
        eff = apply_environment(scn, EnvironmentConfig(name="e", headers={"x-tenant": "staging"}))
        headers = eff.target.config["headers"]
        self.assertNotIn("X-Tenant", headers)             # no duplicate semantic header
        self.assertEqual(headers, {"x-tenant": "staging"})

    def test_normal_vs_secret_conflict_rejected(self) -> None:  # req 24
        scn = _http_scenario(headers={"Authorization": "literal"})
        env = EnvironmentConfig(name="e", secret_headers={"Authorization": SecretHeaderRef("V")})
        with self.assertRaises(ConfigurationError):
            apply_environment(scn, env)

    def test_case_variant_normal_vs_secret_conflict_rejected(self) -> None:  # req 25
        scn = _http_scenario(headers={"authorization": "literal"})
        env = EnvironmentConfig(name="e", secret_headers={"Authorization": SecretHeaderRef("V")})
        with self.assertRaises(ConfigurationError):
            apply_environment(scn, env)
        # and the reverse: env normal header that collides with env secret header
        env2 = EnvironmentConfig(
            name="e", headers={"Authorization": "x"},
            secret_headers={"authorization": SecretHeaderRef("V")},
        )
        with self.assertRaises(ConfigurationError):
            apply_environment(_http_scenario(), env2)

    def test_does_not_change_method(self) -> None:  # req 29
        eff = apply_environment(_http_scenario(method="PUT"), EnvironmentConfig(name="e", url="http://x/y"))
        self.assertEqual(eff.target.config["method"], "PUT")

    def test_does_not_change_payload(self) -> None:  # req 30
        scn = _http_scenario(payload={"customer_id": "C-1"})
        eff = apply_environment(scn, EnvironmentConfig(name="e", url="http://x/y"))
        self.assertEqual(eff.request.payload, {"customer_id": "C-1"})

    def test_does_not_change_expectations(self) -> None:  # req 31
        scn = _http_scenario(expectations=_ok_expectations())
        eff = apply_environment(scn, EnvironmentConfig(name="e", url="http://x/y"))
        self.assertEqual(eff.expectations, scn.expectations)

    def test_does_not_change_evidence_field(self) -> None:  # req 32
        scn = _http_scenario(evidence_field="evidence")
        eff = apply_environment(scn, EnvironmentConfig(name="e", url="http://x/y"))
        self.assertEqual(eff.target.config["evidence_field"], "evidence")

    def test_original_scenario_not_mutated(self) -> None:  # req 33
        scn = _http_scenario(url="http://original/chat", headers={"X-Tenant": "local"})
        original_config = dict(scn.target.config)
        env = EnvironmentConfig(
            name="e", url="http://new/chat", timeout=9.0,
            headers={"x-tenant": "staging"},
            secret_headers={"Authorization": SecretHeaderRef("V", "Bearer ")},
        )
        eff = apply_environment(scn, env)
        self.assertIsNot(eff, scn)
        self.assertEqual(dict(scn.target.config), original_config)  # unchanged
        self.assertEqual(scn.target.config["url"], "http://original/chat")
        self.assertNotIn("secret_headers", scn.target.config)
        self.assertNotIn("timeout_seconds", scn.target.config)

    def test_name_only_environment_is_noop(self) -> None:  # req 37 (partial)
        scn = _http_scenario(url="http://x/y")
        eff = apply_environment(scn, EnvironmentConfig(name="just-a-name"))
        self.assertIs(eff, scn)

    def test_overrides_on_non_http_target_error(self) -> None:  # req 38
        static_scn = Scenario(
            scenario_id="s", name="s",
            target=ScenarioTarget("static", {"status": 200}),
            request=ScenarioRequest(), expectations=(),
        )
        with self.assertRaises(ConfigurationError):
            apply_environment(static_scn, EnvironmentConfig(name="e", url="http://x/y"))

    def test_name_only_environment_on_non_http_is_noop(self) -> None:  # req 38 boundary
        static_scn = Scenario(
            scenario_id="s", name="s",
            target=ScenarioTarget("static", {"status": 200}),
            request=ScenarioRequest(), expectations=(),
        )
        self.assertIs(apply_environment(static_scn, EnvironmentConfig(name="e")), static_scn)

    def test_same_scenario_two_environments_two_urls(self) -> None:  # req 36
        scn = _http_scenario(url="http://default/chat")
        a = apply_environment(scn, EnvironmentConfig(name="a", url="https://a.example.com/chat"))
        b = apply_environment(scn, EnvironmentConfig(name="b", url="https://b.example.com/chat"))
        self.assertEqual(a.target.config["url"], "https://a.example.com/chat")
        self.assertEqual(b.target.config["url"], "https://b.example.com/chat")
        self.assertEqual(scn.target.config["url"], "http://default/chat")  # source untouched


# --------------------------------------------------------------------------- #
# secret resolution through a real localhost request  (sections 12, 29)
# --------------------------------------------------------------------------- #

class SecretResolutionTests(unittest.TestCase):
    def _run(self, env_body: dict, *, scenario_headers=None):
        with LocalHTTPServer() as srv, tempfile.TemporaryDirectory() as tmp:
            body = json.loads(json.dumps(env_body))  # deep copy
            if "url" in body.get("target", {}) and body["target"]["url"] == "<capture>":
                body["target"]["url"] = srv.url("/capture")
            env = load_environment(_write_env(Path(tmp), body))
            scn = _http_scenario(
                url="http://127.0.0.1:9/unused",
                headers=scenario_headers,
                expectations=_ok_expectations(),
            )
            eff = apply_environment(scn, env)
            result = Runner().run(eff)
            return result, dict(srv.last_request_headers)

    def test_bearer_secret_injected_into_authorization_header(self) -> None:  # req 19
        with mock.patch.dict(os.environ, {SECRET_ENV: SECRET}, clear=False):
            result, sent = self._run({
                "name": "staging",
                "target": {
                    "url": "<capture>",
                    "secret_headers": {"Authorization": {"env": SECRET_ENV, "prefix": "Bearer "}},
                },
            })
        self.assertIs(result.overall_status, OverallStatus.PASS, result.errors)
        self.assertEqual(sent.get("authorization"), f"Bearer {SECRET}")

    def test_api_key_style_empty_prefix(self) -> None:  # req 20
        with mock.patch.dict(os.environ, {SECRET_ENV: SECRET}, clear=False):
            result, sent = self._run({
                "name": "staging",
                "target": {
                    "url": "<capture>",
                    "secret_headers": {"X-API-Key": {"env": SECRET_ENV}},
                },
            })
        self.assertIs(result.overall_status, OverallStatus.PASS, result.errors)
        self.assertEqual(sent.get("x-api-key"), SECRET)  # exact value, no prefix

    def test_unset_secret_is_error(self) -> None:  # req 17
        os.environ.pop(SECRET_ENV, None)
        result, _ = self._run({
            "name": "s",
            "target": {"url": "<capture>", "secret_headers": {"Authorization": {"env": SECRET_ENV}}},
        })
        self.assertIs(result.overall_status, OverallStatus.ERROR)
        self.assertTrue(any(SECRET_ENV in e for e in result.errors))

    def test_empty_secret_is_error(self) -> None:  # req 18
        with mock.patch.dict(os.environ, {SECRET_ENV: ""}, clear=False):
            result, _ = self._run({
                "name": "s",
                "target": {"url": "<capture>", "secret_headers": {"Authorization": {"env": SECRET_ENV}}},
            })
        self.assertIs(result.overall_status, OverallStatus.ERROR)
        self.assertTrue(any(SECRET_ENV in e and "empty" in e for e in result.errors))

    def test_scenario_and_env_normal_headers_reach_server(self) -> None:  # req 21/22 e2e
        with mock.patch.dict(os.environ, {SECRET_ENV: SECRET}, clear=False):
            _, sent = self._run(
                {
                    "name": "s",
                    "target": {
                        "url": "<capture>",
                        "headers": {"x-tenant": "staging"},
                        "secret_headers": {"Authorization": {"env": SECRET_ENV, "prefix": "Bearer "}},
                    },
                },
                scenario_headers={"X-Tenant": "local", "X-Scenario": "kept"},
            )
        self.assertEqual(sent.get("x-tenant"), "staging")     # env wins
        self.assertEqual(sent.get("x-scenario"), "kept")      # scenario header survives


# --------------------------------------------------------------------------- #
# CLI integration  (sections 24-25)
# --------------------------------------------------------------------------- #

class EnvironmentCliTests(unittest.TestCase):
    def _suite_dir(self, tmp: str, scenarios: dict[str, Scenario]) -> str:
        # a dedicated sub-directory so the environment JSON file (written at
        # ``tmp`` root) is never discovered as a suite scenario
        d = Path(tmp) / "suite"
        d.mkdir(exist_ok=True)
        for fn, sc in scenarios.items():
            (d / fn).write_text(json.dumps(scenario_to_dict(sc)), encoding="utf-8")
        return str(d)

    def test_no_environment_preserves_behavior(self) -> None:  # req 37
        with LocalHTTPServer() as srv, tempfile.TemporaryDirectory() as tmp:
            scn = _http_scenario(url=srv.url("/capture"), expectations=_ok_expectations())
            path = self._suite_dir(tmp, {"a.json": scn})
            out = io.StringIO()
            with redirect_stdout(out):
                code = main(["validate-suite", path])
            self.assertEqual(code, EXIT_OK, out.getvalue())
            self.assertIn("[PASS] suite", out.getvalue())

    def test_validate_and_validate_suite_share_environment_path(self) -> None:  # req 34, 35
        real_load, real_apply = load_environment, apply_environment
        with LocalHTTPServer() as srv, tempfile.TemporaryDirectory() as tmp, \
                mock.patch("nature_agent_validator.cli.main.configuration.load_environment",
                           side_effect=real_load) as spy_load, \
                mock.patch("nature_agent_validator.cli.main.configuration.apply_environment",
                           side_effect=real_apply) as spy_apply, \
                mock.patch.dict(os.environ, {SECRET_ENV: SECRET}, clear=False):
            env_file = _write_env(Path(tmp), _bearer_env_body(srv.url("/capture")))
            scn = _http_scenario(url="http://127.0.0.1:9/x", expectations=_ok_expectations())
            scn_path = Path(tmp) / "s.json"
            scn_path.write_text(json.dumps(scenario_to_dict(scn)), encoding="utf-8")
            suite_dir = Path(tmp) / "suite"
            suite_dir.mkdir()
            (suite_dir / "s.json").write_text(json.dumps(scenario_to_dict(scn)), encoding="utf-8")

            with redirect_stdout(io.StringIO()):
                c1 = main(["validate", str(scn_path), "--environment", str(env_file)])
                c2 = main(["validate-suite", str(suite_dir), "--environment", str(env_file)])
        self.assertEqual((c1, c2), (EXIT_OK, EXIT_OK))
        self.assertEqual(spy_load.call_count, 2)      # both commands loaded the env
        self.assertEqual(spy_apply.call_count, 2)     # both commands applied it (1 scenario each)

    def test_environment_error_goes_to_stderr_exit_2(self) -> None:  # req 25
        with tempfile.TemporaryDirectory() as tmp:
            scn = _http_scenario(url="http://127.0.0.1:9/x")
            path = self._suite_dir(tmp, {"a.json": scn})
            bad_env = _write_env(Path(tmp), {"name": "x", "target": {"nope": 1}}, name="bad.json")
            err = io.StringIO()
            with redirect_stderr(err), redirect_stdout(io.StringIO()):
                code = main(["validate-suite", path, "--environment", str(bad_env)])
            self.assertEqual(code, EXIT_ERROR)
            self.assertIn("error:", err.getvalue())

    def test_environment_with_json_mode(self) -> None:  # req 39
        with LocalHTTPServer() as srv, tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {SECRET_ENV: SECRET}, clear=False):
            scn = _http_scenario(url="http://127.0.0.1:9/x", expectations=_ok_expectations())
            path = self._suite_dir(tmp, {"a.json": scn})
            env_file = _write_env(Path(tmp), _bearer_env_body(srv.url("/capture")), name="e.json")
            out = io.StringIO()
            with redirect_stdout(out):
                code = main(["validate-suite", path, "--environment", str(env_file), "--json"])
            self.assertEqual(code, EXIT_OK)
            payload = json.loads(out.getvalue())
            self.assertEqual(payload["overall_status"], "PASS")
            self.assertNotIn(SECRET, out.getvalue())

    def test_environment_with_junit_stdout(self) -> None:  # req 40
        with LocalHTTPServer() as srv, tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {SECRET_ENV: SECRET}, clear=False):
            scn = _http_scenario(url="http://127.0.0.1:9/x", expectations=_ok_expectations())
            path = self._suite_dir(tmp, {"a.json": scn})
            env_file = _write_env(Path(tmp), _bearer_env_body(srv.url("/capture")), name="e.json")
            out = io.StringIO()
            with redirect_stdout(out):
                code = main(["validate-suite", path, "--environment", str(env_file), "--junit"])
            self.assertEqual(code, EXIT_OK)
            ET.fromstring(out.getvalue())  # valid XML
            self.assertNotIn(SECRET, out.getvalue())

    def test_environment_with_junit_output_file(self) -> None:  # req 41
        with LocalHTTPServer() as srv, tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {SECRET_ENV: SECRET}, clear=False):
            scn = _http_scenario(url="http://127.0.0.1:9/x", expectations=_ok_expectations())
            path = self._suite_dir(tmp, {"a.json": scn})
            env_file = _write_env(Path(tmp), _bearer_env_body(srv.url("/capture")), name="e.json")
            report = Path(tmp) / "r.xml"
            out = io.StringIO()
            with redirect_stdout(out):
                code = main(["validate-suite", path, "--environment", str(env_file),
                             "--junit-output", str(report)])
            self.assertEqual(code, EXIT_OK)
            raw = report.read_bytes()
            ET.fromstring(raw)
            self.assertNotIn(SECRET, raw.decode("utf-8"))
            self.assertNotIn(SECRET, out.getvalue())


# --------------------------------------------------------------------------- #
# secret leakage scans  (sections 16-18, 37)
# --------------------------------------------------------------------------- #

class SecretLeakageTests(unittest.TestCase):
    def _run_all_outputs(self):
        """Run one scenario+environment through every CLI mode and the object
        model, returning every string that could conceivably carry the secret."""
        strings: dict[str, str] = {}
        with LocalHTTPServer() as srv, tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {SECRET_ENV: SECRET}, clear=False):
            env_body = {
                "name": "staging",
                "target": {
                    "url": srv.url("/capture"),
                    "timeout": 10,
                    "headers": {"X-Environment": "staging"},
                    "secret_headers": {"Authorization": {"env": SECRET_ENV, "prefix": "Bearer "}},
                },
            }
            env_file = _write_env(Path(tmp), env_body)
            env = load_environment(env_file)
            strings["repr(EnvironmentConfig)"] = repr(env)
            strings["repr(SecretHeaderRef)"] = repr(env.secret_headers["Authorization"])

            scn = _http_scenario(url="http://127.0.0.1:9/x", expectations=_ok_expectations())
            suite_dir = Path(tmp) / "suite"
            suite_dir.mkdir()
            (suite_dir / "s.json").write_text(json.dumps(scenario_to_dict(scn)), encoding="utf-8")

            # object model
            eff = apply_environment(scn, env)
            strings["repr(effective scenario)"] = repr(eff)
            strings["effective target to_dict"] = str(eff.target.to_dict())
            result = Runner().run(eff)
            strings["repr(ValidationResult)"] = repr(result)
            strings["str(ValidationResult.to_dict)"] = str(result.to_dict())
            strings["json(ValidationResult.to_dict)"] = json.dumps(result.to_dict(), default=str)

            # every CLI mode
            for mode in (["--json"], ["--junit"], []):
                buf, ebuf = io.StringIO(), io.StringIO()
                with redirect_stdout(buf), redirect_stderr(ebuf):
                    main(["validate-suite", str(suite_dir), "--environment", str(env_file), *mode])
                strings[f"cli stdout {mode or ['human']}"] = buf.getvalue()
                strings[f"cli stderr {mode or ['human']}"] = ebuf.getvalue()

            report = Path(tmp) / "out.xml"
            with redirect_stdout(io.StringIO()):
                main(["validate-suite", str(suite_dir), "--environment", str(env_file),
                      "--junit-output", str(report)])
            strings["junit file"] = report.read_text(encoding="utf-8")

            # an error path: point at a dead port so the adapter raises
            dead_scn = _http_scenario(url="http://127.0.0.1:9/x")
            dead_dir = Path(tmp) / "dead"
            dead_dir.mkdir()
            (dead_dir / "s.json").write_text(json.dumps(scenario_to_dict(dead_scn)), encoding="utf-8")
            dead_env = _write_env(
                Path(tmp),
                {"name": "d", "target": {"url": "http://127.0.0.1:9/refused",
                                         "secret_headers": {"Authorization": {"env": SECRET_ENV, "prefix": "Bearer "}}}},
                name="dead_env.json",
            )
            ebuf = io.StringIO()
            with redirect_stdout(io.StringIO()), redirect_stderr(ebuf):
                main(["validate-suite", str(dead_dir), "--environment", str(dead_env)])
            errres = Runner().run(apply_environment(dead_scn, load_environment(dead_env)))
            strings["error path result errors"] = str(errres.errors)
            strings["error path to_dict"] = json.dumps(errres.to_dict(), default=str)
        return strings

    def test_secret_value_never_appears_in_any_output(self) -> None:  # req 42-48, 50, 51
        for label, text in self._run_all_outputs().items():
            self.assertNotIn(SECRET, text, f"secret leaked in: {label}")

    def test_env_var_name_allowed_in_missing_secret_error(self) -> None:  # req 49
        with LocalHTTPServer() as srv, tempfile.TemporaryDirectory() as tmp:
            os.environ.pop(SECRET_ENV, None)
            env_file = _write_env(Path(tmp), {
                "name": "s",
                "target": {"url": srv.url("/capture"),
                           "secret_headers": {"Authorization": {"env": SECRET_ENV}}},
            })
            scn = _http_scenario(url="http://127.0.0.1:9/x")
            eff = apply_environment(scn, load_environment(env_file))
            result = Runner().run(eff)
        self.assertIs(result.overall_status, OverallStatus.ERROR)
        joined = " ".join(result.errors)
        self.assertIn(SECRET_ENV, joined)   # the NAME may appear
        self.assertNotIn(SECRET, joined)    # the VALUE must not

    def test_environmentconfig_repr_has_reference_not_value(self) -> None:  # req 51
        with mock.patch.dict(os.environ, {SECRET_ENV: SECRET}, clear=False), \
                tempfile.TemporaryDirectory() as tmp:
            env = load_environment(_write_env(Path(tmp), {
                "name": "s",
                "target": {"secret_headers": {"Authorization": {"env": SECRET_ENV, "prefix": "Bearer "}}},
            }))
        text = repr(env)
        self.assertIn(SECRET_ENV, text)     # the reference (env var name) is visible
        self.assertNotIn(SECRET, text)      # the resolved value is not


# --------------------------------------------------------------------------- #
# Phase 5 remediation: secret-reflection guard  (blocker fix)
# --------------------------------------------------------------------------- #

class SecretReflectionTests(unittest.TestCase):
    """A target that reflects an injected secret back in its response must make
    the run ERROR at the adapter boundary, before the contaminated response can
    enter a NormalizedResult / ValidationResult / report."""

    def _bearer_env(self, tmp: Path, url: str) -> Path:
        return _write_env(tmp, {
            "name": "reflect",
            "target": {
                "url": url,
                "secret_headers": {"Authorization": {"env": SECRET_ENV, "prefix": "Bearer "}},
            },
        })

    def _scenario_file(self, directory: Path) -> None:
        scn = _http_scenario(url="http://127.0.0.1:9/x", expectations=_ok_expectations())
        (directory / "s.json").write_text(json.dumps(scenario_to_dict(scn)), encoding="utf-8")

    def _run_all_outputs(self, route: str) -> dict[str, str]:
        """Run one reflected-secret scenario through the object model and every
        CLI output mode; return every string that could carry the secret."""
        strings: dict[str, str] = {}
        with LocalHTTPServer() as srv, tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {SECRET_ENV: SECRET}, clear=False):
            root = Path(tmp)
            suite_dir = root / "suite"
            suite_dir.mkdir()
            self._scenario_file(suite_dir)
            env_file = self._bearer_env(root, srv.url(route))

            # object model
            env = load_environment(env_file)
            scn = _http_scenario(url="http://127.0.0.1:9/x", expectations=_ok_expectations())
            eff = apply_environment(scn, env)
            result = Runner().run(eff)
            self.assertIs(
                result.overall_status, OverallStatus.ERROR, f"{route}: not ERROR"
            )
            self.assertTrue(
                any("resolved secret value" in e for e in result.errors),
                f"{route}: fixed diagnostic missing: {result.errors}",
            )
            strings["repr(ValidationResult)"] = repr(result)
            strings["ValidationResult.to_dict"] = str(result.to_dict())
            strings["json(ValidationResult.to_dict)"] = json.dumps(result.to_dict(), default=str)
            strings["result.errors"] = str(result.errors)

            # CLI: human, --json, --junit, --junit-output; stdout + stderr
            report = root / "out.xml"
            for mode in ([], ["--json"], ["--junit"], ["--junit-output", str(report)]):
                out, err = io.StringIO(), io.StringIO()
                with redirect_stdout(out), redirect_stderr(err):
                    code = main(["validate-suite", str(suite_dir),
                                 "--environment", str(env_file), *mode])
                self.assertEqual(code, EXIT_ERROR, f"{route} {mode}: exit {code}")
                strings[f"cli stdout {mode or ['human']}"] = out.getvalue()
                strings[f"cli stderr {mode or ['human']}"] = err.getvalue()
            strings["junit file"] = report.read_text(encoding="utf-8")
        return strings

    def test_reflected_bearer_in_body_is_error_and_no_leak(self) -> None:  # req A, B
        for label, text in self._run_all_outputs("/reflect-body").items():
            self.assertNotIn(SECRET, text, f"secret leaked in: {label}")

    def test_reflected_secret_in_response_header_is_error_and_no_leak(self) -> None:
        for label, text in self._run_all_outputs("/reflect-header").items():
            self.assertNotIn(SECRET, text, f"secret leaked in: {label}")

    def test_reflected_secret_on_http_error_response_is_error_and_no_leak(self) -> None:  # req D
        for label, text in self._run_all_outputs("/reflect-error").items():
            self.assertNotIn(SECRET, text, f"secret leaked in: {label}")

    def test_parsed_json_reflection_detected_independently_of_text(self) -> None:  # req C
        # secret present in the JSON body -> parsed value AND text both carry it;
        # the guard rejects before NormalizedResult.body is populated.
        with LocalHTTPServer() as srv, tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {SECRET_ENV: SECRET}, clear=False):
            env = load_environment(self._bearer_env(Path(tmp), srv.url("/reflect-body")))
            scn = _http_scenario(
                url="http://127.0.0.1:9/x",
                expectations=(AssertionSpec("j", "json_path_equals",
                                            {"path": "seen_authorization", "value": "x"}),),
            )
            result = Runner().run(apply_environment(scn, env))
        self.assertIs(result.overall_status, OverallStatus.ERROR)
        self.assertEqual(result.assertion_results, ())  # never evaluated against contaminated body
        self.assertNotIn(SECRET, json.dumps(result.to_dict(), default=str))

    def test_non_reflecting_target_still_passes(self) -> None:  # req E (no regression)
        with LocalHTTPServer() as srv, tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {SECRET_ENV: SECRET}, clear=False):
            env = load_environment(self._bearer_env(Path(tmp), srv.url("/capture")))
            scn = _http_scenario(url="http://127.0.0.1:9/x", expectations=_ok_expectations())
            result = Runner().run(apply_environment(scn, env))
        self.assertIs(result.overall_status, OverallStatus.PASS, result.errors)

    def test_diagnostic_is_fixed_and_carries_nothing_sensitive(self) -> None:  # req 5
        with LocalHTTPServer() as srv, tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {SECRET_ENV: SECRET}, clear=False):
            env = load_environment(self._bearer_env(Path(tmp), srv.url("/reflect-body")))
            scn = _http_scenario(url="http://127.0.0.1:9/x", expectations=_ok_expectations())
            result = Runner().run(apply_environment(scn, env))
        joined = " ".join(result.errors)
        self.assertIn("target response contained a resolved secret value", joined)
        self.assertNotIn(SECRET, joined)
        self.assertNotIn("Bearer", joined)         # no request header material
        self.assertNotIn("Authorization", joined)  # no header name
        self.assertNotIn("seen_authorization", joined)  # no response body echoed


if __name__ == "__main__":
    unittest.main()
