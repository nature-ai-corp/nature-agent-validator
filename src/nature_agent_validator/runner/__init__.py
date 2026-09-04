"""The :class:`Runner` -- orchestrates one scenario into one ``ValidationResult``.

Flow:

1. resolve a target adapter (passed in, or built from ``scenario.target``)
2. send ``scenario.request`` and collect the normalized result + optional evidence
3. build and evaluate every expectation against that context
4. fold the outcomes into a :class:`ValidationResult`

The runner contains no transport logic (that is the adapter's job) and no
judgment logic (that is the assertions' job). Validator-side failures are
caught and surfaced as ``ERROR``; they are never reported as failed assertions.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Callable, Iterable

from nature_agent_validator.adapters import TargetAdapter, build_adapter
from nature_agent_validator.adapters.base import AdapterResponse
from nature_agent_validator.assertions import AssertionContext, build_assertion
from nature_agent_validator.assertions.result import AssertionOutcome, AssertionResult
from nature_agent_validator.reporting import (
    EvidenceSummary,
    ExecutionMetadata,
    OverallStatus,
    ValidationResult,
)
from nature_agent_validator.scenario import Scenario
from nature_agent_validator.scenario.target import ScenarioTarget

AdapterFactory = Callable[[ScenarioTarget], TargetAdapter]


class Runner:
    def __init__(self, adapter_factory: AdapterFactory | None = None) -> None:
        self._adapter_factory: AdapterFactory = adapter_factory or build_adapter

    def run(
        self, scenario: Scenario, adapter: TargetAdapter | None = None
    ) -> ValidationResult:
        started = datetime.now(timezone.utc)
        perf_start = time.perf_counter()
        errors: list[str] = []
        owns_adapter = adapter is None

        if adapter is None:
            try:
                adapter = self._adapter_factory(scenario.target)
            except Exception as exc:  # noqa: BLE001 - reported as ERROR
                return self._finish(
                    scenario,
                    OverallStatus.ERROR,
                    (),
                    EvidenceSummary(available=False),
                    [f"adapter build failed: {exc}"],
                    started,
                    perf_start,
                )

        response: AdapterResponse | None = None
        try:
            response = adapter.send(scenario.request)
        except Exception as exc:  # noqa: BLE001 - reported as ERROR
            errors.append(f"adapter send failed: {exc!r}")
        finally:
            if owns_adapter:
                try:
                    adapter.close()
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"adapter close failed: {exc!r}")

        if response is None:
            return self._finish(
                scenario,
                OverallStatus.ERROR,
                (),
                EvidenceSummary(available=False),
                errors,
                started,
                perf_start,
            )

        context = AssertionContext(
            result=response.result, evidence=response.evidence
        )
        results: list[AssertionResult] = []
        for spec in scenario.expectations:
            try:
                assertion = build_assertion(spec)
                results.append(assertion.evaluate(context))
            except Exception as exc:  # noqa: BLE001 - reported as ERROR
                errors.append(f"assertion {spec.assertion_id!r} error: {exc}")

        evidence_summary = EvidenceSummary.from_record(response.evidence)

        if errors:
            status = OverallStatus.ERROR
        elif any(r.outcome is AssertionOutcome.FAIL for r in results):
            status = OverallStatus.FAIL
        else:
            status = OverallStatus.PASS

        return self._finish(
            scenario,
            status,
            tuple(results),
            evidence_summary,
            errors,
            started,
            perf_start,
        )

    def run_many(self, scenarios: Iterable[Scenario]) -> list[ValidationResult]:
        return [self.run(scenario) for scenario in scenarios]

    # -- internal --------------------------------------------------------------

    @staticmethod
    def _finish(
        scenario: Scenario,
        status: OverallStatus,
        assertion_results: tuple[AssertionResult, ...],
        evidence_summary: EvidenceSummary,
        errors: list[str],
        started: datetime,
        perf_start: float,
    ) -> ValidationResult:
        finished = datetime.now(timezone.utc)
        metadata = ExecutionMetadata(
            adapter=scenario.target.adapter,
            started_at=started,
            finished_at=finished,
            duration_ms=(time.perf_counter() - perf_start) * 1000.0,
        )
        return ValidationResult(
            scenario_id=scenario.scenario_id,
            scenario_name=scenario.name,
            overall_status=status,
            assertion_results=assertion_results,
            execution_metadata=metadata,
            evidence_summary=evidence_summary,
            errors=tuple(errors),
        )


__all__ = ["Runner"]
