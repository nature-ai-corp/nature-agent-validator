"""JSON (de)serialization for scenarios.

Only JSON is supported in Phase 0 -- it needs nothing beyond the standard
library. YAML support is intentionally deferred: it would require a
third-party parser, which is subject to OSS review (see ``README.md``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from nature_agent_validator.assertions.spec import AssertionSpec
from nature_agent_validator.errors import ScenarioError

from .request import ScenarioRequest
from .scenario import Scenario
from .target import ScenarioTarget


def scenario_from_dict(data: Mapping[str, Any]) -> Scenario:
    try:
        return Scenario(
            scenario_id=str(data["scenario_id"]),
            name=str(data["name"]),
            description=str(data.get("description", "")),
            target=ScenarioTarget.from_dict(data["target"]),
            request=ScenarioRequest.from_dict(data.get("request", {})),
            expectations=tuple(
                AssertionSpec.from_dict(item)
                for item in data.get("expectations", [])
            ),
            metadata=dict(data.get("metadata", {})),
        )
    except KeyError as exc:
        raise ScenarioError(f"scenario is missing required field {exc}") from None
    except (TypeError, ValueError) as exc:
        raise ScenarioError(f"scenario is malformed: {exc}") from None


def scenario_to_dict(scenario: Scenario) -> dict[str, Any]:
    return {
        "scenario_id": scenario.scenario_id,
        "name": scenario.name,
        "description": scenario.description,
        "target": scenario.target.to_dict(),
        "request": scenario.request.to_dict(),
        "expectations": [spec.to_dict() for spec in scenario.expectations],
        "metadata": dict(scenario.metadata),
    }


def _check_suffix(path: Path) -> None:
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        raise ScenarioError(
            f"{path.name}: YAML scenarios require a YAML parser dependency that "
            "is not approved in Phase 0. Convert the scenario to JSON."
        )
    if suffix != ".json":
        raise ScenarioError(
            f"{path.name}: unsupported scenario file type {suffix!r}; expected .json"
        )


def load_scenario(path: str | Path) -> Scenario:
    p = Path(path)
    _check_suffix(p)
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ScenarioError(f"scenario file not found: {p}") from None
    except json.JSONDecodeError as exc:
        raise ScenarioError(f"{p.name}: invalid JSON: {exc}") from None
    if not isinstance(raw, Mapping):
        raise ScenarioError(f"{p.name}: top-level JSON value must be an object")
    return scenario_from_dict(raw)


def load_scenarios(path: str | Path) -> list[Scenario]:
    """Load a single ``.json`` scenario file or every ``*.json`` in a directory."""
    p = Path(path)
    if p.is_dir():
        return [load_scenario(child) for child in sorted(p.glob("*.json"))]
    if not p.exists():
        raise ScenarioError(f"path not found: {p}")
    return [load_scenario(p)]


__all__ = [
    "load_scenario",
    "load_scenarios",
    "scenario_from_dict",
    "scenario_to_dict",
]
