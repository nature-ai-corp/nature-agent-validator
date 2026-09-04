"""Acceptance C & D: the package imports and exposes the core domain objects."""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout

#: The single authoritative Alpha version. ``pyproject.toml`` sources the
#: distribution version from ``nature_agent_validator.__version__`` via
#: setuptools' dynamic ``attr`` mechanism, so this constant is the only place a
#: release version is edited.
EXPECTED_VERSION = "0.1.0a1"


class PackageImportTests(unittest.TestCase):
    def test_top_level_import_and_version(self) -> None:
        import nature_agent_validator as nav

        self.assertIsInstance(nav.__version__, str)
        self.assertRegex(nav.__version__, r"^\d+\.\d+\.\d+")

    def test_version_is_the_frozen_alpha_value(self) -> None:
        import nature_agent_validator as nav

        self.assertEqual(nav.__version__, EXPECTED_VERSION)

    def test_cli_version_flag_reports_the_same_version(self) -> None:
        from nature_agent_validator.cli.main import main

        buf = io.StringIO()
        with self.assertRaises(SystemExit) as ctx, redirect_stdout(buf):
            main(["--version"])
        self.assertEqual(ctx.exception.code, 0)
        self.assertEqual(buf.getvalue().strip(), f"nav {EXPECTED_VERSION}")

    def test_distribution_metadata_matches_when_installed(self) -> None:
        """When the package is installed, its distribution metadata version
        must equal ``__version__``. Skipped when running from a source tree
        that has not been installed (the dynamic attr sourcing is verified by
        the build check instead)."""
        from importlib import metadata

        import nature_agent_validator as nav

        try:
            dist_version = metadata.version("nature-agent-validator")
        except metadata.PackageNotFoundError:
            self.skipTest("package not installed; nothing to reconcile")
        self.assertEqual(dist_version, nav.__version__)

    def test_core_domain_objects_are_exported(self) -> None:
        import nature_agent_validator as nav

        for name in (
            "Scenario",
            "ScenarioRequest",
            "ScenarioTarget",
            "AssertionSpec",
            "AssertionResult",
            "AssertionContext",
            "TargetAdapter",
            "AdapterResponse",
            "NormalizedResult",
            "EvidenceEvent",
            "EvidenceRecord",
            "EvaluatorProvider",
            "ValidationResult",
            "OverallStatus",
            "Runner",
        ):
            self.assertTrue(hasattr(nav, name), f"missing export: {name}")

    def test_submodules_import(self) -> None:
        for mod in (
            "nature_agent_validator.scenario",
            "nature_agent_validator.runner",
            "nature_agent_validator.assertions",
            "nature_agent_validator.evidence",
            "nature_agent_validator.adapters",
            "nature_agent_validator.evaluators",
            "nature_agent_validator.reporting",
            "nature_agent_validator.cli",
        ):
            __import__(mod)

    def test_no_llm_or_network_modules_imported(self) -> None:
        """Acceptance F & G: importing the core pulls in no HTTP client or LLM SDK.

        Runs in a fresh interpreter so unrelated test-runner imports don't
        pollute the check.
        """
        import subprocess
        import sys
        from pathlib import Path

        src = str(Path(__file__).resolve().parent.parent / "src")
        code = (
            "import sys;"
            "import nature_agent_validator, nature_agent_validator.runner,"
            " nature_agent_validator.cli;"
            "forbidden = {'http', 'http.client', 'urllib.request', 'socket', 'ssl',"
            " 'openai', 'anthropic', 'httpx', 'requests', 'aiohttp'};"
            "leaked = sorted(forbidden & set(sys.modules));"
            "print(leaked);"
            "sys.exit(1 if leaked else 0)"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env={"PYTHONPATH": src, "PATH": ""},
        )
        self.assertEqual(
            proc.returncode, 0, f"forbidden modules imported: {proc.stdout.strip()}"
        )


if __name__ == "__main__":
    unittest.main()
