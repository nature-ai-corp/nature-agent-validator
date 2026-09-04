"""Evaluator Provider is a boundary only -- no implementation ships in Phase 0."""

from __future__ import annotations

import unittest

from nature_agent_validator.evaluators import (
    EvaluationRequest,
    EvaluationVerdict,
    EvaluatorProvider,
)


class _StubEvaluator:
    """A local, model-free stand-in used only to exercise the protocol."""

    name = "stub"

    def evaluate(self, request: EvaluationRequest) -> EvaluationVerdict:
        passed = request.criterion.lower() in request.observed_text.lower()
        return EvaluationVerdict(passed=passed, provider=self.name)


class EvaluatorBoundaryTests(unittest.TestCase):
    def test_stub_satisfies_runtime_checkable_protocol(self) -> None:
        self.assertIsInstance(_StubEvaluator(), EvaluatorProvider)

    def test_request_context_is_read_only(self) -> None:
        req = EvaluationRequest("s", "polite", "hello", {"k": 1})
        with self.assertRaises(TypeError):
            req.context["k"] = 2  # type: ignore[index]

    def test_verdict_round_trips_to_dict(self) -> None:
        verdict = EvaluationVerdict(passed=True, score=0.9, rationale="ok", provider="stub")
        self.assertEqual(
            verdict.to_dict(),
            {"passed": True, "score": 0.9, "rationale": "ok", "provider": "stub"},
        )

    def test_no_core_module_imports_an_evaluator_backend(self) -> None:
        import nature_agent_validator.evaluators as ev

        source = ev.__file__
        self.assertTrue(source.endswith("__init__.py"))


if __name__ == "__main__":
    unittest.main()
