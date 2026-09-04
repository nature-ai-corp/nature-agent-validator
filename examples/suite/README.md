# Example scenario suite (Phase 3–4)

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
nav validate-suite examples/suite                      # human summary
nav validate-suite examples/suite --json               # suite JSON to stdout
nav validate-suite examples/suite --junit              # JUnit XML to stdout (XML only)
nav validate-suite examples/suite --junit-output validation.xml   # JUnit XML to a file
```

This suite **intentionally contains one failing scenario**, so:

- suite `overall_status` = `FAIL` (no scenario ERRORed) → CLI exit code **1**
- scenario counts: 3 pass, 1 fail, 0 error
- assertion counts: 11 passed, 2 failed, 1 skipped

Remove `02_fail_static.json` and the suite is `PASS` (exit `0`).

### JUnit output for this suite

- one scenario → one `<testcase>` (4 total)
- `02_fail_static.json` → `<testcase><failure/></testcase>`
- no scenario ERRORed → `<testsuite errors="0">`; no `<error>` children
- `03_blackbox_skip.json` has a `SKIPPED` assertion, but its `<testcase>` has
  **no `<skipped>`** and `<testsuite skipped="0">` — assertion skip ≠ testcase skip
- `<testsuite failures="1" tests="4">`
- `--junit-output` also prints the normal human summary on stdout
- exit codes are unchanged: `0` PASS / `1` FAIL / `2` ERROR or a load /
  report-write failure

Exit codes: `0` = suite PASS, `1` = suite FAIL, `2` = suite ERROR **or** a
load error (path not a directory, no `.json` files, or a malformed / invalid
scenario file) **or** a JUnit report-write failure.
