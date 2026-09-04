"""Deterministic assertion implementations shipped in Phase 0.

This is a minimal subset. Built-in checks are ``Assertion`` subclasses recorded
in the module-internal type table (``_register``); the runner, scenario format,
and result shape do not change when the set grows. Phase 0 does not expose a
public registration API.

Implemented types:

* ``status_equals``          -- transport status equals an expected value
* ``equals``                 -- body (or a path within it) equals a value
* ``contains``               -- response text contains a substring
* ``not_contains``           -- response text does not contain a substring
* ``regex_match``            -- response text matches a regular expression
* ``json_path_equals``       -- value at a dotted body path equals a value
* ``latency_below``              -- measured latency is within a millisecond budget
* ``evidence_event_exists``      -- an evidence event of a type (and optional
                                    exact attribute subset) was observed
* ``evidence_event_not_exists``  -- no such evidence event was observed

The two evidence assertions are *coverage-aware* (Phase 2): they are
``SKIPPED`` unless evidence is available **and** the event type's namespace is
in the record's declared coverage. Absence of an event never supports a
negative assertion PASS unless that namespace is covered.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from nature_agent_validator.errors import AssertionConfigError
from nature_agent_validator.evidence import evidence_namespace

from .base import Assertion
from .context import AssertionContext
from .registry import _register
from .result import AssertionResult

_MISSING = object()
_CLIP = 300


def _clip(value: Any) -> Any:
    text = value if isinstance(value, str) else repr(value)
    return text if len(text) <= _CLIP else text[:_CLIP] + "...(truncated)"


def _dig(obj: Any, path: str) -> Any:
    """Walk ``obj`` along a dotted path. Integer segments index sequences."""
    current = obj
    for part in path.split("."):
        if isinstance(current, Mapping) and part in current:
            current = current[part]
        elif isinstance(current, (list, tuple)):
            try:
                idx = int(part)
            except ValueError:
                return _MISSING
            if -len(current) <= idx < len(current):
                current = current[idx]
            else:
                return _MISSING
        else:
            return _MISSING
    return current


def _attrs_match(actual: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    return all(actual.get(k) == v for k, v in expected.items())


@_register
class StatusEqualsAssertion(Assertion):
    type = "status_equals"

    def evaluate(self, context: AssertionContext) -> AssertionResult:
        raw = self._require("value")
        try:
            expected = int(raw)
        except (TypeError, ValueError):
            raise AssertionConfigError(
                f"assertion {self.assertion_id!r}: 'value' must be an integer"
            ) from None
        observed = context.result.status
        if observed == expected:
            return self._pass(expected=expected, observed=observed)
        return self._fail(
            expected=expected,
            observed=observed,
            message=f"status {observed!r} != expected {expected!r}",
        )


@_register
class EqualsAssertion(Assertion):
    type = "equals"

    def evaluate(self, context: AssertionContext) -> AssertionResult:
        expected = self._require("value")
        path = self.config.get("path")
        if path:
            observed = _dig(context.result.body, str(path))
            if observed is _MISSING:
                return self._fail(
                    expected=expected,
                    observed=None,
                    message=f"path {path!r} not present in body",
                )
        else:
            observed = context.result.body
        if observed == expected:
            return self._pass(expected=expected, observed=_clip(observed))
        return self._fail(
            expected=expected,
            observed=_clip(observed),
            message="value does not equal expected",
        )


@_register
class ContainsAssertion(Assertion):
    type = "contains"

    def evaluate(self, context: AssertionContext) -> AssertionResult:
        needle = str(self._require("value"))
        haystack = context.result.text or ""
        if needle in haystack:
            return self._pass(
                expected=f"text contains {needle!r}", observed=_clip(haystack)
            )
        return self._fail(
            expected=f"text contains {needle!r}",
            observed=_clip(haystack),
            message=f"{needle!r} not found in response text",
        )


@_register
class NotContainsAssertion(Assertion):
    type = "not_contains"

    def evaluate(self, context: AssertionContext) -> AssertionResult:
        needle = str(self._require("value"))
        haystack = context.result.text or ""
        if needle not in haystack:
            return self._pass(
                expected=f"text does not contain {needle!r}",
                observed=_clip(haystack),
            )
        return self._fail(
            expected=f"text does not contain {needle!r}",
            observed=_clip(haystack),
            message=f"forbidden substring {needle!r} present in response text",
        )


@_register
class RegexMatchAssertion(Assertion):
    type = "regex_match"

    def evaluate(self, context: AssertionContext) -> AssertionResult:
        pattern = str(self._require("pattern"))
        try:
            compiled = re.compile(pattern)
        except re.error as exc:
            raise AssertionConfigError(
                f"assertion {self.assertion_id!r}: invalid regex {pattern!r}: {exc}"
            ) from None
        haystack = context.result.text or ""
        if compiled.search(haystack):
            return self._pass(
                expected=f"text matches /{pattern}/", observed=_clip(haystack)
            )
        return self._fail(
            expected=f"text matches /{pattern}/",
            observed=_clip(haystack),
            message="no match for pattern in response text",
        )


@_register
class JsonPathEqualsAssertion(Assertion):
    type = "json_path_equals"

    def evaluate(self, context: AssertionContext) -> AssertionResult:
        path = str(self._require("path"))
        expected = self._require("value")
        observed = _dig(context.result.body, path)
        if observed is _MISSING:
            return self._fail(
                expected=expected,
                observed=None,
                message=f"path {path!r} not present in body",
            )
        if observed == expected:
            return self._pass(expected=expected, observed=_clip(observed))
        return self._fail(
            expected=expected,
            observed=_clip(observed),
            message=f"value at {path!r} does not equal expected",
        )


@_register
class LatencyBelowAssertion(Assertion):
    type = "latency_below"

    def evaluate(self, context: AssertionContext) -> AssertionResult:
        raw = self._require("max_ms")
        try:
            budget = float(raw)
        except (TypeError, ValueError):
            raise AssertionConfigError(
                f"assertion {self.assertion_id!r}: 'max_ms' must be a number"
            ) from None
        observed = context.result.latency_ms
        if observed is None:
            return self._fail(
                expected=f"<= {budget} ms",
                observed=None,
                message="latency not reported by adapter",
            )
        if observed <= budget:
            return self._pass(expected=f"<= {budget} ms", observed=observed)
        return self._fail(
            expected=f"<= {budget} ms",
            observed=observed,
            message=f"latency {observed} ms exceeds budget {budget} ms",
        )


class _EvidenceAssertion(Assertion):
    """Shared logic for the coverage-aware evidence existence checks.

    ``_guard`` enforces the mandatory rule: no evidence, or a namespace that is
    not in the declared coverage, yields ``SKIPPED`` -- for *both* the positive
    and the negative check. Absence is only meaningful within declared
    coverage.
    """

    def _event_type(self) -> str:
        return str(self._require("event_type"))

    def _namespace(self) -> str:
        return evidence_namespace(self._event_type())

    def _matching_events(self, context: AssertionContext) -> list[Any]:
        event_type = self._event_type()
        attributes = self.config.get("attributes", {}) or {}
        assert context.evidence is not None  # guarded by _guard
        return [
            e
            for e in context.evidence
            if e.event_type == event_type and _attrs_match(e.attributes, attributes)
        ]

    def _describe(self) -> str:
        event_type = self.config.get("event_type")
        attributes = self.config.get("attributes")
        if attributes:
            return f"event {event_type!r} with attributes {dict(attributes)!r}"
        return f"event {event_type!r}"

    def _guard(self, context: AssertionContext) -> AssertionResult | None:
        namespace = self._namespace()
        if context.evidence is None:
            return self._skip(
                expected=self._describe(),
                observed="no evidence available",
                message="target exposed no evidence; not evaluated",
            )
        if not context.evidence.covers(namespace):
            return self._skip(
                expected=self._describe(),
                observed=f"declared coverage {list(context.evidence.coverage)}",
                message=(
                    f"evidence namespace {namespace!r} is not in declared "
                    "coverage; not evaluated"
                ),
            )
        return None


@_register
class EvidenceEventExistsAssertion(_EvidenceAssertion):
    type = "evidence_event_exists"

    def evaluate(self, context: AssertionContext) -> AssertionResult:
        skipped = self._guard(context)
        if skipped is not None:
            return skipped
        matches = self._matching_events(context)
        if matches:
            return self._pass(
                expected=f"{self._describe()} present",
                observed=f"{len(matches)} matching event(s)",
            )
        return self._fail(
            expected=f"{self._describe()} present",
            observed="0 matching events",
            message=f"expected {self._describe()} but it was not observed",
        )


@_register
class EvidenceEventNotExistsAssertion(_EvidenceAssertion):
    type = "evidence_event_not_exists"

    def evaluate(self, context: AssertionContext) -> AssertionResult:
        skipped = self._guard(context)
        if skipped is not None:
            return skipped
        matches = self._matching_events(context)
        if not matches:
            return self._pass(
                expected=f"{self._describe()} absent", observed="0 matching events"
            )
        return self._fail(
            expected=f"{self._describe()} absent",
            observed=f"{len(matches)} matching event(s)",
            message=f"forbidden {self._describe()} was observed",
        )


__all__ = [
    "ContainsAssertion",
    "EqualsAssertion",
    "EvidenceEventExistsAssertion",
    "EvidenceEventNotExistsAssertion",
    "JsonPathEqualsAssertion",
    "LatencyBelowAssertion",
    "NotContainsAssertion",
    "RegexMatchAssertion",
    "StatusEqualsAssertion",
]
