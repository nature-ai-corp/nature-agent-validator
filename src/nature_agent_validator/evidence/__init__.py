"""Evidence Contract -- a small, generic, optional record of what happened.

This is deliberately **not** the full Agent Evidence SDK. It is the minimal
surface the Validator needs to reason about internal agent behaviour when a
target environment chooses to expose it.

Design constraints (see ``docs/architecture.md``):

* small        -- two dataclasses, one version constant, one helper
* generic      -- no NATURE-specific event types are frozen here
* versionable  -- ``EvidenceRecord.contract_version``
* optional     -- the Validator runs with or without evidence

Evidence is *fact* (it records what happened). The Validator is *judgment*
(it decides whether what happened was acceptable). These responsibilities do
not mix: nothing in this module evaluates anything.

**Trust:** evidence is observational input supplied by the target. It is not
cryptographically verified, tamper-proof, or independently attested. The
Validator judges it deterministically; provenance assurance is future scope.

Coverage
--------
An :class:`EvidenceRecord` also declares which evidence *namespaces* it claims
to cover (``authorization``, ``tool``, ``knowledge``, ...). Coverage is what
lets a negative assertion tell "observed and absent" apart from "not
observable": absence of a ``tool.executed`` event only supports a
forbidden-tool assertion when the record declares that it covers ``tool``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any, Iterator, Mapping

from nature_agent_validator.errors import EvidenceError

#: Version of the Evidence Contract represented by this module. Bump on a
#: backward-incompatible change to the shape of :class:`EvidenceEvent` /
#: :class:`EvidenceRecord`. ``coverage`` (Phase 2) and the now-optional
#: ``timestamp`` are backward-compatible additions and do not bump it.
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


def evidence_namespace(event_type: str) -> str:
    """Return the coverage namespace for an event type.

    The namespace is the prefix before the first ``"."``; an event type with no
    dot is its own namespace.

    >>> evidence_namespace("tool.executed")
    'tool'
    >>> evidence_namespace("authorization.decision")
    'authorization'
    >>> evidence_namespace("response")
    'response'
    """
    return str(event_type).split(".", 1)[0]


def _parse_timestamp(raw: Any) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw
    text = str(raw)
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise EvidenceError(
            f"evidence event 'timestamp' is not ISO-8601: {raw!r}"
        ) from exc


@dataclass(frozen=True, slots=True)
class EvidenceEvent:
    """A single observed fact about a target's internal behaviour."""

    event_id: str
    event_type: str
    #: Optional. ``None`` when the target did not stamp the event.
    timestamp: datetime | None = None
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
            "timestamp": (
                self.timestamp.isoformat() if self.timestamp is not None else None
            ),
            "source": self.source,
            "attributes": dict(self.attributes),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvidenceEvent":
        if not isinstance(data, Mapping):
            raise EvidenceError(
                f"evidence event must be a JSON object, got {type(data).__name__}"
            )
        try:
            event_id = str(data["event_id"])
            event_type = str(data["event_type"])
        except KeyError as exc:
            raise EvidenceError(
                f"evidence event missing required field {exc}"
            ) from None
        attributes = data.get("attributes", {})
        if not isinstance(attributes, Mapping):
            raise EvidenceError(
                "evidence event 'attributes' must be a JSON object, got "
                f"{type(attributes).__name__}"
            )
        return cls(
            event_id=event_id,
            event_type=event_type,
            timestamp=_parse_timestamp(data.get("timestamp")),
            source=str(data.get("source", "")),
            attributes=dict(attributes),
        )


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    """An ordered collection of :class:`EvidenceEvent` for one target run,
    plus the set of evidence namespaces the target claims to cover."""

    events: tuple[EvidenceEvent, ...] = ()
    #: Open, string-based set of covered namespaces (e.g. ``("authorization",
    #: "tool")``). Never inferred from the events present -- only what the
    #: target explicitly declared.
    coverage: tuple[str, ...] = ()
    contract_version: str = EVIDENCE_CONTRACT_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "events", tuple(self.events))
        object.__setattr__(
            self,
            "coverage",
            tuple(dict.fromkeys(str(c) for c in self.coverage)),
        )

    def __iter__(self) -> Iterator[EvidenceEvent]:
        return iter(self.events)

    def __len__(self) -> int:
        return len(self.events)

    def covers(self, namespace: str) -> bool:
        """Whether ``namespace`` is in the declared coverage set."""
        return str(namespace) in self.coverage

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
            "coverage": list(self.coverage),
            "events": [e.to_dict() for e in self.events],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvidenceRecord":
        if not isinstance(data, Mapping):
            raise EvidenceError(
                f"evidence must be a JSON object, got {type(data).__name__}"
            )
        raw_events = data.get("events", [])
        if not isinstance(raw_events, (list, tuple)):
            raise EvidenceError(
                f"evidence 'events' must be a list, got {type(raw_events).__name__}"
            )
        raw_coverage = data.get("coverage", [])
        if not isinstance(raw_coverage, (list, tuple)) or not all(
            isinstance(c, str) for c in raw_coverage
        ):
            raise EvidenceError("evidence 'coverage' must be a list of strings")
        return cls(
            events=tuple(EvidenceEvent.from_dict(e) for e in raw_events),
            coverage=tuple(raw_coverage),
            contract_version=str(
                data.get("contract_version", EVIDENCE_CONTRACT_VERSION)
            ),
        )

    @classmethod
    def from_events(
        cls, events: list[Mapping[str, Any]] | None
    ) -> "EvidenceRecord | None":
        """Build a record from a bare list of event dicts (no coverage), or
        ``None`` if omitted. Kept for the legacy list form of static evidence."""
        if events is None:
            return None
        if not isinstance(events, (list, tuple)):
            raise EvidenceError(
                f"evidence events must be a list, got {type(events).__name__}"
            )
        return cls(events=tuple(EvidenceEvent.from_dict(e) for e in events))


__all__ = [
    "EVIDENCE_CONTRACT_VERSION",
    "KNOWN_EVENT_TYPES",
    "EvidenceEvent",
    "EvidenceRecord",
    "evidence_namespace",
]
