"""End-to-end: ``nav validate`` runs an HTTP scenario against a real localhost
endpoint, in both human and ``--json`` output modes.
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from nature_agent_validator.cli.main import EXIT_ERROR, EXIT_OK, main

from tests.http_fixture import LocalHTTPServer, unused_localhost_port


def _write_scenario(directory: Path, body: dict) -> Path:
    path = directory / "http_scenario.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


def _scenario_body(url: str) -> dict:
    return {
        "scenario_id": "http-cli-demo",
        "name": "generic HTTP target via CLI",
        "target": {
            "adapter": "http",
            "config": {"url": url, "method": "POST", "timeout_seconds": 5},
        },
        "request": {"payload": {"message": "What is John Smith's salary?"}},
        "expectations": [
            {"assertion_id": "status", "type": "status_equals", "config": {"value": 200}},
            {
                "assertion_id": "echoed",
                "type": "json_path_equals",
                "config": {
                    "path": "received.message",
                    "value": "What is John Smith's salary?",
                },
            },
            {
                "assertion_id": "no-currency",
                "type": "not_contains",
                "config": {"value": "$"},
            },
        ],
    }


class HttpCliTests(unittest.TestCase):
    def test_human_readable_run_passes(self) -> None:
        with LocalHTTPServer() as srv, tempfile.TemporaryDirectory() as tmp:
            path = _write_scenario(Path(tmp), _scenario_body(srv.url("/echo")))
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = main(["validate", str(path)])
        self.assertEqual(code, EXIT_OK, buf.getvalue())
        self.assertIn("[PASS]", buf.getvalue())

    def test_json_report_output(self) -> None:
        with LocalHTTPServer() as srv, tempfile.TemporaryDirectory() as tmp:
            path = _write_scenario(Path(tmp), _scenario_body(srv.url("/echo")))
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = main(["validate", str(path), "--json"])
        self.assertEqual(code, EXIT_OK)
        payload = json.loads(buf.getvalue())
        result = payload["results"][0]
        self.assertEqual(result["overall_status"], "PASS")
        self.assertEqual(result["execution_metadata"]["adapter"], "http")
        outcomes = {a["assertion_id"]: a["outcome"] for a in result["assertion_results"]}
        self.assertEqual(outcomes["status"], "PASS")
        self.assertEqual(outcomes["echoed"], "PASS")

    def test_transport_failure_exits_error(self) -> None:
        dead_url = f"http://127.0.0.1:{unused_localhost_port()}/echo"
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_scenario(Path(tmp), _scenario_body(dead_url))
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = main(["validate", str(path)])
        self.assertEqual(code, EXIT_ERROR, buf.getvalue())
        self.assertIn("[ERROR]", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
