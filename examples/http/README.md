# HTTP target example

`generic_localhost.json` validates a **real HTTP endpoint** with the generic
`http` adapter. It is kept in this subdirectory (not in `examples/`) because it
needs a local server running — `nav validate examples/` must stay
network-free.

All traffic is localhost-only. No Internet access is required.

## Run it

Terminal 1 — start the demo endpoint (standard library only):

```bash
python examples/http/demo_server.py        # serves 127.0.0.1:8080
```

Terminal 2 — validate it:

```bash
nav validate examples/http/generic_localhost.json
nav validate examples/http/generic_localhost.json --json
```

Expected: `[PASS]` — status is `200`, the body contains `not authorized`, the
JSON `answer` field matches, and latency is within budget.

## What it shows

| Piece | Where |
| --- | --- |
| Target config | `target.adapter = "http"`, `target.config` = `url` / `method` / `headers` / `timeout_seconds` |
| Request body | `request.payload` — JSON-encoded, `Content-Type: application/json` added automatically |
| Status assertion | `status_equals` against the real HTTP status |
| Text assertions | `contains` / `not_contains` against the response body text |
| JSON assertion | `json_path_equals` against the parsed JSON body |
| Latency assertion | `latency_below` against the adapter-measured round trip |

## PASS vs FAIL vs ERROR here

* Stop `demo_server.py` and re-run → **ERROR** (connection refused is a
  transport failure, not an assertion failure).
* Change `status_equals` to `201` and re-run → **FAIL** (the endpoint
  responded fine; an expectation was not met).
* A `401` / `500` endpoint would still be a **result**: point the scenario at
  it and assert `status_equals: 401` for a **PASS**.
