"""Scenario domain objects: immutability and JSON round-tripping."""

from __future__ import annotations

import dataclasses
import unittest

from nature_agent_validator.assertions import AssertionSpec
from nature_agent_validator.errors import ScenarioError
from nature_agent_validator.scenario import Scenario, ScenarioRequest, ScenarioTarget
from nature_agent_validator.scenario.serialization import (
    scenario_from_dict,
    scenario_to_dict,
)


def _sample() -> Scenario:
    return Scenario(
        scenario_id="s1",
        name="sample",
        description="d",
        target=ScenarioTarget("static", {"status": 200}),
        request=ScenarioRequest(payload={"message": "hi"}, attributes={"method": "POST"}),
        expectations=(
            AssertionSpec("a1", "status_equals", {"value": 200}),
            AssertionSpec("a2", "contains", {"value": "ok"}),
        ),
        metadata={"suite": "demo"},
    )


class ScenarioTests(unittest.TestCase):
    def test_frozen(self) -> None:
        s = _sample()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            s.scenario_id = "other"  # type: ignore[misc]

    def test_mapping_fields_are_read_only(self) -> None:
        s = _sample()
        with self.assertRaises(TypeError):
            s.metadata["x"] = 1  # type: ignore[index]

    def test_expectations_coerced_to_tuple(self) -> None:
        s = Scenario(
            scenario_id="s",
            name="n",
            target=ScenarioTarget("static"),
            request=ScenarioRequest(),
            expectations=[AssertionSpec("a", "contains", {"value": "x"})],
        )
        self.assertIsInstance(s.expectations, tuple)

    def test_dict_round_trip(self) -> None:
        s = _sample()
        self.assertEqual(scenario_from_dict(scenario_to_dict(s)), s)

    def test_missing_required_field_raises_scenario_error(self) -> None:
        with self.assertRaises(ScenarioError):
            scenario_from_dict({"name": "no id", "target": {"adapter": "static"}})


if __name__ == "__main__":
    unittest.main()
