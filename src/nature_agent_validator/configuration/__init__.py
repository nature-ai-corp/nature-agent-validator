"""Environment configuration and secret-safe HTTP authentication (Phase 5).

An :class:`EnvironmentConfig` is an explicit JSON file describing **runtime
connection overrides only** -- it never changes validation intent. The same
portable :class:`~nature_agent_validator.scenario.scenario.Scenario` can be run
against different environments by supplying a different config.

Secrets are **references, never values**. A :class:`SecretHeaderRef` names a
process environment variable and an optional literal prefix; the real value is
read from :data:`os.environ` as late as possible (inside ``HttpAdapter.send``)
and lives only in the outbound request headers for the duration of one send.
Nothing here reads ``os.environ`` and nothing stores a resolved secret.

Not a configuration-management system: no registry, no inheritance, no
profiles, no ``base_url``, no templating / ``${VAR}`` interpolation, no
``.env`` files, no external secret managers. See ``docs/architecture.md``.
"""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from nature_agent_validator.errors import ConfigurationError
from nature_agent_validator.scenario import Scenario, ScenarioTarget

#: Environment-variable name rule (POSIX-ish identifier). No shell syntax,
#: no ``${...}``, no dotted names, no expressions.
_ENV_NAME_PATTERN = "[A-Za-z_][A-Za-z0-9_]*"
_ENV_NAME_RE = re.compile(_ENV_NAME_PATTERN)

_ROOT_FIELDS = frozenset({"name", "target"})
_TARGET_FIELDS = frozenset({"url", "timeout", "headers", "secret_headers"})
_SECRET_REF_FIELDS = frozenset({"env", "prefix"})

#: The Phase-1 HTTP adapter config keys these overrides map onto.
HTTP_ADAPTER_NAME = "http"


@dataclasses.dataclass(frozen=True, slots=True)
class SecretHeaderRef:
    """A reference to a secret to inject as one outbound HTTP header.

    Stores only the environment-variable *name* and an optional literal
    *prefix* (e.g. ``"Bearer "``). It never holds a resolved value.
    """

    env: str
    prefix: str = ""


@dataclasses.dataclass(frozen=True, slots=True)
class EnvironmentConfig:
    """Runtime connection overrides for an HTTP target. Values only for normal
    headers; secret headers are :class:`SecretHeaderRef` references."""

    name: str
    url: str | None = None
    timeout: float | None = None
    headers: Mapping[str, str] = dataclasses.field(default_factory=dict)
    secret_headers: Mapping[str, SecretHeaderRef] = dataclasses.field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "headers", MappingProxyType(dict(self.headers)))
        object.__setattr__(
            self, "secret_headers", MappingProxyType(dict(self.secret_headers))
        )

    @property
    def has_target_overrides(self) -> bool:
        return (
            self.url is not None
            or self.timeout is not None
            or bool(self.headers)
            or bool(self.secret_headers)
        )


# --------------------------------------------------------------------------- #
# loading
# --------------------------------------------------------------------------- #

def load_environment(path: str | Path) -> EnvironmentConfig:
    """Parse and validate an environment JSON file. Fail-closed on anything
    malformed, ambiguous, or unsupported (raises :class:`ConfigurationError`)."""
    p = Path(path)
    if not p.is_file():
        raise ConfigurationError(f"environment file not found: {p}")
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"{p.name}: invalid JSON: {exc}") from None
    if not isinstance(raw, Mapping):
        raise ConfigurationError(
            f"{p.name}: top-level value must be a JSON object"
        )

    unknown = sorted(set(raw) - _ROOT_FIELDS)
    if unknown:
        raise ConfigurationError(f"unknown environment field(s): {unknown}")

    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ConfigurationError(
            "environment 'name' is required and must be a non-empty string"
        )

    target = raw.get("target", {})
    if not isinstance(target, Mapping):
        raise ConfigurationError("environment 'target' must be a JSON object")
    unknown_t = sorted(set(target) - _TARGET_FIELDS)
    if unknown_t:
        raise ConfigurationError(f"unknown environment target field(s): {unknown_t}")

    url = _parse_url(target.get("url"))
    timeout = _parse_timeout(target.get("timeout"))
    headers = _parse_headers(target.get("headers", {}))
    secret_headers = _parse_secret_headers(target.get("secret_headers", {}))

    return EnvironmentConfig(
        name=name,
        url=url,
        timeout=timeout,
        headers=headers,
        secret_headers=secret_headers,
    )


def _parse_url(raw: Any) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ConfigurationError(
            f"environment target.url must be a string, got {type(raw).__name__}"
        )
    return raw


def _parse_timeout(raw: Any) -> float | None:
    if raw is None:
        return None
    # reuse the Phase-1 adapter's coercion semantics
    try:
        return float(raw)
    except (TypeError, ValueError):
        raise ConfigurationError(
            f"environment target.timeout must be a number, got {raw!r}"
        ) from None


def _parse_headers(raw: Any) -> dict[str, str]:
    if not isinstance(raw, Mapping):
        raise ConfigurationError("environment target.headers must be a JSON object")
    out: dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or key == "":
            raise ConfigurationError(
                f"environment target.headers has an invalid header name: {key!r}"
            )
        if not isinstance(value, str):
            raise ConfigurationError(
                f"environment target.headers[{key!r}] must be a string, got "
                f"{type(value).__name__}"
            )
        out[key] = value
    return out


def _parse_secret_headers(raw: Any) -> dict[str, SecretHeaderRef]:
    if not isinstance(raw, Mapping):
        raise ConfigurationError(
            "environment target.secret_headers must be a JSON object"
        )
    out: dict[str, SecretHeaderRef] = {}
    seen_ci: dict[str, str] = {}
    for header_name, ref_raw in raw.items():
        if not isinstance(header_name, str) or header_name == "":
            raise ConfigurationError(
                "environment target.secret_headers has an invalid header name: "
                f"{header_name!r}"
            )
        lowered = header_name.lower()
        if lowered in seen_ci:
            raise ConfigurationError(
                "environment target.secret_headers has duplicate header name "
                f"(case-insensitive): {seen_ci[lowered]!r} and {header_name!r}"
            )
        seen_ci[lowered] = header_name
        if not isinstance(ref_raw, Mapping):
            raise ConfigurationError(
                f"secret header {header_name!r} must be a JSON object"
            )
        unknown_r = sorted(set(ref_raw) - _SECRET_REF_FIELDS)
        if unknown_r:
            raise ConfigurationError(
                f"secret header {header_name!r} has unknown field(s): {unknown_r}"
            )
        env_name = ref_raw.get("env")
        if not isinstance(env_name, str) or not _ENV_NAME_RE.fullmatch(env_name):
            raise ConfigurationError(
                f"secret header {header_name!r}: 'env' must be an environment "
                f"variable name matching /{_ENV_NAME_PATTERN}/ (got {env_name!r})"
            )
        prefix = ref_raw.get("prefix", "")
        if not isinstance(prefix, str):
            raise ConfigurationError(
                f"secret header {header_name!r}: 'prefix' must be a string, got "
                f"{type(prefix).__name__}"
            )
        out[header_name] = SecretHeaderRef(env=env_name, prefix=prefix)
    return out


# --------------------------------------------------------------------------- #
# application  (the single shared path for `validate` and `validate-suite`)
# --------------------------------------------------------------------------- #

def apply_environment(scenario: Scenario, env: EnvironmentConfig) -> Scenario:
    """Return a **new** effective ``Scenario`` with ``env``'s runtime overrides
    applied to its HTTP target. The original ``scenario`` is never mutated.

    Only ``target`` url / timeout / headers / secret_headers are touched;
    scenario id, name, method, request, expectations, evidence_field, and every
    other field are copied verbatim. Applying target overrides to a non-HTTP
    target is a :class:`ConfigurationError`.
    """
    if not env.has_target_overrides:
        return scenario  # a name-only environment changes nothing

    if scenario.target.adapter != HTTP_ADAPTER_NAME:
        raise ConfigurationError(
            f"environment {env.name!r} has target overrides but scenario "
            f"{scenario.scenario_id!r} targets adapter "
            f"{scenario.target.adapter!r}, not {HTTP_ADAPTER_NAME!r}"
        )

    config: dict[str, Any] = dict(scenario.target.config)

    if env.url is not None:
        config["url"] = env.url  # exact override, no joining/templating
    if env.timeout is not None:
        config["timeout_seconds"] = env.timeout  # Phase-1 key + semantics

    merged = _merge_headers(config.get("headers") or {}, env.headers)

    merged_ci = {k.lower() for k in merged}
    for secret_name in env.secret_headers:
        if secret_name.lower() in merged_ci:
            raise ConfigurationError(
                f"environment {env.name!r}: header {secret_name!r} is configured "
                "both as a normal header and as a secret header"
            )

    if merged:
        config["headers"] = merged
    if env.secret_headers:
        # references only -- {header, env, prefix}; never a resolved value
        config["secret_headers"] = [
            {"header": name, "env": ref.env, "prefix": ref.prefix}
            for name, ref in env.secret_headers.items()
        ]

    effective_target = ScenarioTarget(adapter=HTTP_ADAPTER_NAME, config=config)
    return dataclasses.replace(scenario, target=effective_target)


def _merge_headers(
    scenario_headers: Mapping[str, Any], env_headers: Mapping[str, str]
) -> dict[str, str]:
    """Scenario headers overlaid by environment headers; environment wins for
    the same header name **case-insensitively**, with no duplicate semantic
    headers left behind."""
    merged = {str(k): str(v) for k, v in dict(scenario_headers).items()}
    for key, value in env_headers.items():
        for existing in [ek for ek in merged if ek.lower() == key.lower()]:
            del merged[existing]
        merged[key] = value
    return merged


__all__ = [
    "EnvironmentConfig",
    "SecretHeaderRef",
    "load_environment",
    "apply_environment",
]
