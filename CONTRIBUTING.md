# Contributing to NATURE Agent Validator

Thanks for your interest. This project is in early **Alpha**: the surface is
small on purpose and the architecture has firm boundaries. Contributions that
respect those boundaries are very welcome.

## Before you start

- **Open an issue first** for anything beyond a small, obvious fix. Describe the
  problem or use case and the change you have in mind so scope can be agreed
  before you invest time.
- Keep pull requests focused. One logical change per PR.
- By contributing you agree that your contribution is licensed under the
  project's [Apache License 2.0](LICENSE). There is no separate CLA or DCO
  sign-off process at this time.

## Development setup

Requires Python 3.12, 3.13, or 3.14. No third-party packages are needed.

```bash
git clone https://github.com/nature-ai-corp/nature-agent-validator
cd nature-agent-validator

# run the CLI without installing
PYTHONPATH=src python -m nature_agent_validator validate examples/

# or install locally (editable)
pip install -e .
nav validate examples/
```

## Tests are required

Every change must keep the full suite green:

```bash
python3 -m unittest discover -s tests -t .
python3 -m compileall -q src tests
```

- Add focused tests for new behaviour or bug fixes. Optimise for covering the
  contract, not for raising the test count.
- Do not weaken or delete existing tests to make a change pass.

## Architecture rules (please preserve)

These are deliberate product boundaries, not preferences. See
[`docs/product-boundary.md`](docs/product-boundary.md) and
[`docs/architecture.md`](docs/architecture.md).

- **Deterministic-first core.** The core must run with no LLM, no evaluator
  model, no network, and no container runtime. Semantic evaluation may only
  ever plug in through the existing `EvaluatorProvider` boundary and must never
  become a required core dependency.
- **One engine, evidence optional.** Do not add a separate "internal mode".
  Evidence assertions report `SKIPPED` when evidence is unavailable or the
  relevant coverage namespace is not declared — *absence of evidence is not
  evidence of absence*.
- **Zero / minimal runtime dependencies.** The runtime depends on the Python
  standard library only. Do **not** add a runtime dependency. Do not add
  development or build dependencies without prior maintainer review.
- **Portable scenarios.** Keep the scenario format generic and serialisable;
  no coupling to any specific vendor system.
- Preserve existing result schemas, exit codes, and the PASS / FAIL / ERROR
  semantics unless a change is explicitly agreed.

## Third-party material and provenance

- Do not copy code, tests, fixtures, schemas, or documentation from other
  projects. Contributions must be your own work or carry a clearly stated,
  compatible license and provenance for review.
- Do not introduce any new OSS dependency (runtime, dev, or build) without a
  maintainer decision. Propose it in an issue with the package name, source
  repository, version, purpose, and why the standard library is insufficient.

## Never include

- Secrets, API keys, tokens, private keys, or credentials of any kind —
  including in tests and examples (use obvious placeholders / sentinels).
- Real customer, personal, or confidential data.
- Internal infrastructure details or non-public architecture.

## Review

All pull requests require maintainer review and a green test run before merge.
Maintainers may ask for changes to keep a contribution within the boundaries
above.
