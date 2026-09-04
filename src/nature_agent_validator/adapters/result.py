"""The normalized shape every adapter returns.

Adapters translate a transport-specific response into this common structure so
that assertions never need to know how the target was reached.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class NormalizedResult:
    #: Transport status where the concept applies (HTTP status, process exit
    #: code, ...). ``None`` when the transport has no such concept.
    status: int | None = None
    #: Parsed response body (e.g. decoded JSON), when the adapter can parse it.
    body: Any = None
    #: Response as text. Adapters SHOULD always populate this; assertions such
    #: as ``contains`` / ``regex_match`` operate on it.
    text: str = ""
    #: Response metadata headers, lower-cased keys recommended.
    headers: Mapping[str, str] = field(default_factory=dict)
    #: Wall-clock time the target took, in milliseconds, if measured.
    latency_ms: float | None = None
    #: Transport-level error message (connection refused, timeout, ...). A
    #: populated ``error`` still yields a result -- assertions decide the
    #: verdict; it does not by itself make the run an ``ERROR``.
    error: str | None = None
    #: Escape hatch to the underlying transport object, for debugging only.
    raw: Any = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "headers",
            MappingProxyType({str(k): str(v) for k, v in dict(self.headers).items()}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "body": self.body,
            "text": self.text,
            "headers": dict(self.headers),
            "latency_ms": self.latency_ms,
            "error": self.error,
        }


__all__ = ["NormalizedResult"]
