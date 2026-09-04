# NATURE Agent Validator 0.1.0a1

**Alpha / pre-release.** APIs, the scenario format, and CLI command names may
change without notice. Not for production use.

NATURE Agent Validator answers one question — *did the Agent behave as
expected?* — with a deterministic core that needs no LLM, no evaluator model,
no network, and no container runtime.

## In this release

- **Deterministic agent validation** — portable JSON Scenarios, one Runner,
  and standard-library assertions (`status_equals`, `equals`, `contains` /
  `not_contains`, `regex_match`, `json_path_equals`, `latency_below`).
  Outcomes are `PASS` / `FAIL` / `ERROR`.
- **Generic HTTP validation** — the `http` adapter validates a real HTTP
  endpoint using only `urllib`; completed 3xx/4xx/5xx responses are results,
  transport failures are `ERROR`, redirects are not followed.
- **Optional evidence-enabled validation** — a small, versioned Evidence
  Contract with coverage-aware `evidence_event_exists` /
  `evidence_event_not_exists`. Absence of evidence is not evidence of
  absence: these report `SKIPPED` unless the relevant namespace is covered.
- **Scenario suite / batch validation** — `nav validate-suite` runs a
  directory of Scenarios through the same Runner, aggregating
  `ERROR > FAIL > PASS`.
- **JUnit reporting** — deterministic `--junit` / `--junit-output` for CI,
  with request/response content redacted.
- **Environment & secret-safe configuration** — `--environment` applies
  runtime HTTP connection overrides only; secrets are environment-variable
  *references*, resolved late, never written to a scenario, result, report,
  or error, and a reflected secret fails closed.
- **Scenario authoring CLI** — `nav scenario init` (deterministic starter,
  never overwrites), `nav scenario check` (static validation, no network, no
  secret resolution), `nav scenario describe` / `describe assertions`.

## Requirements & licensing

- **Zero runtime dependencies.** Python 3.12, 3.13, or 3.14.
- **Apache License 2.0.** Copyright 2026 NATURE AI CORP.

## Release artifacts

| File | Purpose |
| --- | --- |
| `nature_agent_validator-0.1.0a1-py3-none-any.whl` | Wheel |
| `nature_agent_validator-0.1.0a1.tar.gz` | Source distribution |
| `nature-agent-validator-0.1.0a1.spdx.json` | SPDX 2.3 JSON SBOM |
| `SHA256SUMS` | SHA-256 checksums for the three files above |

Build provenance and an SBOM attestation are recorded with GitHub Artifact
Attestations for every asset in this release; verify with
`gh attestation verify <file> --repo nature-ai-corp/nature-agent-validator`.

Not published to PyPI.
