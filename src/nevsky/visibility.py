"""Transient Battle/Storm mat visibility, separate from saved game state."""

from __future__ import annotations

from collections.abc import Callable
from contextvars import ContextVar
from functools import wraps
from inspect import signature
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")
_COMBAT_MATS: ContextVar[tuple[int, set[str]] | None] = ContextVar(
    "nevsky_combat_mats", default=None
)


def reveal_combat_mats(function: Callable[P, T]) -> Callable[P, T]:
    """Reveal the current engagement's participants during player callbacks."""
    parameters = signature(function)

    @wraps(function)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> T:
        bound = parameters.bind(*args, **kwargs)
        state = bound.arguments["state"]
        lords: set[str] = set()
        for name in ("attacker_lords", "defender_lords", "sallying_lords"):
            lords.update(bound.arguments.get(name) or [])
        lords.update(combat_visible_lords(state))
        token = _COMBAT_MATS.set((id(state), lords))
        try:
            return function(*args, **kwargs)
        finally:
            _COMBAT_MATS.reset(token)

    return wrapped


def combat_visible_lords(state: object) -> set[str]:
    scope = _COMBAT_MATS.get()
    return scope[1] if scope is not None and scope[0] == id(state) else set()
