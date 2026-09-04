"""JUnit XML export for a :class:`~nature_agent_validator.suite.SuiteResult`
(Phase 4 -- reporting interoperability only).

This is **one explicit reporter**, not a plugin framework: a single pure
function that turns an already-computed ``SuiteResult`` into a JUnit XML
string. It runs no scenarios and changes no validation status.

Frozen mapping
--------------
* one ``SuiteResult``            -> one ``<testsuite>``
* one ``ValidationResult`` (scenario) -> one ``<testcase>``  (never per-assertion)
* scenario ``PASS``   -> ``<testcase>`` with no ``<failure>`` / ``<error>`` / ``<skipped>``
* scenario ``FAIL``   -> ``<testcase>`` with one ``<failure>``
* scenario ``ERROR``  -> ``<testcase>`` with one ``<error>``

Assertion-level ``SKIPPED`` is **never** a JUnit ``<skipped>`` and never
changes the testcase result -- NATURE has no scenario-level SKIPPED state.
``<testsuite skipped>`` is therefore always ``"0"``. Assertion pass/fail/skip
counts are preserved only as diagnostics (``<properties>`` and
``<system-out>``).

Security: the reporter never emits request headers, credentials, raw HTTP
request/response bodies, or raw evidence payloads. In particular it does
**not** emit ``AssertionResult.observed`` (which can carry clipped
target-originated response text). Diagnostics are limited to the assertion
``type`` + the framework's own normalized ``message`` string, and, for
``ERROR``, the existing ``ValidationResult.errors`` strings.

Determinism: output is a pure function of the ``SuiteResult`` -- scenario
order is preserved, attribute order is fixed, and no wall-clock timestamp,
hostname, random id, or absolute path is added. ``time`` (seconds) is emitted
only from the scenario duration already recorded in ``ExecutionMetadata``.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from nature_agent_validator.assertions.result import AssertionOutcome
from nature_agent_validator.reporting import OverallStatus, ValidationResult
from nature_agent_validator.suite import SuiteResult


def _failure_text(result: ValidationResult) -> str:
    failed = [
        a for a in result.assertion_results if a.outcome is AssertionOutcome.FAIL
    ]
    lines = [
        f"[{a.type}] {a.assertion_id}: {a.message}".rstrip()
        for a in failed
    ]
    return "\n".join(lines) if lines else "one or more expectations were not met"


def _testcase(parent: ET.Element, suite_name: str, result: ValidationResult) -> None:
    counts = result.counts()
    attrs = {
        "name": result.scenario_name or result.scenario_id,
        "classname": suite_name,
    }
    md = result.execution_metadata
    if md is not None:
        attrs["time"] = f"{max(md.duration_ms, 0.0) / 1000.0:.3f}"
    testcase = ET.SubElement(parent, "testcase", attrs)

    props = ET.SubElement(testcase, "properties")
    for name, value in (
        ("scenario_id", result.scenario_id),
        ("assertions.passed", str(counts["pass"])),
        ("assertions.failed", str(counts["fail"])),
        ("assertions.skipped", str(counts["skipped"])),
    ):
        ET.SubElement(props, "property", {"name": name, "value": value})

    if result.overall_status is OverallStatus.FAIL:
        failure = ET.SubElement(
            testcase,
            "failure",
            {"message": f"{counts['fail']} assertion(s) failed", "type": "assertion"},
        )
        failure.text = _failure_text(result)
    elif result.overall_status is OverallStatus.ERROR:
        error = ET.SubElement(
            testcase,
            "error",
            {"message": "scenario execution could not complete", "type": "error"},
        )
        error.text = "\n".join(result.errors) or "scenario execution could not complete"

    system_out = ET.SubElement(testcase, "system-out")
    system_out.text = (
        f"Assertions: passed={counts['pass']} "
        f"failed={counts['fail']} skipped={counts['skipped']}"
    )


def suite_result_to_junit_xml(result: SuiteResult) -> str:
    """Render ``result`` as a JUnit XML document string (UTF-8, with header)."""
    scenario_counts = result.scenario_counts()
    testsuite = ET.Element(
        "testsuite",
        {
            "name": result.name,
            "tests": str(result.total),
            "failures": str(scenario_counts["fail"]),
            "errors": str(scenario_counts["error"]),
            "skipped": "0",  # assertion SKIPPED is never a scenario/testcase skip
        },
    )

    durations = [
        r.execution_metadata.duration_ms
        for r in result.results
        if r.execution_metadata is not None
    ]
    if result.results and len(durations) == len(result.results):
        testsuite.set(
            "time", f"{sum(max(d, 0.0) for d in durations) / 1000.0:.3f}"
        )

    for scenario_result in result.results:  # suite order preserved
        _testcase(testsuite, result.name, scenario_result)

    ET.indent(testsuite)
    return ET.tostring(testsuite, encoding="unicode", xml_declaration=True)


__all__ = ["suite_result_to_junit_xml"]
