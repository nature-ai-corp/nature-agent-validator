# HTTP target examples

Three scenarios validate a **real HTTP endpoint** with the generic `http`
adapter. They are kept in this subdirectory (not in `examples/`) because they
need a local server running — `nav validate examples/` must stay network-free.

| File | Shows |
| --- | --- |
| `generic_localhost.json` | Black-box: status / text / JSON / latency assertions only. |
| `evidence_localhost.json` | Evidence path: `target.config.evidence_field = "evidence"` parses `{coverage, events}` from the JSON body; asserts `evidence_event_exists` (authorization deny) and `evidence_event_not_exists` (no `payroll.read` tool). |
| `http_status_error.json` | A `403` response is a **result**, not a transport error: `status_equals: 403` plus a `json_path_equals` check on the JSON error body — and the scenario still PASSes. |

All traffic is localhost-only. No Internet access is required.

## Run it

Terminal 1 — start the demo endpoint (standard library only):

```bash
python examples/http/demo_server.py        # serves 127.0.0.1:8080 (/agent, /agent-evidence, /deny)
```

Terminal 2 — validate it:

```bash
nav validate examples/http/generic_localhost.json
nav validate examples/http/evidence_localhost.json --json
nav validate examples/http/http_status_error.json
```

Expected: `[PASS]` for all three. `evidence_localhost.json` additionally
reports `evidence: available -- 2 event(s); coverage: authorization, tool,
response`.

## What it shows

| Piece | Where |
| --- | --- |
| Target config | `target.adapter = "http"`, `target.config` = `url` / `method` / `headers` / `timeout_seconds` / `evidence_field` |
| Request body | `request.payload` — JSON-encoded, `Content-Type: application/json` added automatically |
| Status assertion | `status_equals` against the real HTTP status |
| Text assertions | `contains` / `not_contains` against the response body text |
| JSON assertion | `json_path_equals` against the parsed JSON body |
| Latency assertion | `latency_below` against the adapter-measured round trip |
| Evidence assertions | `evidence_event_exists` / `evidence_event_not_exists` against `{coverage, events}` parsed from `evidence_field` |

## PASS vs FAIL vs ERROR here

* Stop `demo_server.py` and re-run → **ERROR** (connection refused is a
  transport failure, not an assertion failure).
* Change `status_equals` to `201` and re-run → **FAIL** (the endpoint
  responded fine; an expectation was not met).
* A `401` / `403` / `500` endpoint is still a **result**: `http_status_error.json`
  points at `/deny` (`403`) and asserts `status_equals: 403` for a **PASS**.
* Point `evidence_localhost.json` at `/agent` (no `evidence` key in the body) →
  the two evidence assertions become **SKIPPED**, overall still **PASS**.
* Corrupt the `evidence` block the server returns → **ERROR** (malformed
  evidence is never silently trusted).
