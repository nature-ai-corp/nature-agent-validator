"""The :class:`Scenario` -- the portable unit of validation.

A scenario is a plain, serializable description of:

* what to send (``request``) to which target (``target``)
* what behaviour is expected (``expectations`` -- a list of assertion specs)
* identifying / grouping information (``scenario_id``, ``name``, ``metadata``)

It contains no execution logic and no NATURE-specific fields. The same
scenario definition is valid whether the target exposes structured evidence
or is a complete black box.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Mapping

from .request import ScenarioRequest
from .target import ScenarioTarget

if TYPE_CHECKING:
    from nature_agent_validator.assertions.spec import AssertionSpec


@dataclass(frozen=True, slots=True)
class Scenario:
    scenario_id: str
    name: str
    target: ScenarioTarget
    request: ScenarioRequest
    description: str = ""
    expectations: tuple["AssertionSpec", ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "expectations", tuple(self.expectations))
        object.__setattr__(
            self, "metadata", MappingProxyType(dict(self.metadata))
        )


__all__ = ["Scenario"]
