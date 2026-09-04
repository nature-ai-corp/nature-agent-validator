# Examples

Runnable scenarios for the built-in `static` adapter, so they execute with
**no network access and no dependencies**.

```bash
# from the repo root, with the package installed (pip install -e .)
nav validate examples/
nav validate examples/sales_cannot_read_payroll.json --json
```

Or without installing:

```bash
PYTHONPATH=src python -m nature_agent_validator validate examples/
```

| File | Shows |
| --- | --- |
| `sales_cannot_read_payroll.json` | Evidence-enabled target: visible refusal **and** internal assertions are evaluated. Evidence declares `coverage: ["request","authorization","tool","response"]`, so `evidence_event_exists` (authorization deny) and `evidence_event_not_exists` (no `tool.executed` for `payroll.read`) both PASS. |
| `sales_cannot_read_payroll_blackbox.json` | Same scenario against a black-box target: the two evidence assertions report `SKIPPED` (not PASSED, not FAILED); the overall verdict is still `PASS`, and the report shows `2 skipped`. |

## HTTP target

[`http/`](http/) validates a **real localhost HTTP endpoint** with the generic
`http` adapter. It needs a demo server running, so it lives in its own
subdirectory and is not part of the network-free `nav validate examples/` run.
See [`http/README.md`](http/README.md).

## Scenario suite (Phase 3–4)

[`suite/`](suite/) is a batch of four `StaticAdapter` scenarios (normal PASS,
deterministic FAIL, black-box PASS with a `SKIPPED` evidence assertion, and an
evidence-enabled PASS). Run it with `nav validate-suite examples/suite`, or
emit a CI-portable JUnit report with `--junit` / `--junit-output FILE`. It is
a sub-directory, so `nav validate examples/` does not pick it up. See
[`suite/README.md`](suite/README.md).
