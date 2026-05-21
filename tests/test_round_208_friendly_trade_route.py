"""Round 208 (base-rules audit, batch 3): SMOKE-145.

Friendly Locale (1.3.1) Condition 1 requires a STRONGHOLD Conquered by
the side -- not merely any Conquered marker. A conquered Trade Route (a
boxed but non-Stronghold Locale) is Friendly to NEITHER side. Rules
example: "Neva with a Conquered marker: Friendly to NEITHER side."
Pre-fix, _is_friendly_locale treated any own Conquered marker as
satisfying Condition 1, wrongly making a Teuton-conquered Rus Trade
Route Friendly to the Teutons (e.g. enabling Pay-with-Loot there).
"""
from __future__ import annotations

import nevsky.actions  # noqa: F401
from nevsky.actions import _is_friendly_locale
from nevsky.scenarios import load_scenario
from nevsky.static_data import load_locales


def _first(pred):
    return next(k for k, v in load_locales().items() if pred(v))


def test_conquered_trade_route_friendly_to_neither():
    s = load_scenario("crusade_on_novgorod", seed=1)
    tr = _first(lambda v: v.get("type") == "trade_route")  # all in Rus
    s.locales[tr].teutonic_conquered = 1
    assert _is_friendly_locale(s, tr, "teutonic") is False
    assert _is_friendly_locale(s, tr, "russian") is False


def test_conquered_stronghold_is_friendly_to_conqueror():
    s = load_scenario("crusade_on_novgorod", seed=1)
    fort = _first(lambda v: v.get("type") == "fort" and v.get("territory") == "russian")
    s.locales[fort].teutonic_conquered = 1
    assert _is_friendly_locale(s, fort, "teutonic") is True
    assert _is_friendly_locale(s, fort, "russian") is False  # enemy conquered marker


def test_own_territory_trade_route_friendly_to_owner():
    s = load_scenario("crusade_on_novgorod", seed=1)
    tr = _first(lambda v: v.get("type") == "trade_route")  # Rus
    # Empty, in Russian territory -> Friendly to Russians via own-territory.
    assert _is_friendly_locale(s, tr, "russian") is True


def test_castle_overlay_on_conquered_town_is_friendly():
    # A Castle built (Stonemasons) overlaying a Locale makes it a
    # Stronghold; if Conquered by the builder it is Friendly to them.
    s = load_scenario("crusade_on_novgorod", seed=1)
    # Use a russian fort, overlay a teutonic castle + conquered marker.
    fort = _first(lambda v: v.get("type") == "fort" and v.get("territory") == "russian")
    s.locales[fort].teutonic_castle = True
    s.locales[fort].teutonic_conquered = 1
    assert _is_friendly_locale(s, fort, "teutonic") is True
