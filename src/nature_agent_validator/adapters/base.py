"""The Target Adapter abstraction.

An adapter is the only component that knows how to reach a target. It sends a
:class:`~nature_agent_validator.scenario.request.ScenarioRequest`, returns a
:class:`~nature_agent_validator.adapters.result.NormalizedResult`, and MAY
attach a :class:`~nature_agent_validator.evidence.EvidenceRecord` when the
target environment exposes internal evidence.

Phase 0 ships one concrete adapter -- :class:`~nature_agent_validator.adapters.static.StaticAdapter`
(a no-network fixture). Future adapters (HTTP, CLI, local callable, WebSocket,
MCP, ...) implement this same interface without changing the runner.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Mapping

from nature_agent_validator.errors import AdapterError

from .result import NormalizedResult

if TYPE_CHECKING:
    from nature_agent_validator.evidence import EvidenceRecord
    from nature_agent_validator.scenario.request import ScenarioRequest


@dataclass(frozen=True, slots=True)
class AdapterResponse:
    """What an adapter hands back to the runner."""

    result: NormalizedResult
    #: ``None`` for black-box targets; a record when evidence is available.
    evidence: "EvidenceRecord | None" = None


class TargetAdapter(ABC):
    """Base class for all target adapters."""

    #: Stable identifier used in ``scenario.target.adapter``.
    name: ClassVar[str] = ""

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> "TargetAdapter":
        """Build an adapter instance from ``scenario.target.config``.

        Subclasses that can be created declaratively (and therefore driven from
        a serialized scenario / the CLI) override this.
        """
        raise AdapterError(
            f"adapter {cls.name or cls.__name__!r} cannot be constructed from "
            "config; instantiate it directly and pass it to Runner.run()"
        )

    @abstractmethod
    def send(self, request: "ScenarioRequest") -> AdapterResponse:
        """Send ``request`` to the target and return a normalized response."""

    def close(self) -> None:
        """Release any resources. Overridden by adapters that hold connections."""
        return None


__all__ = ["AdapterResponse", "TargetAdapter"]
