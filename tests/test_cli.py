"""CLI: `nav validate` against the shipped examples."""

from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout, redirect_stderr

from nature_agent_validator.cli.main import EXIT_ERROR, EXIT_OK, main

from tests import EXAMPLES_DIR


class CliTests(unittest.TestCase):
    def test_validate_example_directory_passes(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["validate", str(EXAMPLES_DIR)])
        self.assertEqual(code, EXIT_OK, buf.getvalue())
        self.assertIn("[PASS]", buf.getvalue())

    def test_validate_json_output_is_valid_json(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(
                [
                    "validate",
                    str(EXAMPLES_DIR / "sales_cannot_read_payroll.json"),
                    "--json",
                ]
            )
        self.assertEqual(code, EXIT_OK)
        payload = json.loads(buf.getvalue())
        self.assertIn("results", payload)
        self.assertEqual(payload["results"][0]["overall_status"], "PASS")

    def test_blackbox_example_skips_evidence_but_passes(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(
                [
                    "validate",
                    str(EXAMPLES_DIR / "sales_cannot_read_payroll_blackbox.json"),
                    "--json",
                ]
            )
        self.assertEqual(code, EXIT_OK)
        result = json.loads(buf.getvalue())["results"][0]
        outcomes = [a["outcome"] for a in result["assertion_results"]]
        self.assertIn("SKIPPED", outcomes)
        self.assertEqual(result["overall_status"], "PASS")

    def test_missing_path_is_error_exit(self) -> None:
        err = io.StringIO()
        with redirect_stderr(err):
            code = main(["validate", str(EXAMPLES_DIR / "does_not_exist.json")])
        self.assertEqual(code, EXIT_ERROR)


if __name__ == "__main__":
    unittest.main()
