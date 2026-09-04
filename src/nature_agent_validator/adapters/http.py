"""Generic HTTP target adapter (Phase 1).

The first adapter that reaches a *real* external target. It sends one HTTP
request described entirely by the scenario and normalizes whatever comes back
into a :class:`~nature_agent_validator.adapters.result.NormalizedResult`, so
that assertions never see an HTTP object.

Standard library only -- :mod:`urllib.request` / :mod:`urllib.error`. No
third-party HTTP client, no TLS-bypass options, no authentication framework.

Error semantics (see ``docs/architecture.md`` -- Outcome model):

* A *completed* HTTP exchange -- including 3xx, 4xx and 5xx -- is returned as a
  ``NormalizedResult``. Assertions decide the verdict. A scenario may
  legitimately expect ``302`` / ``401`` / ``403`` / ``404`` / ``500``.
* A *transport* failure (DNS failure, connection refused, timeout, malformed
  URL, unsupported scheme) raises :class:`AdapterError`, which the runner
  surfaces as ``ERROR`` -- never as a failed assertion.

Automatic redirect following is **disabled**: the explicitly configured target
stays authoritative. A ``3xx`` response is normalized and handed to assertions
like any other response, with its ``Location`` header preserved in
``NormalizedResult.headers``. Configurable redirect support is deferred to a
later architecture decision.

Optional evidence (Phase 2): if ``target.config`` declares ``evidence_field``
and the JSON response body contains that top-level key, its value is parsed as
an :class:`~nature_agent_validator.evidence.EvidenceRecord` (``{coverage,
events}``). No JSONPath, no nested paths, no header transport, no vendor
schema. A present-but-malformed evidence field is an ``AdapterError`` (→
``ERROR``) -- it is never silently downgraded to "no evidence".

This module is imported lazily by :func:`nature_agent_validator.adapters.registry.build_adapter`
so that merely importing the core package pulls in no networking modules.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import TYPE_CHECKING, Any, Mapping
from urllib.parse import urlsplit

from nature_agent_validator.errors import AdapterError, EvidenceError
from nature_agent_validator.evidence import EvidenceRecord

from .base import AdapterResponse, TargetAdapter
from .result import NormalizedResult

if TYPE_CHECKING:
    from nature_agent_validator.scenario.request import ScenarioRequest

_DEFAULT_TIMEOUT_SECONDS = 30.0
_ALLOWED_SCHEMES = ("http", "https")


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Never follow a redirect.

    Returning ``None`` from ``redirect_request`` tells urllib not to issue the
    follow-up request; the ``3xx`` response then propagates out of the opener
    (as an :class:`urllib.error.HTTPError`) and is normalized like any other
    HTTP response.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        return None


#: Module-level opener: the stdlib default chain with redirect-following
#: replaced by the no-op handler above. Stateless; safe to share.
_OPENER = urllib.request.build_opener(_NoRedirectHandler)


def _has_header(headers: Mapping[str, str], name: str) -> bool:
    lowered = name.lower()
    return any(str(k).lower() == lowered for k in headers)


def _try_parse_json(text: str) -> Any:
    """Return the parsed JSON value, or ``None`` when the body is not JSON."""
    if not text:
        return None
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None


class HttpAdapter(TargetAdapter):
    """Send ``scenario.request`` to an HTTP endpoint and normalize the response.

    Configuration (``scenario.target.config``):

    * ``url`` -- required; must be ``http://`` or ``https://``
    * ``method`` -- optional; defaults to ``POST`` when the request carries a
      body, otherwise ``GET``
    * ``headers`` -- optional mapping of static request headers
    * ``timeout_seconds`` -- optional; defaults to ``30``
    * ``evidence_field`` -- optional; a top-level JSON response key to parse as
      an ``EvidenceRecord`` (see the module docstring)

    The request body is ``scenario.request.payload``:

    * ``None``            -> no body
    * ``str`` / ``bytes`` -> sent as-is
    * anything else       -> JSON-encoded, with ``Content-Type: application/json``
      added when the scenario did not set it

    Redirects are not followed (Phase 1): a ``3xx`` is returned to assertions
    as-is.
    """

    name = "http"

    def __init__(
        self,
        url: str,
        *,
        method: str | None = None,
        headers: Mapping[str, Any] | None = None,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        evidence_field: str | None = None,
    ) -> None:
        scheme = urlsplit(url).scheme.lower()
        if scheme not in _ALLOWED_SCHEMES:
            raise AdapterError(
                f"http adapter only supports {' / '.join(_ALLOWED_SCHEMES)} URLs; "
                f"got {scheme or '(none)'!r} in {url!r}"
            )
        self._url = url
        self._method = method.upper() if method else None
        self._headers: dict[str, str] = {
            str(k): str(v) for k, v in dict(headers or {}).items()
        }
        self._timeout = float(timeout_seconds)
        self._evidence_field = evidence_field

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> "HttpAdapter":
        try:
            url = config["url"]
        except KeyError:
            raise AdapterError(
                "http adapter requires 'url' in target.config"
            ) from None
        timeout = config.get("timeout_seconds", _DEFAULT_TIMEOUT_SECONDS)
        try:
            timeout = float(timeout)
        except (TypeError, ValueError):
            raise AdapterError(
                f"http adapter: 'timeout_seconds' must be a number, got {timeout!r}"
            ) from None
        headers = config.get("headers")
        if headers is not None and not isinstance(headers, Mapping):
            raise AdapterError(
                f"http adapter: 'headers' must be a mapping, got {type(headers).__name__}"
            )
        method = config.get("method")
        if method is not None and not isinstance(method, str):
            raise AdapterError(
                f"http adapter: 'method' must be a string, got {type(method).__name__}"
            )
        evidence_field = config.get("evidence_field")
        if evidence_field is not None and not isinstance(evidence_field, str):
            raise AdapterError(
                "http adapter: 'evidence_field' must be a string, got "
                f"{type(evidence_field).__name__}"
            )
        return cls(
            url=str(url),
            method=method,
            headers=headers,
            timeout_seconds=timeout,
            evidence_field=evidence_field,
        )

    # -- internal ------------------------------------------------------------

    @staticmethod
    def _encode_body(payload: Any) -> tuple[bytes | None, bool]:
        """Return ``(body_bytes_or_None, is_json)``."""
        if payload is None:
            return None, False
        if isinstance(payload, bytes):
            return payload, False
        if isinstance(payload, str):
            return payload.encode("utf-8"), False
        return json.dumps(payload).encode("utf-8"), True

    # -- TargetAdapter -----------------------------------------------------

    def send(self, request: "ScenarioRequest") -> AdapterResponse:
        body, is_json = self._encode_body(request.payload)
        headers = dict(self._headers)
        if body is not None and is_json and not _has_header(headers, "content-type"):
            headers["Content-Type"] = "application/json"

        method = self._method or ("POST" if body is not None else "GET")
        req = urllib.request.Request(
            self._url, data=body, method=method, headers=headers
        )

        start = time.perf_counter()
        try:
            with _OPENER.open(req, timeout=self._timeout) as resp:
                raw = resp.read()
                status = int(resp.status)
                resp_headers = _response_headers(resp.headers)
        except urllib.error.HTTPError as exc:
            # A complete HTTP response that happens to be non-2xx (3xx included,
            # since redirects are not followed). A result, not a transport
            # error -- hand it to the assertions.
            try:
                raw = exc.read() or b""
            finally:
                exc.close()
            status = int(exc.code)
            resp_headers = _response_headers(exc.headers)
        except urllib.error.URLError as exc:
            raise AdapterError(
                f"HTTP request to {self._url!r} failed: {exc.reason}"
            ) from exc
        except TimeoutError as exc:
            raise AdapterError(
                f"HTTP request to {self._url!r} timed out after {self._timeout}s"
            ) from exc
        except ValueError as exc:
            raise AdapterError(
                f"HTTP request to {self._url!r} could not be sent: {exc}"
            ) from exc
        except OSError as exc:
            raise AdapterError(
                f"HTTP request to {self._url!r} failed: {exc}"
            ) from exc
        elapsed_ms = (time.perf_counter() - start) * 1000.0

        text = raw.decode("utf-8", errors="replace")
        result = NormalizedResult(
            status=status,
            body=_try_parse_json(text),
            text=text,
            headers=resp_headers,
            latency_ms=elapsed_ms,
            error=None,
        )
        return AdapterResponse(
            result=result, evidence=self._extract_evidence(result.body)
        )

    def _extract_evidence(self, body: Any) -> "EvidenceRecord | None":
        """Optional, portable evidence extraction.

        Returns ``None`` (black-box) unless ``evidence_field`` is configured
        *and* the JSON body carries that top-level key. A present-but-malformed
        value is raised as an ``AdapterError`` so it is never mistaken for
        trusted evidence.
        """
        field = self._evidence_field
        if field is None or not isinstance(body, Mapping) or field not in body:
            return None
        try:
            return EvidenceRecord.from_dict(body[field])
        except EvidenceError as exc:
            raise AdapterError(
                f"HTTP response evidence in field {field!r} is malformed: {exc}"
            ) from exc


def _response_headers(message: Any) -> dict[str, str]:
    if message is None:
        return {}
    try:
        items = message.items()
    except AttributeError:  # pragma: no cover - defensive
        return {}
    return {str(k).lower(): str(v) for k, v in items}


__all__ = ["HttpAdapter"]
