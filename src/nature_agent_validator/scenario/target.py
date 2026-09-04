"""Which target adapter a scenario runs against, and how to configure it."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class ScenarioTarget:
    #: Name of a registered target adapter (e.g. ``"static"``, later ``"http"``).
    adapter: str
    #: Adapter-specific configuration (base URL, headers, canned response, ...).
    config: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "config", MappingProxyType(dict(self.config)))

    def to_dict(self) -> dict[str, Any]:
        return {"adapter": self.adapter, "config": dict(self.config)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ScenarioTarget":
        return cls(
            adapter=str(data["adapter"]),
            config=dict(data.get("config", {})),
        )


__all__ = ["ScenarioTarget"]
