"""Acceptance C & D: the package imports and exposes the core domain objects."""

from __future__ import annotations

import unittest


class PackageImportTests(unittest.TestCase):
    def test_top_level_import_and_version(self) -> None:
        import nature_agent_validator as nav

        self.assertIsInstance(nav.__version__, str)
        self.assertRegex(nav.__version__, r"^\d+\.\d+\.\d+")

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
