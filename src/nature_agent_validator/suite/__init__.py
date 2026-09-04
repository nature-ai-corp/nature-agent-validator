"""Scenario suites and batch validation (Phase 3).

A :class:`ScenarioSuite` is *only* an ordered collection of existing
:class:`~nature_agent_validator.scenario.scenario.Scenario` objects -- no
templates, variables, tags, filtering, or inheritance.

:class:`SuiteRunner` runs a suite by calling the existing single-scenario
:class:`~nature_agent_validator.runner.Runner` once per scenario, sequentially,
and collecting one :class:`~nature_agent_validator.reporting.ValidationResult`
each into a :class:`SuiteResult`. It duplicates none of the adapter, assertion,
evidence, or PASS/FAIL/ERROR logic -- the single-scenario Runner remains the
sole execution authority.

Directory discovery (:func:`load_suite`):

* the path must be a directory
* regular files whose name ends in ``.json`` are discovered
* ordering is lexical by file name (deterministic)
* sub-directories are **not** traversed
* non-``.json`` entries are ignored
* each file is parsed with the existing scenario deserializer; a malformed or
  structurally invalid scenario raises :class:`ScenarioError` (never silently
  skipped)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from nature_agent_validator.errors import ScenarioError
from nature_agent_validator.reporting import OverallStatus, ValidationResult
from nature_agent_validator.runner import Runner
from nature_agent_validator.scenario import Scenario
from nature_agent_validator.scenario.serialization import load_scenario


@dataclass(frozen=True, slots=True)
class ScenarioSuite:
    """An ordered, named collection of scenarios. Nothing more."""

    name: str
    scenarios: tuple[Scenario, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "scenarios", tuple(self.scenarios))

    def __iter__(self) -> Iterator[Scenario]:
        return iter(self.scenarios)

    def __len__(self) -> int:
        return len(self.scenarios)


def _discover_json_files(directory: Path) -> list[Path]:
    """Regular ``*.json`` files directly in ``directory``, lexically by name."""
    return sorted(
        (
            entry
            for entry in directory.iterdir()
            if entry.is_file() and entry.suffix == ".json"
        ),
        key=lambda p: p.name,
    )


def load_suite(path: str | Path) -> ScenarioSuite:
    """Discover and load every ``.json`` scenario directly under ``path``.

    Raises :class:`ScenarioError` when ``path`` is not a directory, when it
    contains no ``.json`` scenario file, or when any discovered file is not a
    valid scenario.
    """
    directory = Path(path)
    if not directory.is_dir():
        raise ScenarioError(f"suite path is not a directory: {directory}")
    files = _discover_json_files(directory)
    if not files:
        raise ScenarioError(f"no .json scenario files found in {directory}")
    scenarios = tuple(load_scenario(f) for f in files)  # existing deserializer
    return ScenarioSuite(name=directory.name or str(directory), scenarios=scenarios)


@dataclass(frozen=True, slots=True)
class SuiteResult:
    """Deterministic aggregation of one :class:`ValidationResult` per scenario.

    No new scenario status is introduced. ``overall_status`` uses the existing
    vocabulary with the precedence ``ERROR > FAIL > PASS``.
    """

    name: str
    results: tuple[ValidationResult, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "results", tuple(self.results))

    @property
    def total(self) -> int:
        return len(self.results)

    def scenario_counts(self) -> dict[str, int]:
        c = {"pass": 0, "fail": 0, "error": 0}
        for r in self.results:
            if r.overall_status is OverallStatus.PASS:
                c["pass"] += 1
            elif r.overall_status is OverallStatus.FAIL:
                c["fail"] += 1
            else:
                c["error"] += 1
        return c

    def assertion_counts(self) -> dict[str, int]:
        c = {"pass": 0, "fail": 0, "skipped": 0}
        for r in self.results:
            rc = r.counts()
            c["pass"] += rc["pass"]
            c["fail"] += rc["fail"]
            c["skipped"] += rc["skipped"]
        return c

    @property
    def overall_status(self) -> OverallStatus:
        statuses = {r.overall_status for r in self.results}
        if OverallStatus.ERROR in statuses:
            return OverallStatus.ERROR
        if OverallStatus.FAIL in statuses:
            return OverallStatus.FAIL
        return OverallStatus.PASS

    def summary_lines(self) -> list[str]:
        sc = self.scenario_counts()
        ac = self.assertion_counts()
        lines = [
            f"[{self.overall_status.value}] suite {self.name!r} -- "
            f"{self.total} scenario(s): "
            f"{sc['pass']} pass, {sc['fail']} fail, {sc['error']} error",
            f"    assertions: {ac['pass']} passed, {ac['fail']} failed, "
            f"{ac['skipped']} skipped",
        ]
        for r in self.results:
            rc = r.counts()
            extra = f" ({rc['skipped']} skipped)" if rc["skipped"] else ""
            lines.append(
                f"    - [{r.overall_status.value}] {r.scenario_id} "
                f"{r.scenario_name}{extra}"
            )
        return lines

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite": self.name,
            "overall_status": self.overall_status.value,
            "total_scenarios": self.total,
            "scenario_counts": self.scenario_counts(),
            "assertion_counts": self.assertion_counts(),
            # reuse ValidationResult serialization verbatim; order preserved
            "results": [r.to_dict() for r in self.results],
        }


class SuiteRunner:
    """Run a :class:`ScenarioSuite` by delegating each scenario to ``Runner``.

    Sequential only. No threads, asyncio, multiprocessing, retry, or fail-fast:
    every scenario in the suite is attempted, in order.
    """

    def __init__(self, runner: Runner | None = None) -> None:
        self._runner = runner if runner is not None else Runner()

    def run(self, suite: ScenarioSuite) -> SuiteResult:
        results: list[ValidationResult] = []
        for scenario in suite.scenarios:
            results.append(self._runner.run(scenario))  # single execution authority
        return SuiteResult(name=suite.name, results=tuple(results))


__all__ = [
    "ScenarioSuite",
    "SuiteResult",
    "SuiteRunner",
    "load_suite",
]
