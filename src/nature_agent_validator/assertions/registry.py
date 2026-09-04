"""Internal assertion-type table.

Phase 0 does **not** expose a public plugin/registration API. The built-in
assertion types in :mod:`nature_agent_validator.assertions.builtin` populate a
private table via the module-internal ``_register`` decorator. The only
supported entry point is the :func:`build_assertion` factory, which the runner
uses to turn an :class:`AssertionSpec` into a live assertion.
"""

from __future__ import annotations

from nature_agent_validator.errors import NatureValidatorError, UnknownAssertionType

from .base import Assertion
from .spec import AssertionSpec

_REGISTRY: dict[str, type[Assertion]] = {}


def _register(cls: type[Assertion]) -> type[Assertion]:
    """Module-internal class decorator: record ``cls`` under its ``type`` name."""
    name = cls.type
    if not name:
        raise NatureValidatorError(
            f"{cls.__name__} must define a non-empty class attribute 'type'"
        )
    existing = _REGISTRY.get(name)
    if existing is not None and existing is not cls:
        raise NatureValidatorError(
            f"assertion type {name!r} is already registered to "
            f"{existing.__name__}"
        )
    _REGISTRY[name] = cls
    return cls


def _known_types() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))


def _get_assertion_type(name: str) -> type[Assertion]:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise UnknownAssertionType(
            f"no assertion registered for type {name!r} (known: {_known_types()})"
        ) from None


def build_assertion(spec: AssertionSpec) -> Assertion:
    """Factory: resolve ``spec.type`` and build the assertion from ``spec``."""
    return _get_assertion_type(spec.type).from_spec(spec)


__all__ = ["build_assertion"]
