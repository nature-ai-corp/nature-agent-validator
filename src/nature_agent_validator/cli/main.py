"""``nav`` entry point.

Exit codes:

* ``0`` -- every scenario passed
* ``1`` -- at least one scenario FAILed (assertion failure)
* ``2`` -- at least one scenario ERRORed, or a scenario could not be loaded
* ``3`` -- usage error
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from nature_agent_validator import __version__
from nature_agent_validator.errors import NatureValidatorError
from nature_agent_validator.reporting import OverallStatus
from nature_agent_validator.runner import Runner
from nature_agent_validator.scenario.serialization import load_scenarios

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_ERROR = 2
EXIT_USAGE = 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nav",
        description="NATURE Agent Validator -- did the agent behave as expected?",
    )
    parser.add_argument(
        "--version", action="version", version=f"nav {__version__}"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser(
        "validate", help="run a scenario file or a directory of scenario files"
    )
    validate.add_argument(
        "path", help="path to a .json scenario file or a directory of them"
    )
    validate.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="emit the full results as JSON instead of a text summary",
    )
    return parser


def _run_validate(args: argparse.Namespace) -> int:
    try:
        scenarios = load_scenarios(args.path)
    except NatureValidatorError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    if not scenarios:
        print(f"error: no scenarios found at {args.path!r}", file=sys.stderr)
        return EXIT_ERROR

    runner = Runner()
    results = runner.run_many(scenarios)

    if args.as_json:
        json.dump(
            {"results": [r.to_dict() for r in results]},
            sys.stdout,
            indent=2,
            default=str,
        )
        sys.stdout.write("\n")
    else:
        for result in results:
            print(result.summary_line())
            c = result.counts()
            print(
                f"    assertions: {c['pass']} passed, {c['fail']} failed, "
                f"{c['skipped']} skipped"
            )
            es = result.evidence_summary
            if es.available:
                cov = ", ".join(es.coverage) if es.coverage else "(none declared)"
                print(
                    f"    evidence: available -- {es.event_count} event(s); "
                    f"coverage: {cov}"
                )
            else:
                print("    evidence: not available (black-box)")
            for ar in result.assertion_results:
                if ar.outcome.value != "PASS":
                    print(f"    - {ar.assertion_id} [{ar.outcome.value}] {ar.message}")
            for err in result.errors:
                print(f"    ! {err}")

    if any(r.overall_status is OverallStatus.ERROR for r in results):
        return EXIT_ERROR
    if any(r.overall_status is OverallStatus.FAIL for r in results):
        return EXIT_FAIL
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "validate":
        return _run_validate(args)
    parser.error(f"unknown command {args.command!r}")  # pragma: no cover
    return EXIT_USAGE  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
