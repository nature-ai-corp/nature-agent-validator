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
evidence      (leaf)
scenario      (leaf; AssertionSpec referenced only for typing)
evaluators    (leaf; boundary only)
adapters      -> evidence, scenario
assertions    -> evidence            (adapters referenced only for typing)
reporting     -> assertions, evidence
runner        -> adapters, assertions, scenario, reporting, evidence
cli           -> runner, scenario.serialization, adapters.registry
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
- `StaticAdapter` (Phase 0): returns a canned response, no I/O. Reference
  implementation; powers examples, tests, and the CLI.
- `registry.py`: a private table mapping an adapter name to a
  declaratively-constructible class, plus the `build_adapter(target)` factory
  used by the runner and CLI. Only `static` is present in Phase 0; unknown
  names raise `AdapterError` (surfaced as `ERROR`, not a failed assertion).
  There is **no** public adapter-registration API in Phase 0.

Planned future adapters — HTTP (first), CLI, local Python callable, WebSocket,
MCP, other agent systems — implement the same interface with no runner change.

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
| `evidence_event_present` / `evidence_event_absent` | an evidence event of a type (with an optional attribute subset) was / was not observed |

In Phase 0 new built-in checks are added as `Assertion` subclasses in
`assertions/builtin.py`; the scenario format, runner, and result shape do not
change. A public registration API for third-party assertions is deferred to a
later phase.

### `SKIPPED` and principle P0-3

Evidence assertions return `SKIPPED` (not `FAIL`) when no evidence is
available. A skipped assertion never makes a scenario `FAIL`, and its `passed`
convenience is `None` (never `False`). This is what lets one scenario
definition run unchanged against both a black-box target and an
evidence-enabled one.

## Evidence Contract  (`evidence/`)

Deliberately **not** the full Agent Evidence SDK — the minimum the Validator
needs, kept small, generic, versioned, and optional.

- `EvidenceEvent`: `event_id`, `event_type`, `timestamp`, `source`,
  `attributes`.
- `EvidenceRecord`: ordered `events` + `contract_version`
  (`EVIDENCE_CONTRACT_VERSION`, currently `0.1.0`), with helpers
  `event_types()`, `has_event_type()`, `of_type()`.
- `KNOWN_EVENT_TYPES` is a **non-binding** vocabulary (`request.received`,
  `agent.selected`, `authorization.decision`, `model.invoked`,
  `skill.invoked`, `knowledge.accessed`, `tool.requested`, `tool.executed`,
  `workflow.transition`, `response.generated`). No enterprise schema is
  frozen. Nothing in this package evaluates anything (P0-6).

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
| `evidence_summary` | `available`, `event_count`, `event_types`, `contract_version` |
| `errors` | validator-side failure messages |

`to_dict()` produces a JSON-serializable structure; `summary_line()` a one-line
human summary; `counts()` the pass/fail/skipped tally.

### Outcome model

- **PASS** — every evaluated assertion passed (`SKIPPED` do not count against).
- **FAIL** — at least one assertion was evaluated and failed.
- **ERROR** — the Validator could not complete the run: the adapter could not
  be built, `adapter.send` raised, or an assertion definition was broken
  (unknown type, malformed config).

`ERROR` and assertion failure are never conflated. A `NormalizedResult` that
merely carries a transport `error` string is still a result: assertions judge
it (typically `FAIL`), and the run is not `ERROR`.

## Runner  (`runner/`)

`Runner(adapter_factory=build_adapter)`; `run(scenario, adapter=None)` returns
a `ValidationResult`; `run_many(scenarios)` returns a list. The runner holds
no transport logic and no judgment logic. If `adapter` is passed in, the
caller owns its lifecycle; if the runner built it, the runner closes it.

## CLI  (`cli/`)

`nav validate <file-or-dir> [--json]`. Loads `.json` scenario(s), runs them
via the `build_adapter` factory, prints a text summary or full JSON. Exit
codes: `0` all passed, `1` some failed, `2` some errored / load failure, `3`
usage. Command naming is not frozen.
