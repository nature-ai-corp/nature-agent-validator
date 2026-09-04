"""A tiny deterministic localhost HTTP server for the HTTP-adapter tests.

Standard library only. **Test-only** -- this is not part of the product
architecture. It binds exclusively to ``127.0.0.1`` on an ephemeral port, so
the suite never needs Internet access and never opens a public listener.

Routes:

* ``GET  /text``  -> ``200`` ``text/plain`` body ``"hello world"``
* ``*    /echo``  -> ``200`` JSON echoing method, request headers, and the
                     parsed request body
* ``*    /deny``  -> ``401`` JSON ``{"error": "unauthorized", ...}``
* ``*    /boom``  -> ``500`` JSON ``{"error": "kaboom"}``
* ``*    /redirect`` -> ``302`` with ``Location: /text`` and a JSON marker body
                        (used to prove the adapter does NOT follow redirects)
* ``*    /evidence`` -> ``200`` ``{response, evidence: {coverage, events}}``
* ``*    /evidence-malformed`` -> ``200`` with a structurally invalid ``evidence``
* ``*    /capture`` -> ``200`` ``{"answer": "ok"}`` and records the received
                       request headers on the server as ``last_request_headers``
                       (lower-cased). The response body does NOT echo them, so
                       secret-leak tests can assert a token was *sent* without
                       the token ever appearing in a response.
* ``*    /reflect-body``   -> ``200`` JSON that echoes the request
                             ``Authorization`` header value into the body
* ``*    /reflect-header`` -> ``200`` ``{"answer":"ok"}`` plus a response header
                             ``X-Echoed-Auth`` carrying the request auth value
* ``*    /reflect-error``  -> ``401`` JSON that echoes the request auth value
                             (exercises the HTTPError normalization path)
* ``*    /slow``  -> sleeps 1.0s, then ``200`` (used only for timeout tests;
                     the timeout fires long before the sleep completes)
* anything else   -> ``404`` JSON
"""

from __future__ import annotations

import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

_SLOW_SECONDS = 1.0


class _Handler(BaseHTTPRequestHandler):
    # HTTP/1.0: the server closes the connection after each response, which
    # keeps the client side simple and avoids keep-alive lingering in tests.
    protocol_version = "HTTP/1.0"

    def log_message(self, *args: Any) -> None:  # noqa: D102 - silence test output
        return

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length > 0 else b""

    def _send(
        self,
        code: int,
        payload: Any,
        *,
        content_type: str = "application/json",
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        if isinstance(payload, (dict, list)):
            data = json.dumps(payload).encode("utf-8")
        elif isinstance(payload, str):
            data = payload.encode("utf-8")
        else:
            data = bytes(payload)
        try:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            for name, value in (extra_headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            # The client (deliberately) hung up first -- e.g. the timeout test.
            return

    def _dispatch(self, method: str) -> None:
        path = self.path.split("?", 1)[0]
        raw = self._read_body()
        try:
            parsed = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            parsed = None

        if path == "/text":
            self._send(
                200, "hello world", content_type="text/plain; charset=utf-8"
            )
        elif path == "/echo":
            self._send(
                200,
                {
                    "method": method,
                    "path": path,
                    "headers": {k.lower(): v for k, v in self.headers.items()},
                    "received": parsed,
                    "raw": raw.decode("utf-8", "replace"),
                },
            )
        elif path == "/deny":
            self._send(401, {"error": "unauthorized", "detail": "missing token"})
        elif path == "/boom":
            self._send(500, {"error": "kaboom"})
        elif path == "/evidence":
            # Portable evidence shape: {response, evidence: {coverage, events}}.
            # Events deliberately omit 'timestamp' (it is optional).
            self._send(
                200,
                {
                    "response": "I am not authorized to provide that information.",
                    "evidence": {
                        "coverage": ["authorization", "tool", "response"],
                        "events": [
                            {
                                "event_id": "evt-1",
                                "event_type": "authorization.decision",
                                "source": "demo-agent",
                                "attributes": {
                                    "decision": "deny",
                                    "permission": "payroll.read",
                                },
                            },
                            {
                                "event_id": "evt-2",
                                "event_type": "response.generated",
                                "source": "demo-agent",
                                "attributes": {},
                            },
                        ],
                    },
                },
            )
        elif path == "/evidence-malformed":
            self._send(
                200,
                {"response": "ok", "evidence": {"events": "not-a-list"}},
            )
        elif path == "/capture":
            # record what the client sent; do NOT echo it back in the body
            self.server.last_request_headers = {  # type: ignore[attr-defined]
                k.lower(): v for k, v in self.headers.items()
            }
            self._send(200, {"answer": "ok"})
        elif path == "/reflect-body":
            # a hostile/buggy target that reflects the credential into the body
            self._send(
                200,
                {"answer": "ok", "seen_authorization": self.headers.get("Authorization", "")},
            )
        elif path == "/reflect-header":
            self._send(
                200,
                {"answer": "ok"},
                extra_headers={"X-Echoed-Auth": self.headers.get("Authorization", "")},
            )
        elif path == "/reflect-error":
            self._send(
                401,
                {"error": "denied", "token_was": self.headers.get("Authorization", "")},
            )
        elif path == "/redirect":
            self._send(
                302,
                {"redirected": False, "note": "body of the 302 itself"},
                extra_headers={"Location": "/text"},
            )
        elif path == "/slow":
            time.sleep(_SLOW_SECONDS)
            self._send(200, {"slept_seconds": _SLOW_SECONDS})
        else:
            self._send(404, {"error": "not found", "path": path})

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

    def do_PUT(self) -> None:  # noqa: N802
        self._dispatch("PUT")

    def do_DELETE(self) -> None:  # noqa: N802
        self._dispatch("DELETE")


class _QuietThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request: Any, client_address: Any) -> None:
        # Client-side disconnects (timeout test) are expected; stay silent.
        return


class LocalHTTPServer:
    """Context manager running :class:`_Handler` on ``127.0.0.1`` in a thread."""

    def __init__(self) -> None:
        self._server = _QuietThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._thread = threading.Thread(
            target=lambda: self._server.serve_forever(poll_interval=0.05),
            name="local-http-fixture",
            daemon=True,
        )

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    @property
    def last_request_headers(self) -> dict[str, str]:
        """Lower-cased headers of the most recent request to ``/capture``."""
        return getattr(self._server, "last_request_headers", {})

    def __enter__(self) -> "LocalHTTPServer":
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


def unused_localhost_port() -> int:
    """Bind an ephemeral ``127.0.0.1`` port, release it, and return the number.

    A connection to the returned port is refused -- used to exercise the
    "connection refused -> ERROR" path deterministically without the Internet.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])
    finally:
        s.close()


__all__ = ["LocalHTTPServer", "unused_localhost_port"]
