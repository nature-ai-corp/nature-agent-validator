# Architecture

Phase 0 defines component **boundaries** and a minimal working implementation
of each. The guiding rule: keep the surface small and extensible, and never
let a model, the network, or a container become a core requirement.

## Component map

```
                 +-------------------+
   scenario  --> |      Runner       | --> ValidationResult
   (+ adapter)   |                   |
                 |  1. resolve adapter
                 |  2. adapter.send(request) -> NormalizedResult (+ EvidenceRecord?)
                 |  3. build + evaluate each AssertionSpec over an AssertionContext
                 |  4. fold outcomes -> overall_status
                 +-------------------+
```

Package dependency direction (no cycles):

```
errors        (leaf)
evidence      -> errors              (raises EvidenceError on malformed input)
scenario      (leaf; AssertionSpec referenced only for typing)
evaluators    (leaf; boundary only)
adapters      -> evidence, scenario  (adapters.http -> urllib, imported lazily only)
assertions    -> evidence            (adapters referenced only for typing)
reporting     -> assertions, evidence
runner        -> adapters, assertions, scenario, reporting, evidence
suite         -> runner, scenario, scenario.serialization, reporting, errors   (Phase 3)
cli           -> runner, suite, scenario.serialization, adapters.registry
```

## Scenario  (`scenario/`)

A portable, serializable description of one validation. It carries no
execution logic and no NATURE-specific fields.

| Field | Meaning |
| --- | --- |
| `scenario_id` | stable identifier |
| `name`, `description` | human context |
| `target` | `ScenarioTarget(adapter, config)` — which adapter to use and how to configure it |
| `request` | `ScenarioRequest(payload, attributes)` — transport-agnostic; `payload` is adapter-interpreted, `attributes` carries hints (HTTP method/path, a role to impersonate, ...) |
| `expectations` | tuple of `AssertionSpec` |
| `metadata` | free-form grouping (`suite`, tags, ...) |

Domain objects are frozen dataclasses; mapping fields are exposed read-only.
JSON (de)serialization lives in `scenario/serialization.py`. YAML is
deliberately deferred (it needs a third-party parser, pending OSS review).

## Adapter  (`adapters/`)

The **only** component that knows how to reach a target.

- `TargetAdapter` (ABC): `send(request) -> AdapterResponse`, optional
  `close()`, optional `from_config(config)` for declarative construction.
- `AdapterResponse`: `result: NormalizedResult` + `evidence: EvidenceRecord | None`.
- `NormalizedResult`: `status`, `body`, `text`, `headers`, `latency_ms`,
  `error`, `raw`. Assertions only ever see this shape, never a transport
  object.
- `StaticAdapter` (`static`): returns a canned response, no I/O. Reference
  implementation; powers the Phase 0 examples, tests, and CLI.
- `HttpAdapter` (`http`, Phase 1): sends one real HTTP request with the
  standard library (`urllib.request` / `urllib.error`) and normalizes the
  response. Config: `url` (required, `http`/`https` only), `method` (defaults
  to `POST` with a body, else `GET`), `headers` (static), `timeout_seconds`
  (default `30`), `evidence_field` (optional, Phase 2 — a top-level JSON
  response key parsed as `{coverage, events}`). The body is `request.payload` —
  string/bytes sent as-is, anything else JSON-encoded with an added
  `Content-Type: application/json` when absent. A completed exchange,
  **including 3xx/4xx/5xx**, becomes a `NormalizedResult`; a transport failure
  (connection refused, DNS, timeout, malformed URL, unsupported scheme) raises
  `AdapterError` → `ERROR`. **Redirects are not followed** (Phase 1): a `3xx`
  is normalized like any response, `Location` kept in `NormalizedResult.headers`;
  configurable redirect support is a later decision. Evidence: `None` unless
  `evidence_field` is set and present in the JSON body; malformed → `AdapterError`.
- `registry.py`: a private table mapping an adapter name to a
  declaratively-constructible class, plus the `build_adapter(target)` factory
  used by the runner and CLI. `static` is in the eager table; `http` is
  resolved through a lazy loader so that importing the core package pulls in
  no networking module. Unknown names raise `AdapterError` (surfaced as
  `ERROR`, not a failed assertion). There is **no** public
  adapter-registration API.

`HttpAdapter` is intentionally **not** re-exported from
`nature_agent_validator.adapters` / the top-level package (that would import
`urllib` at core-import time); use
`from nature_agent_validator.adapters.http import HttpAdapter`.

Planned future adapters — CLI, local Python callable, WebSocket, MCP, other
agent systems — implement the same interface with no runner change. The runner
stays transport-agnostic: it never imports `http`/`urllib` and has no HTTP
branch.

## Assertion  (`assertions/`)

A deterministic judgment over an `AssertionContext` (the `NormalizedResult`
plus optional `EvidenceRecord`). Assertions never perform I/O.

- `AssertionSpec` (data): `assertion_id`, `type`, `config`.
- `Assertion` (ABC): class var `type`, `evaluate(context) -> AssertionResult`.
  Built from a spec via `build_assertion(spec)`. Ordinary failure returns a
  `FAIL` result; only malformed configuration raises (`AssertionConfigError`).
- `AssertionResult`: `assertion_id`, `type`, `outcome`, `expected`,
  `observed`, `message`. `outcome` (`PASS` / `FAIL` / `SKIPPED`) is the
  authoritative state. `passed` is a derived convenience and is **tri-state**:
  `PASS -> True`, `FAIL -> False`, `SKIPPED -> None` (serialized as JSON
  `null`). `SKIPPED` never behaves or serializes as a failure.
- `registry.py`: a private type table populated by `assertions/builtin.py`
  through a module-internal decorator, plus the `build_assertion(spec)`
  factory. `UnknownAssertionType` for an unregistered `type`. Phase 0 exposes
  **no** public assertion-registration API.

Phase 0 ships this subset (all standard-library):

| Type | Checks |
| --- | --- |
| `status_equals` | transport status equals a value |
| `equals` | body — or a dotted path within it — equals a value |
| `contains` / `not_contains` | response text contains / does not contain a substring |
| `regex_match` | response text matches a regular expression |
| `json_path_equals` | value at a dotted body path equals a value |
| `latency_below` | measured latency within a millisecond budget |
| `evidence_event_exists` / `evidence_event_not_exists` | a matching evidence event (type + optional exact attribute subset) was / was not observed — **coverage-aware**, see below |

New built-in checks are added as `Assertion` subclasses in
`assertions/builtin.py`; the scenario format, runner, and result shape do not
change. A public registration API for third-party assertions is deferred to a
later phase.

### `SKIPPED`, coverage, and the negative-evidence rule (P0-3 / Phase 2)

Evidence assertions return `SKIPPED` (not `FAIL`) when they cannot be
evaluated. A skipped assertion never makes a scenario `FAIL`, and its `passed`
convenience is `None` (never `False`). This is what lets one scenario
definition run unchanged against a black-box target and an evidence-enabled
one.

Both `evidence_event_exists` and `evidence_event_not_exists` are `SKIPPED`
unless **(a)** an `EvidenceRecord` is present **and** **(b)** the event type's
namespace is in `record.coverage`. Namespace = the prefix of `event_type`
before the first `.` (`tool.executed` → `tool`; a dotless type is its own
namespace). Only then:

- `evidence_event_exists` → `PASS` if ≥1 matching event, else `FAIL`.
- `evidence_event_not_exists` → `PASS` only if 0 matching events, else `FAIL`.
  It never passes on absence alone — *no evidence of an action is not evidence
  the action did not happen*.

Attribute matching is an exact subset (`all(event.attributes[k] == v)` for the
given keys). No regex, no filter DSL. Coverage is never inferred from the
events present.

## Evidence Contract  (`evidence/`)

Deliberately **not** the full Agent Evidence SDK — the minimum the Validator
needs, kept small, generic, versioned, and optional.

- `EvidenceEvent`: `event_id`, `event_type`, `timestamp` (**optional**;
  `None` when the target did not stamp it; ISO-8601, a trailing `Z` accepted),
  `source`, `attributes`.
- `EvidenceRecord`: ordered `events` + `coverage` + `contract_version`
  (`EVIDENCE_CONTRACT_VERSION`, `0.1.0`), with helpers `covers(namespace)`,
  `event_types()`, `has_event_type()`, `of_type()`.
- `coverage` is an **open, string-based** tuple of evidence namespaces the
  target claims to cover (`authorization`, `tool`, `knowledge`, `workflow`,
  …). It is de-duplicated, order-preserving, and **never inferred** from the
  events present. It is what lets a negative assertion tell "observed and
  absent" from "not observable" (see the Assertion section).
- `evidence_namespace(event_type)` — the prefix before the first `.`.
- `KNOWN_EVENT_TYPES` is a **non-binding** vocabulary (`request.received`,
  `agent.selected`, `authorization.decision`, `model.invoked`,
  `skill.invoked`, `knowledge.accessed`, `tool.requested`, `tool.executed`,
  `workflow.transition`, `response.generated`). `event_type` and `coverage`
  namespaces stay open strings — no enterprise schema is frozen, no closed
  enum. Nothing in this package evaluates anything (P0-6).
- `from_dict` / `from_events` are **strict**: a non-object record, non-list
  `events`/`coverage`, non-string coverage entries, an event missing
  `event_id` / `event_type`, a non-object `attributes`, or an unparseable
  `timestamp` raise `EvidenceError`. Malformed optional evidence is surfaced
  (as `ERROR` via the runner), never silently downgraded to "no evidence".

### Trust boundary

Evidence is **observational input supplied by the target**. It is not
cryptographically verified, tamper-proof, independently attested, or
compliance-grade. The Validator judges the supplied evidence deterministically;
provenance/trust assurance is future scope.

### Evidence input path

The runner is evidence-source agnostic: an adapter returns
`AdapterResponse(result, evidence)` and the runner passes `evidence` straight
into the `AssertionContext`. It never knows how evidence was obtained.

- **StaticAdapter** — `config.evidence` accepts either the full
  `{coverage, events}` object or the legacy bare list of event dicts (no
  coverage).
- **HttpAdapter** — opt-in via `config.evidence_field`: a **top-level** JSON
  response key whose value is parsed as `{coverage, events}`. No JSONPath, no
  nested path DSL, no response-header transport, no vendor schema. Field
  absent / body not JSON ⇒ no evidence (black-box). Field present but
  structurally invalid ⇒ `AdapterError` ⇒ `ERROR`.

## Evaluator Provider  (`evaluators/`)

The **future** extension boundary for semantic evaluation. Phase 0 ships no
implementation and requires none.

- `EvaluationRequest`: `scenario_id`, `criterion`, `observed_text`, `context`.
- `EvaluationVerdict`: `passed`, `score`, `rationale`, `provider`.
- `EvaluatorProvider` (`runtime_checkable` Protocol): `name`,
  `evaluate(request) -> EvaluationVerdict`.

Future backends (a local evaluator, a DeepEval adapter, Claude, OpenAI,
DeepSeek, ...) would implement this. None may become a required core
dependency (P0-2). None are imported or integrated now.

## ValidationResult  (`reporting/`)

| Field | Meaning |
| --- | --- |
| `scenario_id`, `scenario_name` | which scenario produced this |
| `overall_status` | `PASS` / `FAIL` / `ERROR` |
| `assertion_results` | tuple of `AssertionResult` |
| `execution_metadata` | `adapter`, `started_at`, `finished_at`, `duration_ms` |
| `evidence_summary` | `available`, `event_count`, `event_types`, `coverage`, `contract_version` |
| `errors` | validator-side failure messages |

`to_dict()` produces a JSON-serializable structure — it includes a top-level
`counts` object (`{pass, fail, skipped}`) so a consumer sees at a glance that a
`PASS` may still contain `SKIPPED` assertions. `summary_line()` is a one-line
human summary (with `(N skipped)` when any); `counts()` the pass/fail/skipped
tally. The CLI human view additionally prints an `assertions:` count line and
an `evidence:` line (availability, event count, declared coverage).

### Outcome model

Statuses stay **`PASS` / `FAIL` / `ERROR`** only — no `PARTIAL` / `PASS_WITH_SKIPS`.

- **PASS** — every evaluated assertion passed. May contain `SKIPPED` assertions
  (they do not count against); the counts make that explicit.
- **FAIL** — at least one assertion was evaluated and failed. `FAIL` overrides
  any number of `SKIPPED`.
- **ERROR** — the Validator could not complete the run: the adapter could not
  be built, `adapter.send` raised, an assertion definition was broken (unknown
  type, malformed config), or supplied evidence was structurally malformed.

`ERROR` and assertion failure are never conflated. A `NormalizedResult` that
merely carries a transport `error` string is still a result: assertions judge
it (typically `FAIL`), and the run is not `ERROR`.

For the `http` adapter specifically: an HTTP `302` / `401` / `403` / `404` /
`500` is a completed exchange and therefore a **result** (assert
`status_equals: 302` or `status_equals: 500` and the run can `PASS`) — the
adapter does not follow redirects; connection refused, DNS failure, and read
timeout raise `AdapterError` from `adapter.send` and become **ERROR**.

## Runner  (`runner/`)

`Runner(adapter_factory=build_adapter)`; `run(scenario, adapter=None)` returns
a `ValidationResult`; `run_many(scenarios)` returns a list. The runner holds
no transport logic and no judgment logic. If `adapter` is passed in, the
caller owns its lifecycle; if the runner built it, the runner closes it.

## Scenario suite  (`suite/`, Phase 3)

Batch validation of many existing scenarios. Adds **no** new execution,
assertion, evidence, or status logic — `SuiteRunner` calls the single-scenario
`Runner` once per scenario.

- `ScenarioSuite(name, scenarios: tuple[Scenario, ...])` — an ordered,
  immutable collection. Nothing else: no tags, filters, templates, variables,
  inheritance, or profiles.
- `load_suite(path) -> ScenarioSuite` — discovers regular `*.json` files
  directly in a directory (**not** recursive), ordered lexically by file name,
  each parsed with the existing `load_scenario` deserializer. Raises
  `ScenarioError` when the path is not a directory, holds no `.json` file, or
  any file is malformed / structurally invalid — never silently skipped.
  Non-`.json` entries are ignored.
- `SuiteRunner(runner=Runner()).run(suite) -> SuiteResult` — sequential, in
  order, every scenario attempted (no parallelism, retry, or fail-fast).
- `SuiteResult(name, results: tuple[ValidationResult, ...])` — exposes
  `total`, `scenario_counts()` (`{pass, fail, error}`), `assertion_counts()`
  (`{pass, fail, skipped}` summed across scenarios), `overall_status`
  (`ERROR > FAIL > PASS`; a `PASS`-with-`SKIPPED` scenario stays `PASS`),
  `summary_lines()`, and `to_dict()`. `to_dict()` embeds each
  `ValidationResult.to_dict()` verbatim, in discovery order — one result
  schema, not two.

## CLI  (`cli/`)

`nav validate <file-or-dir> [--json]`. Loads `.json` scenario(s), runs them
via the `build_adapter` factory, prints a text summary or full JSON.

`nav validate-suite <directory> [--json]` (Phase 3). `load_suite → SuiteRunner
→ SuiteResult`, then a human summary (suite line + counts + one line per
scenario) or the suite JSON.

Exit codes, both commands: `0` overall PASS, `1` overall FAIL, `2` overall
ERROR **or** a load failure (missing path, non-directory suite, no `.json`
files, malformed/invalid scenario), `3` usage. No Phase-3 additions to this
set. Command naming is not frozen.

The CLI needed **no changes** for Phase 1: an `http` scenario runs through the
same `load_scenarios → Runner.run_many → build_adapter` path as a `static`
one. A directory run is non-recursive (`*.json`), so neither `examples/http/`
nor `examples/suite/` is picked up by `nav validate examples/`.
