# Example scenario suite (Phase 3)

Four portable `StaticAdapter` scenarios — no network, fully deterministic.
`nav validate-suite` runs every `*.json` file in this directory, in lexical
order, as one batch.

| File | Demonstrates | Scenario status |
| --- | --- | --- |
| `01_pass_static.json` | normal PASS (status + text + latency) | PASS |
| `02_fail_static.json` | deterministic FAIL (forbidden `$` present) | FAIL |
| `03_blackbox_skip.json` | black-box target → evidence assertion `SKIPPED`, scenario still PASS | PASS (1 skipped) |
| `04_evidence_pass.json` | evidence-enabled: `evidence_event_exists` + `evidence_event_not_exists` both PASS under declared coverage | PASS |

```bash
nav validate-suite examples/suite
nav validate-suite examples/suite --json
```

This suite **intentionally contains one failing scenario**, so:

- suite `overall_status` = `FAIL` (no scenario ERRORed) → CLI exit code **1**
- scenario counts: 3 pass, 1 fail, 0 error
- assertion counts: 11 passed, 2 failed, 1 skipped

Remove `02_fail_static.json` and the suite is `PASS` (exit `0`).

Exit codes: `0` = suite PASS, `1` = suite FAIL, `2` = suite ERROR or a
load error (path not a directory, no `.json` files, or a malformed / invalid
scenario file).
