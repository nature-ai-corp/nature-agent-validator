"""Scenario authoring & developer UX (Phase 6).

This package adds **no** runtime capability and **no** second scenario schema.
It is a thin authoring layer over the existing authoritative contract:

    authoring UX
        -> nature_agent_validator.scenario.serialization  (load / validate)
        -> nature_agent_validator.adapters.registry        (adapter config shape)
        -> nature_agent_validator.assertions               (assertion dispatch)

Three things a first-time developer needs:

* :func:`init_scenario_file` -- write one deterministic, minimal, valid HTTP
  starter scenario (never overwrites).
* :func:`check_scenario_file` -- statically validate a scenario file through the
  same loader the runner uses, plus the adapter/assertion config checks the
  runtime already knows -- with **no** network, adapter send, or secret
  resolution.
* :func:`describe_scenario` / :func:`describe_assertions` -- concise authoring
  reference text derived from the live schema and the live assertion registry.

The assertion catalog (:data:`ASSERTION_CATALOG`) is a small immutable metadata
table. It is not authoritative for *which* types exist -- that is
:func:`nature_agent_validator.assertions.known_assertion_types` -- and a test
(`tests/test_authoring.py`) fails if the two diverge.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nature_agent_validator.adapters import (
    NormalizedResult,
    available_adapter_names,
    build_adapter,
)
from nature_agent_validator.assertions import (
    AssertionContext,
    build_assertion,
    known_assertion_types,
)
from nature_agent_validator.errors import (
    AdapterError,
    NatureValidatorError,
    ScenarioError,
)
from nature_agent_validator.scenario.serialization import load_scenario

# --------------------------------------------------------------------------- #
# Assertion catalog (metadata only -- see module docstring / drift test)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class AssertionDoc:
    """One row of authoring documentation for a deterministic assertion type."""

    name: str
    #: ``"response"`` (visible behaviour) or ``"evidence"`` (internal behaviour).
    category: str
    summary: str
    #: The config keys that are *required* (the assertion errors without them).
    required_config: tuple[str, ...] = ()
    #: Config keys that are accepted but optional.
    optional_config: tuple[str, ...] = ()


ASSERTION_CATALOG: tuple[AssertionDoc, ...] = (
    AssertionDoc(
        "status_equals",
        "response",
        "Transport status (HTTP status code / process exit code) equals an "
        "expected integer.",
        ("value",),
    ),
    AssertionDoc(
        "equals",
        "response",
        "The whole response body -- or the value at a dotted path within it -- "
        "equals an expected value.",
        ("value",),
        ("path",),
    ),
    AssertionDoc(
        "contains",
        "response",
        "The response text contains a substring.",
        ("value",),
    ),
    AssertionDoc(
        "not_contains",
        "response",
        "The response text does not contain a (forbidden) substring.",
        ("value",),
    ),
    AssertionDoc(
        "regex_match",
        "response",
        "The response text matches a regular expression (re.search).",
        ("pattern",),
    ),
    AssertionDoc(
        "json_path_equals",
        "response",
        "The value at a dotted path in the parsed JSON body equals an expected "
        "value. Integer segments index lists.",
        ("path", "value"),
    ),
    AssertionDoc(
        "latency_below",
        "response",
        "The measured latency is within a millisecond budget.",
        ("max_ms",),
    ),
    AssertionDoc(
        "evidence_event_exists",
        "evidence",
        "A matching evidence event was observed -- event type plus an optional "
        "exact attribute-subset match.",
        ("event_type",),
        ("attributes",),
    ),
    AssertionDoc(
        "evidence_event_not_exists",
        "evidence",
        "No matching evidence event was observed. PASSes on absence only within "
        "declared coverage -- never on missing evidence alone.",
        ("event_type",),
        ("attributes",),
    ),
)

_EVIDENCE_PRINCIPLE = (
    "Absence of evidence is not evidence of absence."
)


def catalog_assertion_names() -> tuple[str, ...]:
    """The assertion type names the catalog documents, sorted."""
    return tuple(sorted(doc.name for doc in ASSERTION_CATALOG))


# --------------------------------------------------------------------------- #
# init
# --------------------------------------------------------------------------- #

#: A localhost placeholder -- structurally valid, not expected to answer.
_STARTER_URL = "http://127.0.0.1:8080/agent"


def _identifiers_from_path(path: Path) -> tuple[str, str]:
    """Derive ``(scenario_id, name)`` from a file name. Introduces **no** new
    identifier rules -- ``scenario_id`` accepts any string -- it is only a
    convenience default the author can edit."""
    stem = path.stem.strip()
    scenario_id = stem or "scenario"
    words = [w for w in re.split(r"[-_\s]+", stem) if w]
    name = " ".join(w[:1].upper() + w[1:] for w in words) if words else "Scenario"
    return scenario_id, name


def build_starter_scenario(path: Path) -> dict[str, Any]:
    """The canonical starter :class:`Scenario` as a plain dict, ready to be
    serialized with :func:`nature_agent_validator.scenario.serialization`'s
    field vocabulary. Deterministic: no timestamp, host, user, UUID, or
    environment data; no credential/secret material of any kind."""
    scenario_id, name = _identifiers_from_path(path)
    return {
        "scenario_id": scenario_id,
        "name": name,
        "description": (
            "Starter HTTP scenario generated by `nav scenario init`. Point "
            "target.config.url at your agent's endpoint, then edit "
            "request.payload and the expectations to describe the behaviour "
            "you expect."
        ),
        "target": {
            "adapter": "http",
            "config": {
                "url": _STARTER_URL,
                "method": "POST",
                "timeout_seconds": 30,
            },
        },
        "request": {
            "payload": {"message": "Say hello."},
        },
        "expectations": [
            {
                "assertion_id": "status-ok",
                "type": "status_equals",
                "config": {"value": 200},
            },
            {
                "assertion_id": "responds",
                "type": "contains",
                "config": {"value": "hello"},
            },
        ],
        "metadata": {},
    }


def render_starter_scenario(path: Path) -> str:
    """The starter scenario as a UTF-8 JSON document: 2-space indent, a single
    trailing newline, deterministic key order, no non-ASCII escaping."""
    body = build_starter_scenario(path)
    return json.dumps(body, indent=2, ensure_ascii=False) + "\n"


def init_scenario_file(path: str | Path) -> Path:
    """Write a starter scenario to ``path``.

    Never overwrites: an existing destination raises :class:`ScenarioError`
    (the caller maps this to exit code 2) and the file is left untouched. A
    missing parent directory or an unwritable path surfaces as :class:`OSError`.
    """
    p = Path(path)
    if p.exists():
        raise ScenarioError(f"refusing to overwrite existing file: {p}")
    payload = render_starter_scenario(p)
    try:
        # "x" fails if the file appears between the check above and here.
        with open(p, "x", encoding="utf-8", newline="\n") as fh:
            fh.write(payload)
    except FileExistsError:
        raise ScenarioError(
            f"refusing to overwrite existing file: {p}"
        ) from None
    return p


# --------------------------------------------------------------------------- #
# check  (static only -- no network, no adapter send, no secret resolution)
# --------------------------------------------------------------------------- #

#: A benign, fully static context. Assertion ``evaluate`` methods are pure
#: judgments over this shape (they perform no I/O), so running them against an
#: empty result surfaces missing/!mistyped config as ``AssertionConfigError``
#: without contacting anything. The PASS/FAIL verdict itself is discarded.
_STATIC_CHECK_CONTEXT = AssertionContext(result=NormalizedResult(), evidence=None)


def check_scenario_file(path: str | Path) -> list[str]:
    """Statically validate the scenario at ``path``. Returns a list of concise
    ``field.path: message`` diagnostics; an empty list means the scenario is
    structurally valid.

    Reuses the authoritative runtime path only:

    * :func:`load_scenario` -- JSON syntax, root shape, required fields, field
      types, identifier coercion;
    * :func:`build_adapter` -- the adapter name and its config shape (this
      constructs the adapter but never calls ``send`` and performs no I/O; for
      ``http`` it validates ``url`` / ``method`` / ``timeout_seconds`` /
      ``headers`` / ``evidence_field`` / ``secret_headers`` *references*, and
      resolves **no** secret);
    * :func:`build_assertion` + a static ``evaluate`` -- unknown assertion
      types and assertion-specific config errors.

    It performs no HTTP request, DNS lookup, socket connection, adapter send,
    agent execution, secret resolution, or ``os.environ`` credential lookup,
    and it neither modifies the scenario nor writes any file.
    """
    p = Path(path)
    try:
        scenario = load_scenario(p)
    except ScenarioError as exc:
        return [str(exc)]

    diagnostics: list[str] = []

    try:
        build_adapter(scenario.target)
    except AdapterError as exc:
        diagnostics.append(f"target: {exc}")
    except NatureValidatorError as exc:  # defensive -- keep it a diagnostic
        diagnostics.append(f"target: {exc}")

    known_types = known_assertion_types()
    known = ", ".join(known_types)
    for index, spec in enumerate(scenario.expectations):
        where = f"expectations[{index}]"
        try:
            assertion = build_assertion(spec)
        except NatureValidatorError as exc:
            # UnknownAssertionType (and any config error build_assertion raises)
            if not spec.type:
                diagnostics.append(f"{where}.type: assertion 'type' is required")
            elif spec.type not in known_types:
                diagnostics.append(
                    f"{where}.type: unknown assertion type {spec.type!r} "
                    f"(known: {known})"
                )
            else:
                diagnostics.append(f"{where}: {exc}")
            continue
        try:
            assertion.evaluate(_STATIC_CHECK_CONTEXT)
        except NatureValidatorError as exc:
            diagnostics.append(f"{where} ({spec.type}): {exc}")

    return diagnostics


# --------------------------------------------------------------------------- #
# describe
# --------------------------------------------------------------------------- #


def describe_scenario() -> str:
    """Concise authoring overview of the Scenario structure -- derived from the
    live schema (fields) and the live adapter registry (adapter names)."""
    adapters = " / ".join(available_adapter_names())
    return f"""\
NATURE Agent Validator -- Scenario authoring
============================================

A Scenario is a portable, serializable (JSON) description of one validation:
what to send to which target, and what behaviour is expected. It carries no
execution logic. The same Scenario runs unchanged against a black-box target
and an evidence-enabled one.

Top-level fields
----------------
  scenario_id    required. Stable identifier, echoed into the result.
  name           required. Human-readable title.
  description     optional. Free text (default "").
  target         required. {{ "adapter": <name>, "config": {{ ... }} }}
  request        optional. {{ "payload": <any>, "attributes": {{ ... }} }}
                 payload is the body the adapter sends; attributes are
                 transport-agnostic hints.
  expectations   optional. A list of assertion specs, each:
                   {{ "assertion_id": <str>, "type": <str>, "config": {{ ... }} }}
  metadata       optional. Free-form grouping object (suite, tags, ...).

Target adapters
---------------
  {adapters}
    http    - send one real HTTP request. config.url is required and must be
              http:// or https://; optional config.method (default POST with a
              body, else GET), config.headers, config.timeout_seconds (30),
              config.evidence_field.
    static  - return a canned response, no I/O (tests / examples / demos).

Authoring workflow
------------------
  1. nav scenario init  my-scenario.json      generate a starter file
  2. nav scenario check my-scenario.json      static validation, no agent call
  3. edit target.config.url / request / expectations
  4. nav validate my-scenario.json            run it against the agent

  nav scenario describe assertions             list the deterministic checks

Runtime environment (separate)
------------------------------
Runtime connection overrides -- exact url, extra headers, and secret-header
references -- are NOT part of the Scenario. They live in a separate
EnvironmentConfig file supplied via `nav validate --environment FILE`
(also on `nav validate-suite`). Secret values come only from process
environment variables, resolved at request time; never store credentials in
a Scenario.
"""


def describe_assertions() -> str:
    """Concise catalog of the deterministic assertions, split into response
    (visible behaviour) and evidence (internal behaviour) checks. The set of
    types is taken from the live registry; a drift test keeps this in sync."""
    registry_types = set(known_assertion_types())
    documented = {doc.name for doc in ASSERTION_CATALOG}
    # Defensive: if something is registered but undocumented, still list it so
    # the output can never silently hide a supported type.
    extra = sorted(registry_types - documented)

    def _row(doc: AssertionDoc) -> str:
        req = ", ".join(doc.required_config) if doc.required_config else "(none)"
        opt = (
            f"   optional config: {', '.join(doc.optional_config)}\n"
            if doc.optional_config
            else ""
        )
        return (
            f"  {doc.name}\n"
            f"   {doc.summary}\n"
            f"   required config: {req}\n"
            f"{opt}"
        )

    response = [d for d in ASSERTION_CATALOG if d.category == "response"]
    evidence = [d for d in ASSERTION_CATALOG if d.category == "evidence"]

    parts = [
        "NATURE Agent Validator -- deterministic assertion catalog",
        "========================================================",
        "",
        "Each expectation is { assertion_id, type, config }. Every assertion "
        "returns",
        "PASS, FAIL, or SKIPPED -- a SKIPPED assertion never makes a scenario "
        "FAIL.",
        "",
        "A. Response / behaviour assertions (visible behaviour)",
        "-----------------------------------------------------",
    ]
    parts.extend(_row(d) for d in response)
    parts.extend(
        [
            "B. Evidence assertions (internal behaviour, optional)",
            "----------------------------------------------------",
            f"  {_EVIDENCE_PRINCIPLE}",
            "",
            "  Evidence assertions are SKIPPED (never FAIL, never PASS) when:",
            "    - the target exposed no evidence (black-box), or",
            "    - the event type's namespace is not in the record's declared",
            "      coverage (namespace = the part before the first '.').",
            "  Within declared coverage: evidence_event_exists PASSes on a",
            "  match, evidence_event_not_exists PASSes only on a true absence.",
            "  Missing evidence never PASSes a negative assertion.",
            "",
        ]
    )
    parts.extend(_row(d) for d in evidence)

    if extra:
        parts.append("Registered but undocumented (please report):")
        parts.extend(f"  {name}" for name in extra)
        parts.append("")

    return "\n".join(parts).rstrip("\n") + "\n"


__all__ = [
    "AssertionDoc",
    "ASSERTION_CATALOG",
    "catalog_assertion_names",
    "build_starter_scenario",
    "render_starter_scenario",
    "init_scenario_file",
    "check_scenario_file",
    "describe_scenario",
    "describe_assertions",
]
