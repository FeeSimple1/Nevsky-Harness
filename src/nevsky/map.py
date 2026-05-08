"""Map utility: Locale way-class classification.

Per Nevsky_Map.txt, every Locale has zero or more Ways of three types:
Trackway, Waterway, Seaport (the last is technically a Locale property
indicating Sail eligibility, not a Way type — but we lift it into the
classifier here for convenience).

This module is a shared dependency for:
  - Supply Routes (4.6.2): Boats use Waterways; Carts use Trackways.
  - Sail (4.7.3): origin and destination must both be Seaports.
  - Ravage (4.7.2): adjacency type can affect Raiders capability.
  - Setup Transport heuristic (Q-001 / Q-002): default Transport per
    start-Locale way-class profile.

Classifications surface from the way graph (`load_ways`) and the
Locale static data (`load_locales`'s `seaport` field).

Per the user's Q-002 spec, the no-Trackway list (Locales with no
Trackway adjacencies) consists of:
  Riga, Luga, Volkhov, Lovat, Rusa.
The harness verifies this at startup via the way graph.
"""

from __future__ import annotations

from functools import lru_cache

from nevsky.static_data import load_locales, load_ways


@lru_cache(maxsize=1)
def way_classes_per_locale() -> dict[str, set[str]]:
    """Return {locale_id: set of way types adjacent} (e.g.,
    {"riga": {"waterway"}, "dorpat": {"trackway", "waterway"}}).
    """
    out: dict[str, set[str]] = {lid: set() for lid in load_locales()}
    for w in load_ways():
        out.setdefault(w["a"], set()).add(w["type"])
        out.setdefault(w["b"], set()).add(w["type"])
    return out


def has_trackway(locale_id: str) -> bool:
    return "trackway" in way_classes_per_locale().get(locale_id, set())


def has_waterway(locale_id: str) -> bool:
    return "waterway" in way_classes_per_locale().get(locale_id, set())


def is_seaport(locale_id: str) -> bool:
    info = load_locales().get(locale_id, {})
    return bool(info.get("seaport"))


# Per Q-002 spec: the Russian river spine (Lord starts here in 1-slot
# heuristic rule 3a -> Boat).
_RUSSIAN_RIVER_SPINE = {"volkhov", "ladoga", "neva", "novgorod", "rusa", "lovat"}


def on_russian_river_spine(locale_id: str) -> bool:
    return locale_id in _RUSSIAN_RIVER_SPINE


# Locales with no Trackway adjacencies, per spec.
_NO_TRACKWAY_LIST = {"riga", "luga", "volkhov", "lovat", "rusa"}


def in_no_trackway_list(locale_id: str) -> bool:
    return locale_id in _NO_TRACKWAY_LIST
