"""Target adapter abstraction and the built-in static adapter."""

from __future__ import annotations

import unittest

from nature_agent_validator.adapters import (
    AdapterResponse,
    StaticAdapter,
    TargetAdapter,
    build_adapter,
)
# Internal table -- Phase 0 exposes no public adapter-registration API.
from nature_agent_validator.adapters.registry import _BUILTIN
from nature_agent_validator.errors import AdapterError
from nature_agent_validator.scenario import ScenarioRequest, ScenarioTarget


class StaticAdapterTests(unittest.TestCase):
    def test_is_a_target_adapter(self) -> None:
        self.assertTrue(issubclass(StaticAdapter, TargetAdapter))

    def test_from_config_builds_normalized_result_and_evidence(self) -> None:
        adapter = StaticAdapter.from_config(
            {
                "status": 200,
                "body": {"answer": "no"},
                "latency_ms": 12.0,
                "evidence": [
                    {
                        "event_id": "e1",
                        "event_type": "authorization.decision",
                        "timestamp": "2026-09-03T12:00:00+00:00",
                        "attributes": {"decision": "denied"},
                    }
                ],
            }
        )
        resp = adapter.send(ScenarioRequest(payload={"message": "hi"}))
        self.assertIsInstance(resp, AdapterResponse)
        self.assertEqual(resp.result.status, 200)
        self.assertEqual(resp.result.text, '{"answer": "no"}')
        self.assertIsNotNone(resp.evidence)
        self.assertTrue(resp.evidence.has_event_type("authorization.decision"))

    def test_from_config_without_evidence_yields_none(self) -> None:
        adapter = StaticAdapter.from_config({"status": 200, "text": "hi"})
        self.assertIsNone(adapter.send(ScenarioRequest()).evidence)


class RegistryTests(unittest.TestCase):
    def test_static_is_available(self) -> None:
        self.assertIn("static", _BUILTIN)

    def test_build_known_adapter(self) -> None:
        adapter = build_adapter(ScenarioTarget("static", {"status": 204}))
        self.assertIsInstance(adapter, StaticAdapter)

    def test_build_unknown_adapter_raises_adapter_error(self) -> None:
        with self.assertRaises(AdapterError):
            build_adapter(ScenarioTarget("http", {}))


if __name__ == "__main__":
    unittest.main()
