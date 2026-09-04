# Examples

Runnable Phase 0 scenarios. They use the built-in `static` adapter, so they
execute with **no network access and no dependencies**.

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
| `sales_cannot_read_payroll.json` | Evidence-enabled target: visible refusal **and** internal authorization/tool assertions are evaluated. |
| `sales_cannot_read_payroll_blackbox.json` | Same scenario against a black-box target: evidence assertions report `SKIPPED`, verdict is still `PASS`. |

## HTTP target

[`http/`](http/) validates a **real localhost HTTP endpoint** with the generic
`http` adapter. It needs a demo server running, so it lives in its own
subdirectory and is not part of the network-free `nav validate examples/` run.
See [`http/README.md`](http/README.md).
