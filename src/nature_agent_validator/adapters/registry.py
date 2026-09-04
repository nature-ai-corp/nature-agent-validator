"""Resolve a :class:`ScenarioTarget` to a concrete adapter instance.

Built-in, declaratively-constructible adapters are held in a private table.
There is no public adapter-registration API; code-driven callers build an
adapter themselves and pass it straight to ``Runner.run(scenario, adapter=...)``.
The only supported entry point here is the :func:`build_adapter` factory, used
by the runner and the CLI.

The ``http`` adapter is resolved lazily (its module imports :mod:`urllib`) so
that importing the core package never pulls in any networking module.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from nature_agent_validator.errors import AdapterError

from .base import TargetAdapter
from .static import StaticAdapter

if TYPE_CHECKING:
    from nature_agent_validator.scenario.target import ScenarioTarget

_BUILTIN: dict[str, type[TargetAdapter]] = {
    StaticAdapter.name: StaticAdapter,
}


def _load_http() -> type[TargetAdapter]:
    from .http import HttpAdapter

    return HttpAdapter


#: Names whose implementing class is imported only on first use.
_LAZY: dict[str, Callable[[], type[TargetAdapter]]] = {
    "http": _load_http,
}


def _available_names() -> list[str]:
    return sorted({*_BUILTIN, *_LAZY})


def build_adapter(target: "ScenarioTarget") -> TargetAdapter:
    """Factory: build the built-in adapter named by ``target.adapter``."""
    name = target.adapter
    if name in _BUILTIN:
        cls: type[TargetAdapter] = _BUILTIN[name]
    elif name in _LAZY:
        cls = _LAZY[name]()
    else:
        raise AdapterError(
            f"adapter {name!r} is not available "
            f"(built-in adapters: {_available_names()})"
        )
    return cls.from_config(target.config)


__all__ = ["build_adapter"]
