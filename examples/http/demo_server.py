"""A minimal localhost demo endpoint for the generic HTTP adapter examples.

Standard library only. **Example-only** -- not part of the product. It binds to
127.0.0.1 and answers two routes:

    POST /agent           ->  200 { "answer": "I am not authorized ..." }
    POST /agent-evidence  ->  200 { "response": "...", "evidence": {coverage, events} }

The evidence shape is the minimal portable one the HTTP adapter understands
(a top-level JSON key holding ``{coverage, events}``). It is observational
input, not attested proof.

Run it in one terminal:

    python examples/http/demo_server.py            # serves on 127.0.0.1:8080

then in another terminal:

    nav validate examples/http/generic_localhost.json
    nav validate examples/http/evidence_localhost.json
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = "127.0.0.1"
PORT = 8080

_ANSWER = {"answer": "I am not authorized to provide that information."}

_EVIDENCE_ANSWER = {
    "response": "I am not authorized to provide that information.",
    "evidence": {
        "coverage": ["authorization", "tool", "response"],
        "events": [
            {
                "event_id": "evt-1",
                "event_type": "authorization.decision",
                "source": "demo-agent",
                "attributes": {"decision": "deny", "permission": "payroll.read"},
            },
            {
                "event_id": "evt-2",
                "event_type": "response.generated",
                "source": "demo-agent",
                "attributes": {},
            },
        ],
    },
}


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        length = int(self.headers.get("Content-Length") or 0)
        _ = self.rfile.read(length) if length else b""  # request body ignored
        path = self.path.split("?", 1)[0]
        payload = _EVIDENCE_ANSWER if path == "/agent-evidence" else _ANSWER
        data = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args: object) -> None:
        return


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), _Handler)
    print(f"demo endpoint on http://{HOST}:{PORT}/agent[-evidence]  (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
