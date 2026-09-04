"""Resolve a :class:`ScenarioTarget` to a concrete adapter instance.

Phase 0 has one built-in, declaratively-constructible adapter (``static``),
held in a private table. There is no public adapter-registration API yet;
code-driven callers build an adapter themselves and pass it straight to
``Runner.run(scenario, adapter=...)``. The only supported entry point here is
the :func:`build_adapter` factory, used by the runner and the CLI.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from nature_agent_validator.errors import AdapterError

from .base import TargetAdapter
from .static import StaticAdapter

if TYPE_CHECKING:
    from nature_agent_validator.scenario.target import ScenarioTarget

_BUILTIN: dict[str, type[TargetAdapter]] = {
    StaticAdapter.name: StaticAdapter,
}


def build_adapter(target: "ScenarioTarget") -> TargetAdapter:
    """Factory: build the built-in adapter named by ``target.adapter``."""
    try:
        cls = _BUILTIN[target.adapter]
    except KeyError:
        raise AdapterError(
            f"adapter {target.adapter!r} is not available in Phase 0 "
            f"(built-in adapters: {sorted(_BUILTIN)})"
        ) from None
    return cls.from_config(target.config)


__all__ = ["build_adapter"]
