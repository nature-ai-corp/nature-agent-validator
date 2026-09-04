# Changelog

All notable changes to NATURE Agent Validator are recorded here. Versions
follow [PEP 440](https://peps.python.org/pep-0440/); this project is in early
Alpha and the public surface may still change.

## 0.1.0a1 — initial public Alpha

First OSS Alpha of the standalone, no-model-first agent validation framework.
It answers one question: **did the Agent behave as expected?** The core is
deterministic — no LLM, no evaluator model, no network, no container runtime —
and it works against black-box targets, going deeper when a target exposes
structured evidence. *Absence of evidence is not evidence of absence.*

### Core validation foundation

- Portable, serialisable **Scenario** format (`target` + `request` +
  `expectations` + metadata) with JSON (de)serialisation.
- **Runner** that resolves an adapter, sends one request, evaluates every
  expectation, and folds the outcomes into a `ValidationResult`.
- Deterministic **assertions**: `status_equals`, `equals`, `contains`,
  `not_contains`, `regex_match`, `json_path_equals`, `latency_below`.
- Outcome model **PASS / FAIL / ERROR** with a tri-state assertion result
  (`PASS` / `FAIL` / `SKIPPED`); a validator-side failure is `ERROR`, never a
  failed assertion.
- `static` adapter (canned responses, no I/O) for tests, examples, and the CLI.
- `nav validate <file|dir>` CLI with human and `--json` output.

### Generic HTTP validation

- `http` adapter using only the standard library (`urllib`); it is loaded
  lazily so importing the core pulls in no networking module.
- Completed exchanges — including 3xx/4xx/5xx — become results; transport
  failures become `ERROR`. Redirects are not followed.

### Evidence-enabled validation

- Small, generic, versioned, **optional** Evidence Contract
  (`EvidenceEvent` / `EvidenceRecord`, `coverage`).
- Coverage-aware `evidence_event_exists` / `evidence_event_not_exists`: they
  report `SKIPPED` unless evidence is present and the event-type namespace is
  in declared coverage; a negative assertion never passes on missing evidence.
- `http` adapter can extract evidence from a configured top-level response
  field; malformed configured evidence is `ERROR`, never silently trusted.

### Scenario suite validation

- `ScenarioSuite` + `SuiteRunner` + `SuiteResult`: an ordered batch of existing
  scenarios run through the single-scenario engine unchanged.
- `nav validate-suite <dir>` with deterministic discovery and
  `ERROR > FAIL > PASS` aggregation.

### JUnit reporting

- `suite_result_to_junit_xml(...)` — one explicit, deterministic reporter
  (suite → `<testsuite>`, scenario → `<testcase>`), emitted via
  `nav validate-suite --junit` / `--junit-output FILE`.
- Redacted by design: no headers, credentials, raw bodies, or raw evidence
  payloads; assertion-level `SKIPPED` is never a JUnit skip.

### Environment / secret-safe configuration

- `EnvironmentConfig` + `--environment FILE` (on `validate` and
  `validate-suite`): runtime HTTP connection overrides only (exact `url`,
  `timeout`, header overlay, secret-header **references**) — never a change to
  validation intent.
- Secret **references, not values**: a header value is read from
  `os.environ` immediately before the request and never written to a scenario,
  result, report, or error. An unset/empty variable fails closed with `ERROR`.
  A reflected secret in a target response fails closed before it can enter a
  result.

### Scenario authoring developer UX

- `nav scenario init FILE` — generate a deterministic, minimal, valid HTTP
  starter scenario (never overwrites; no credential/secret material).
- `nav scenario check FILE` — static validation through the same loader the
  runner uses, plus adapter/assertion config checks; **no** network, adapter
  send, or secret resolution. Exit `0` valid / `2` invalid.
- `nav scenario describe` / `nav scenario describe assertions` — authoring
  overview and the deterministic assertion catalog, derived from the live
  schema and registry (guarded against drift).

### OSS Alpha packaging / governance foundation

- Apache-2.0 `LICENSE` and NATURE-only `NOTICE`.
- PEP 639 license metadata (`license = "Apache-2.0"`, bundled `license-files`);
  `setuptools.build_meta` backend retained (`setuptools>=77`).
- Single authoritative version constant
  (`nature_agent_validator.__version__`), sourced into packaging via
  setuptools' dynamic `attr` mechanism; `nav --version` reports `nav 0.1.0a1`.
- `SECURITY.md`, `CONTRIBUTING.md`, and this changelog.
- Zero runtime dependencies; standard-library-only test suite.
- GitHub Actions CI on Python 3.12 / 3.13 / 3.14: full test suite,
  `compileall`, and an installed metadata/version consistency check.
- Package-build verification: sdist + wheel build, distribution-metadata and
  bundled-license checks, and a clean-room install of the wheel with CLI
  smoke checks.
- Release-preparation artifacts, each independently verified with the standard
  library: an SPDX JSON SBOM of the built distribution, and a `SHA256SUMS`
  manifest.
- `docs/release-tooling.md` records the CI/release tooling provenance
  (Apache-2.0 `sbom4python`, and the SPDX License List / CC-BY-3.0 attribution).
