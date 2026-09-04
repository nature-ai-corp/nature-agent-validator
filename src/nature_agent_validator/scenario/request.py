"""The request a scenario sends to its target.

Intentionally transport-agnostic. ``payload`` is whatever the target adapter
understands (a JSON body, a prompt string, CLI args, ...). ``attributes``
carries adapter-specific hints (HTTP method/path/headers, timeouts, a role to
impersonate) without the scenario format taking a dependency on any one
transport.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class ScenarioRequest:
    payload: Any = None
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "attributes", MappingProxyType(dict(self.attributes))
        )

    def to_dict(self) -> dict[str, Any]:
        return {"payload": self.payload, "attributes": dict(self.attributes)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ScenarioRequest":
        return cls(
            payload=data.get("payload"),
            attributes=dict(data.get("attributes", {})),
        )


__all__ = ["ScenarioRequest"]
