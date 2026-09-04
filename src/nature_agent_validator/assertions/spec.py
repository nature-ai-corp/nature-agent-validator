"""Serializable description of one expectation.

An :class:`AssertionSpec` is data only. The runner turns each spec into a live
:class:`~nature_agent_validator.assertions.base.Assertion` via the registry at
execution time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class AssertionSpec:
    #: Stable identifier, unique within a scenario. Echoed into the result.
    assertion_id: str
    #: Registered assertion type name (e.g. ``"status_equals"``, ``"contains"``).
    type: str
    #: Type-specific configuration (expected value, threshold, path, ...).
    config: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "config", MappingProxyType(dict(self.config)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "assertion_id": self.assertion_id,
            "type": self.type,
            "config": dict(self.config),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AssertionSpec":
        return cls(
            assertion_id=str(data["assertion_id"]),
            type=str(data["type"]),
            config=dict(data.get("config", {})),
        )


__all__ = ["AssertionSpec"]
