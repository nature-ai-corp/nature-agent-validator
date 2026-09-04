# Product Boundary

This document fixes what NATURE Agent Validator **is**, what it **is not**, and
the principles the Phase 0 architecture is built to protect.

## What the Validator is

- A standalone **agent validation framework**. It answers: *"Did the Agent
  behave as expected?"*
- Usable against third-party AI agents, custom agents, API-based agents, local
  agents, future NATURE products, and future agent harnesses.
- Independently installable and usable, with no dependency on any other NATURE
  system.
- Deterministic at its core: a useful release validates a generic agent with
  no LLM evaluator involved.

## What the Validator is not

- **Not** part of the NATURE Enterprise AI Platform, and not a module of it.
- **Not** an agent runtime.
- **Not** an agent orchestration framework.
- **Not** an LLM provider.
- **Not** a training system.
- **Not** an observability backend.
- **Not** a commercial NATURE AI Assurance product.

## Standalone project boundary

- No code is copied from the NATURE Enterprise AI Platform or other
  proprietary internal architecture.
- This project is never wired into the Enterprise AI Platform codebase.
- No DeepSeek Harness integration, no external model integration, no
  production integration exists in Phase 0.
- The repository is intended for a future public OSS release; until OSS review,
  no third-party package is added and no license is claimed.

## Core principles

| ID | Principle | What it means in the architecture |
| --- | --- | --- |
| **P0-1** | No-model-first | The core runs with no OpenAI / Anthropic / DeepSeek / Qwen / Ollama / local LLM / evaluator model. Deterministic validation is the MVP foundation. |
| **P0-2** | Model optional | Semantic evaluators may later implement `EvaluatorProvider`. No evaluator model may become a required core dependency. |
| **P0-3** | Evidence optional | The Validator works against black-box systems. When structured evidence is available, validation depth increases. There is **one** engine, not an "internal mode" and an "external mode". Evidence assertions report `SKIPPED` when evidence is absent — and (Phase 2) when the relevant coverage namespace was not declared, so absence never yields a false negative-assertion PASS. |
| **P0-7** | Evidence is observational, not attested | Evidence is input supplied by the target. It is **not** cryptographically verified, tamper-proof, independently attested, or compliance-grade. The Validator judges the supplied evidence deterministically; structurally malformed evidence is `ERROR`, never silently trusted. Provenance/trust assurance is future scope. |
| **P0-4** | Portable scenarios | Scenario definitions do not depend on NATURE-specific systems. NATURE-specific evidence extensions may come later; the base scenario format stays generic. |
| **P0-5** | Deterministic assertions first | Status, schema/structure, required / forbidden text, latency, tool called / not called, authorization allowed / denied, expected agent selected, expected workflow result — all checkable without a model. |
| **P0-6** | Evidence is fact, Validator is judgment | Evidence records *what happened*. The Validator decides whether that satisfies expectations. The two responsibilities never mix: nothing in `evidence/` evaluates anything; nothing in `assertions/` performs I/O. |

## Non-goals for Phase 0

No database, Docker, Redis, PostgreSQL, web UI, server process, or background
workers. No plugin system before it is needed. Phase 0 stays small.

## Non-goals for Phase 3 (scenario suites)

A suite is only an ordered collection of existing scenarios. No tags,
filtering, templates, variables, inheritance, or environment profiles. No
parallel execution, retries, fail-fast, watch mode, or remote scenario
repositories. No historical result storage, HTML/JUnit reporting, or CI/CD
configuration. Suite execution reuses the single-scenario engine unchanged;
`ERROR`/`FAIL`/`PASS` keep their meaning.
