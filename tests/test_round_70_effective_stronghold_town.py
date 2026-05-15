"""SMOKE-065 (Round 70): _effective_stronghold returns Castle stats
for Castle-marker overlays on Town locales (base type "town" has no
strongholds.json entry).

Before: `if base is None: return None` short-circuit silently broke
Castle-on-Town (Stonemasons converts an Unbesieged Town in Rus into a
Castle). Downstream consumers (Withdraw, Siege, Storm, Sally) couldn't
recognize the Stronghold.
"""
from __future__ import annotations

import nevsky.actions  # noqa: F401 — ensure handler registration
from nevsky.campaign import _effective_stronghold, _stronghold_at
from nevsky.scenarios import load_scenario


def test_castle_overlay_on_town_returns_castle_stats():
    s = load_scenario("crusade_on_novgorod", seed=1)
    # narwia: type=town, territory=teutonic, seaport=True
    assert _stronghold_at("narwia") is None  # baseline: town has no Stronghold
    s.locales["narwia"].russian_castle = True
    eff = _effective_stronghold(s, "narwia")
    assert eff is not None
    assert eff["capacity"] == 2
    assert eff["walls_max"] == 4
    assert eff["vp"] == 1
    assert eff["garrison"].get("men_at_arms", 0) == 1
    assert eff["garrison"].get("knights", 0) == 1


def test_castle_overlay_on_town_side_matches_marker_color():
    """Castle-on-non-Stronghold base: defender side = marker color
    (there is no underlying Stronghold to inherit from)."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.locales["narwia"].russian_castle = True
    eff = _effective_stronghold(s, "narwia")
    assert eff["side"] == "russian"

    s2 = load_scenario("crusade_on_novgorod", seed=1)
    s2.locales["narwia"].teutonic_castle = True
    eff2 = _effective_stronghold(s2, "narwia")
    assert eff2["side"] == "teutonic"


def test_castle_overlay_on_fort_keeps_smoke_054_side_semantics():
    """Castle-on-Stronghold-base: side preserved from base (SMOKE-054
    semantics). This test guards against the SMOKE-065 fix accidentally
    changing the Castle-on-Fort behavior."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.locales["koporye"].teutonic_castle = True
    eff = _effective_stronghold(s, "koporye")
    assert eff is not None
    assert eff["capacity"] == 2
    # SMOKE-054 baseline: side = base Fort's side (russian for koporye)
    assert eff["side"] == "russian"


def test_no_castle_marker_unchanged():
    """Without Castle marker, _effective_stronghold returns base
    (which may be None for non-Stronghold locales)."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    # Town with no castle marker
    eff = _effective_stronghold(s, "narwia")
    assert eff is None
    # Fort with no castle marker
    eff_fort = _effective_stronghold(s, "koporye")
    assert eff_fort is not None
    assert eff_fort["capacity"] == 1  # base Fort stats
