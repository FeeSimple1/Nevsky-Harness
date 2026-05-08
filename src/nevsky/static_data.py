"""Loaders for the static reference data files in src/nevsky/data/static.

These return parsed JSON dicts, cached on first load. The data is
read-only at runtime; mutating the returned objects is undefined
behavior.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any

_PACKAGE = "nevsky.data.static"


def _read(name: str) -> Any:
    text = resources.files(_PACKAGE).joinpath(name).read_text(encoding="utf-8")
    return json.loads(text)


@lru_cache(maxsize=1)
def load_lords() -> dict[str, dict[str, Any]]:
    """Lord static data keyed by lord_id."""
    return _read("lords.json")["lords"]


@lru_cache(maxsize=1)
def load_locales() -> dict[str, dict[str, Any]]:
    """Locale static data keyed by locale_id."""
    raw = _read("locales.json")["locales"]
    return {entry["id"]: entry for entry in raw}


@lru_cache(maxsize=1)
def load_ways() -> list[dict[str, Any]]:
    """Way graph as a list of {a, b, type} edges (undirected)."""
    return list(_read("ways.json")["ways"])


@lru_cache(maxsize=1)
def load_cards() -> dict[str, dict[str, Any]]:
    """Card metadata keyed by card_id."""
    raw = _read("cards.json")["cards"]
    return {entry["card_id"]: entry for entry in raw}


def neighbors(locale_id: str) -> list[tuple[str, str]]:
    """Return list of (neighbor_locale_id, way_type) for the given locale."""
    out: list[tuple[str, str]] = []
    for w in load_ways():
        if w["a"] == locale_id:
            out.append((w["b"], w["type"]))
        elif w["b"] == locale_id:
            out.append((w["a"], w["type"]))
    return out


@lru_cache(maxsize=1)
def load_forces() -> dict[str, dict[str, Any]]:
    """Forces table (strikes, protection ranges, archery defaults)."""
    raw = _read("forces.json")
    return raw["units"]


@lru_cache(maxsize=1)
def load_strongholds() -> dict[str, dict[str, Any]]:
    """Strongholds table (capacity, walls_max, garrison, vp, spoils)
    keyed by Locale type (novgorod / city / fort / trade_route /
    bishopric / castle). Commanderies are not Strongholds for Siege /
    Storm purposes (Phase 3c)."""
    return _read("strongholds.json")["strongholds"]
