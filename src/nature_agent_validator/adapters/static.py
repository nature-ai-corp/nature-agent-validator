"""A canned-response adapter.

``StaticAdapter`` returns a fixed response and never touches the network. It
exists so the full engine (scenario -> runner -> assertions -> result) can be
exercised in tests, examples, and the CLI with zero dependencies and zero
external services. It is also a minimal reference implementation of
:class:`TargetAdapter`.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Mapping

from nature_agent_validator.evidence import EvidenceRecord

from .base import AdapterResponse, TargetAdapter
from .result import NormalizedResult

if TYPE_CHECKING:
    from nature_agent_validator.scenario.request import ScenarioRequest


class StaticAdapter(TargetAdapter):
    name = "static"

    def __init__(self, response: AdapterResponse) -> None:
        self._response = response

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> "StaticAdapter":
        body = config.get("body")
        text = config.get("text")
        if text is None and body is not None:
            text = json.dumps(body)
        result = NormalizedResult(
            status=config.get("status"),
            body=body,
            text=text or "",
            headers=config.get("headers", {}),
            latency_ms=config.get("latency_ms"),
            error=config.get("error"),
        )
        evidence = _build_evidence(config.get("evidence"))
        return cls(AdapterResponse(result=result, evidence=evidence))

    def send(self, request: "ScenarioRequest") -> AdapterResponse:
        return self._response


def _build_evidence(raw: Any) -> "EvidenceRecord | None":
    """Accept either the full ``{coverage, events}`` object or the legacy bare
    list of event dicts. Malformed evidence raises ``EvidenceError``."""
    if raw is None:
        return None
    if isinstance(raw, Mapping):
        return EvidenceRecord.from_dict(raw)
    return EvidenceRecord.from_events(raw)


__all__ = ["StaticAdapter"]
