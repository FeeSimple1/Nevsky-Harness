"""4.9.1 Grow: the removing side SELECTS which Enemy Ravaged markers to
reduce to half. The harness auto-picked a deterministic sort; now the
player may choose via args.grow_remove (VP is identical either way, but
which Locales stay Ravaged affects later Forage legality).
"""
from __future__ import annotations

import pytest

import nevsky.actions  # noqa: F401
from nevsky.actions import IllegalAction
from nevsky.campaign import _h_end_campaign_resolve
from nevsky.scenarios import load_scenario


def _setup(n=4):
    s = load_scenario("peipus", seed=1)
    s.meta.phase = "campaign"; s.meta.campaign_step = "end_campaign"
    s.meta.active_player = "teutonic"; s.meta.box = 8  # end of Rasputitsa
    rav = []
    for lid, loc in s.locales.items():
        if len(rav) < n and not loc.russian_ravaged and not loc.teutonic_ravaged:
            loc.russian_ravaged = True
            rav.append(lid)
    return s, rav


def test_grow_remove_honors_player_selection():
    s, rav = _setup(4)  # T removes 2 (half of 4), keeps 2
    choose = [rav[1], rav[3]]
    _h_end_campaign_resolve(s, "teutonic", {"grow_remove": choose})
    removed = [lid for lid in rav if not s.locales[lid].russian_ravaged]
    kept = [lid for lid in rav if s.locales[lid].russian_ravaged]
    assert sorted(removed) == sorted(choose)
    assert sorted(kept) == sorted([rav[0], rav[2]])


def test_grow_remove_wrong_count_rejected():
    s, rav = _setup(4)
    with pytest.raises(IllegalAction) as e:
        _h_end_campaign_resolve(s, "teutonic", {"grow_remove": [rav[0]]})  # need 2
    assert e.value.code == "bad_grow_remove"


def test_grow_remove_non_enemy_marker_rejected():
    s, rav = _setup(4)
    bad = next(lid for lid in s.locales if lid not in rav)
    with pytest.raises(IllegalAction) as e:
        _h_end_campaign_resolve(s, "teutonic", {"grow_remove": [rav[0], bad]})
    assert e.value.code == "bad_grow_remove"


def test_grow_default_deterministic_without_arg():
    s, rav = _setup(4)
    _h_end_campaign_resolve(s, "teutonic", {})  # no selection -> sorted fallback
    removed = sorted(lid for lid in rav if not s.locales[lid].russian_ravaged)
    assert removed == sorted(rav)[:2]
