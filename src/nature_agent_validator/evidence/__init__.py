"""Evidence Contract -- a small, generic, optional record of what happened.

This is deliberately **not** the full Agent Evidence SDK. It is the minimal
surface the Validator needs to reason about internal agent behaviour when a
target environment chooses to expose it.

Design constraints (see ``docs/architecture.md``):

* small        -- two dataclasses, one version constant
* generic      -- no NATURE-specific event types are frozen here
* versionable  -- ``EvidenceRecord.contract_version``
* optional     -- the Validator runs with or without evidence

Evidence is *fact* (it records what happened). The Validator is *judgment*
(it decides whether what happened was acceptable). These responsibilities do
not mix: nothing in this module evaluates anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any, Iterator, Mapping

#: Version of the Evidence Contract represented by this module. Bump on any
#: change to the shape of :class:`EvidenceEvent` / :class:`EvidenceRecord`.
EVIDENCE_CONTRACT_VERSION = "0.1.0"

# Non-binding vocabulary. Adapters MAY emit these event types; the Validator
# does not require any of them. Kept here purely as documentation.
KNOWN_EVENT_TYPES: tuple[str, ...] = (
    "request.received",
    "agent.selected",
    "authorization.decision",
    "model.invoked",
    "skill.invoked",
    "knowledge.accessed",
    "tool.requested",
    "tool.executed",
    "workflow.transition",
    "response.generated",
)


@dataclass(frozen=True, slots=True)
class EvidenceEvent:
    """A single observed fact about a target's internal behaviour."""

    event_id: str
    event_type: str
    timestamp: datetime
    source: str = ""
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "attributes", MappingProxyType(dict(self.attributes))
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "attributes": dict(self.attributes),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvidenceEvent":
        raw_ts = data["timestamp"]
        timestamp = (
            raw_ts
            if isinstance(raw_ts, datetime)
            else datetime.fromisoformat(str(raw_ts))
        )
        return cls(
            event_id=str(data["event_id"]),
            event_type=str(data["event_type"]),
            timestamp=timestamp,
            source=str(data.get("source", "")),
            attributes=dict(data.get("attributes", {})),
        )


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    """An ordered collection of :class:`EvidenceEvent` for one target run."""

    events: tuple[EvidenceEvent, ...] = ()
    contract_version: str = EVIDENCE_CONTRACT_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "events", tuple(self.events))

    def __iter__(self) -> Iterator[EvidenceEvent]:
        return iter(self.events)

    def __len__(self) -> int:
        return len(self.events)

    def event_types(self) -> tuple[str, ...]:
        """Distinct event types, in first-seen order."""
        seen: dict[str, None] = {}
        for event in self.events:
            seen.setdefault(event.event_type, None)
        return tuple(seen)

    def has_event_type(self, event_type: str) -> bool:
        return any(e.event_type == event_type for e in self.events)

    def of_type(self, event_type: str) -> tuple[EvidenceEvent, ...]:
        return tuple(e for e in self.events if e.event_type == event_type)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "events": [e.to_dict() for e in self.events],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvidenceRecord":
        return cls(
            events=tuple(
                EvidenceEvent.from_dict(e) for e in data.get("events", [])
            ),
            contract_version=str(
                data.get("contract_version", EVIDENCE_CONTRACT_VERSION)
            ),
        )

    @classmethod
    def from_events(
        cls, events: list[Mapping[str, Any]] | None
    ) -> "EvidenceRecord | None":
        """Build a record from a list of event dicts, or ``None`` if omitted."""
        if events is None:
            return None
        return cls(events=tuple(EvidenceEvent.from_dict(e) for e in events))


__all__ = [
    "EVIDENCE_CONTRACT_VERSION",
    "KNOWN_EVENT_TYPES",
    "EvidenceEvent",
    "EvidenceRecord",
]
