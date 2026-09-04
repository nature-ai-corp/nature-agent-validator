# Environment configs (Phase 5)

An environment file supplies **runtime connection overrides only** for an HTTP
target. It never changes validation intent — the same scenario/suite runs
against any environment.

```bash
# run an HTTP scenario against the 'local' environment (no secrets)
nav validate examples/http/generic_localhost.json --environment examples/environments/local_http.json

# a suite against a remote environment, injecting a bearer token from the shell
export AGENT_TOKEN='...the real token...'
nav validate-suite examples/http --environment examples/environments/staging.json --junit-output validation.xml
```

| File | Shows |
| --- | --- |
| `local_http.json` | exact `url` override + `timeout` + a normal `headers` entry, no secrets |
| `staging.json` | a `secret_headers` reference: header `Authorization` = `"Bearer "` + `os.environ["AGENT_TOKEN"]` |

## Rules

- **Format:** explicit JSON. Required: `name` (non-empty). Optional:
  `target.url`, `target.timeout`, `target.headers`, `target.secret_headers`.
  Any unknown root or target field is an **error** — never silently ignored.
- **`url`:** exact override only. No `base_url`, no joining, no `${VAR}`.
- **`timeout`:** number; reuses the Phase-1 HTTP timeout semantics.
- **`headers`:** overlaid on the scenario headers; the environment value wins
  for the same header name **case-insensitively** (no duplicate semantic
  headers).
- **`secret_headers`:** `{ "<Header>": { "env": "<VAR>", "prefix": "<literal>" } }`.
  `env` must match `[A-Za-z_][A-Za-z0-9_]*`. `prefix` defaults to `""`.
  Secret *references* only live in this file — never a value. The value is read
  from `os.environ` immediately before the request and is **never** written to
  a scenario, a result, JSON, JUnit, human output, or an error message. An
  unset or empty variable is a fail-closed **error** (the error names the
  variable, never a value).
- A `secret_headers`/normal-header collision (case-insensitive) is an
  **error** — the validator never silently picks one.
- Environment target overrides apply to **HTTP targets only**; applying them to
  a `static` scenario is an **error**.
- **No `--environment`** → exactly the pre-Phase-5 behavior; the scenario's own
  `url` / `headers` / `timeout` remain authoritative.
- No `.env` files, no dotenv, no cloud secret managers — secrets are injected
  by your shell / CI / container runtime through the process environment.
