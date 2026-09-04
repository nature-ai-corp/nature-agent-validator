"""``nav`` entry point.

Exit codes (shared by ``validate`` and ``validate-suite``):

* ``0`` -- overall PASS (every scenario passed; SKIPPED assertions are fine)
* ``1`` -- overall FAIL (at least one scenario FAILed, none ERRORed)
* ``2`` -- overall ERROR: at least one scenario ERRORed, the input could
           not be loaded (missing path, non-directory suite, malformed or
           invalid ``.json`` scenario), or a JUnit report file could not be
           written
* ``3`` -- usage error (argparse also exits ``2`` for conflicting flags)

``validate-suite`` output modes are mutually exclusive: default human summary,
``--json`` (JSON to stdout), ``--junit`` (JUnit XML **only** to stdout), or
``--junit-output FILE`` (JUnit XML to ``FILE`` as UTF-8, human summary still
on stdout). A successful JUnit export never changes the suite exit code; a
write failure forces exit ``2``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from nature_agent_validator import __version__
from nature_agent_validator.errors import NatureValidatorError
from nature_agent_validator.reporting import OverallStatus
from nature_agent_validator.reporting.junit import suite_result_to_junit_xml
from nature_agent_validator.runner import Runner
from nature_agent_validator.scenario.serialization import load_scenarios
from nature_agent_validator.suite import SuiteRunner, load_suite

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

    suite = sub.add_parser(
        "validate-suite",
        help="run every .json scenario in a directory as one suite (Phase 3)",
    )
    suite.add_argument(
        "path", help="path to a directory of .json scenario files (not recursive)"
    )
    # One machine-output mode at a time (argparse rejects conflicts, exit 2).
    suite_out = suite.add_mutually_exclusive_group()
    suite_out.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="emit the full suite result as JSON to stdout",
    )
    suite_out.add_argument(
        "--junit",
        action="store_true",
        help="emit a JUnit XML report (only XML) to stdout",
    )
    suite_out.add_argument(
        "--junit-output",
        metavar="FILE",
        dest="junit_output",
        help="write a JUnit XML report to FILE (UTF-8); human summary still on stdout",
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


def _exit_code_for(status: OverallStatus) -> int:
    if status is OverallStatus.ERROR:
        return EXIT_ERROR
    if status is OverallStatus.FAIL:
        return EXIT_FAIL
    return EXIT_OK


def _run_suite(args: argparse.Namespace) -> int:
    try:
        suite = load_suite(args.path)
    except NatureValidatorError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    result = SuiteRunner().run(suite)

    if args.junit:
        # stdout carries XML and nothing else
        xml = suite_result_to_junit_xml(result)
        sys.stdout.write(xml if xml.endswith("\n") else xml + "\n")
    elif args.junit_output:
        xml = suite_result_to_junit_xml(result)
        try:
            Path(args.junit_output).write_text(xml, encoding="utf-8")
        except OSError as exc:
            print(
                f"error: could not write JUnit report to {args.junit_output!r}: {exc}",
                file=sys.stderr,
            )
            return EXIT_ERROR  # a report-write failure never returns success
        for line in result.summary_lines():
            print(line)
    elif args.as_json:
        json.dump(result.to_dict(), sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
    else:
        for line in result.summary_lines():
            print(line)

    return _exit_code_for(result.overall_status)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "validate":
        return _run_validate(args)
    if args.command == "validate-suite":
        return _run_suite(args)
    parser.error(f"unknown command {args.command!r}")  # pragma: no cover
    return EXIT_USAGE  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
