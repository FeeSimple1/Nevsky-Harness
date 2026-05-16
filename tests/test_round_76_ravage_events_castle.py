"""SMOKE-073 (Round 76): T15 Mindaugas (Teutonic) and R12 Mindaugas
(Russian) Stronghold detection misses Castle-on-Town overlays and
(for T15) the trade_route base type.

Per AoW Reference:
  T15: "Place Ravaged in a Locale in Rus within 2 of Ostrov, not at
       Russian Lord or Stronghold"
  R12: "Place Ravaged in a Locale in Livonia within 2 of Rositten,
       not at Teutonic Lord or Stronghold"

The previous code used static-type lists (T15: fort/city/novgorod;
R12: bishopric/castle) to decide "is this a Stronghold of the enemy
side?" This missed:
  - T17 Stonemasons Castle markers on Town locales (russian_castle /
    teutonic_castle overlays).
  - For T15: the base type 'trade_route' (Russian Stronghold per
    strongholds.json).

Fix replaces static-type checks with _effective_stronghold +
.get("side") + non-Conquered guard. Tests cover the Castle-on-Town
overlay case (which is reproducible within the 2-distance window).
"""
from __future__ import annotations

import pytest

from nevsky.actions import IllegalAction
from nevsky.events import _ev_mindaugas_t, _ev_mindaugas_r
from nevsky.scenarios import load_scenario


def test_t15_rejects_russian_castle_on_town_overlay():
    """T17 Stonemasons-built Russian Castle on a Town (e.g., ostrov) blocks T15."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    # ostrov is a Russian-territory Town within 2 of itself (distance 0).
    s.locales["ostrov"].russian_castle = True
    s.locales["ostrov"].teutonic_conquered = 0
    with pytest.raises(IllegalAction) as e:
        _ev_mindaugas_t(s, {"locale": "ostrov"})
    assert e.value.code == "russian_stronghold"


def test_t15_allows_ravage_at_plain_town():
    """A non-Stronghold Town with no Castle marker is fair game for T15."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    # ostrov is a Russian-territory Town, no Castle marker, no enemy Lord.
    s.locales["ostrov"].russian_castle = False
    s.locales["ostrov"].teutonic_castle = False
    # Remove any Russian Lord that might be at ostrov.
    for lid, l in s.lords.items():
        if l.side == "russian" and l.location == "ostrov":
            l.location = None
    r = _ev_mindaugas_t(s, {"locale": "ostrov"})
    assert r["event"] == "T15"
    assert s.locales["ostrov"].teutonic_ravaged is True


def test_r12_rejects_teutonic_castle_on_town_overlay():
    """T17 Stonemasons-built Teutonic Castle on a Town (e.g., rositten) blocks R12."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    # rositten is a Crusader-Livonia Town within 2 of itself (distance 0).
    s.locales["rositten"].teutonic_castle = True
    s.locales["rositten"].russian_conquered = 0
    with pytest.raises(IllegalAction) as e:
        _ev_mindaugas_r(s, {"locale": "rositten"})
    assert e.value.code == "teutonic_stronghold"


def test_r12_allows_ravage_at_plain_livonia_town():
    """A non-Stronghold Livonia Town with no Castle marker is fair game for R12."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    # rositten Town, no Castle marker, no Teuton Lord.
    s.locales["rositten"].russian_castle = False
    s.locales["rositten"].teutonic_castle = False
    for lid, l in s.lords.items():
        if l.side == "teutonic" and l.location == "rositten":
            l.location = None
    r = _ev_mindaugas_r(s, {"locale": "rositten"})
    assert r["event"] == "R12"
    assert s.locales["rositten"].russian_ravaged is True


def test_t15_still_rejects_base_stronghold_types():
    """Regression: T15 must continue to reject base Russian Stronghold
    types (fort/city/novgorod) even after the _effective_stronghold rewrite."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    # pleskau is a Russian City within 2 of ostrov.
    # Make sure no Russian Lord present.
    for lid, l in s.lords.items():
        if l.side == "russian" and l.location == "pskov":
            l.location = None
    s.locales["pskov"].teutonic_conquered = 0
    with pytest.raises(IllegalAction) as e:
        _ev_mindaugas_t(s, {"locale": "pskov"})
    assert e.value.code == "russian_stronghold"


def test_r12_still_rejects_base_stronghold_types():
    """Regression: R12 must continue to reject base Teutonic Stronghold
    types (bishopric/castle) even after the _effective_stronghold rewrite."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    # Find a bishopric/castle within 2 of rositten.
    from nevsky.static_data import load_ways, load_locales
    ways = load_ways()
    adj = {}
    for w in ways:
        adj.setdefault(w["a"], []).append(w["b"])
        adj.setdefault(w["b"], []).append(w["a"])
    visited = {"rositten": 0}
    frontier = ["rositten"]
    for d in range(1, 3):
        nxt = []
        for n in frontier:
            for m in adj.get(n, []):
                if m not in visited:
                    visited[m] = d
                    nxt.append(m)
        frontier = nxt
    locs = load_locales()
    targets = [k for k in visited if locs[k].get("type") in ("bishopric", "castle")
               and locs[k].get("subregion") == "crusader_livonia"]
    if not targets:
        pytest.skip("no bishopric/castle within 2 of rositten in this scenario")
    target = targets[0]
    for lid, l in s.lords.items():
        if l.side == "teutonic" and l.location == target:
            l.location = None
    s.locales[target].russian_conquered = 0
    with pytest.raises(IllegalAction) as e:
        _ev_mindaugas_r(s, {"locale": target})
    assert e.value.code == "teutonic_stronghold"
