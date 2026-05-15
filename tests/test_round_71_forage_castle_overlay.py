"""SMOKE-066 (Round 71): Forage at a friendly Castle-marker overlay
on a Town locale must be allowed in non-Summer seasons.

T17 Stonemasons converts a Russian Town into a Castle (Stronghold).
Forage's "Friendly Stronghold OR Summer" check (4.7.1) previously used
a static-type list that omitted "town", so a Castle-on-Town locale was
treated as a non-Stronghold for Forage purposes — wrongly rejecting
Forage in Early/Late Winter and Rasputitsa.
"""
from __future__ import annotations

import pytest

from nevsky.actions import IllegalAction, apply_action
from nevsky.scenarios import load_scenario


def _setup_forage(state, lord_id, loc):
    lord = state.lords[lord_id]
    lord.state = "mustered"
    lord.location = loc
    lord.forces = {"knights": 1}
    lord.assets = {}
    state.meta.phase = "campaign"
    state.meta.campaign_step = "command"
    state.meta.active_player = lord.side
    state.campaign_turn.in_feed_pay_disband = False
    state.campaign_turn.next_to_reveal = lord.side
    state.campaign_turn.active_lord = lord_id
    state.campaign_turn.active_card = lord_id
    state.campaign_turn.actions_remaining = 3


def test_forage_at_friendly_castle_on_town_in_winter():
    """Friendly Teutonic Castle overlaid on a Town in Teutonic territory:
    Forage allowed in non-Summer."""
    s = load_scenario("watland", seed=1)  # box 4 = early_winter
    s.locales["narwia"].teutonic_castle = True
    _setup_forage(s, "hermann", "narwia")
    r = apply_action(s, {"type": "cmd_forage", "side": "teutonic",
                          "args": {"lord_id": "hermann"}})
    assert r["delta"] == 1
    assert r["new_count"] == 1


def test_forage_at_unfriendly_castle_on_town_rejected_in_winter():
    """Enemy Castle overlay on Town with corresponding Conquered marker:
    not friendly for the active Lord (Castle flip and Conquered marker
    are set jointly by Conquest per _apply_conquest_or_liberation)."""
    s = load_scenario("watland", seed=1)
    # narwia is Teutonic territory; place RUSSIAN castle + Conquered
    s.locales["narwia"].russian_castle = True
    s.locales["narwia"].russian_conquered = 1
    _setup_forage(s, "hermann", "narwia")
    with pytest.raises(IllegalAction) as e:
        apply_action(s, {"type": "cmd_forage", "side": "teutonic",
                          "args": {"lord_id": "hermann"}})
    assert e.value.code == "forage_seasonal"


def test_forage_at_town_with_no_castle_rejected_in_winter():
    """No Castle marker: bare Town isn't a Stronghold; non-Summer rejects."""
    s = load_scenario("watland", seed=1)
    _setup_forage(s, "hermann", "narwia")
    with pytest.raises(IllegalAction) as e:
        apply_action(s, {"type": "cmd_forage", "side": "teutonic",
                          "args": {"lord_id": "hermann"}})
    assert e.value.code == "forage_seasonal"


def test_forage_at_fort_in_winter_still_works():
    """Baseline: native Fort Stronghold still permitted in non-Summer
    (regression guard for SMOKE-066 fix)."""
    s = load_scenario("watland", seed=1)
    _setup_forage(s, "hermann", "dorpat")  # Teutonic bishopric
    r = apply_action(s, {"type": "cmd_forage", "side": "teutonic",
                          "args": {"lord_id": "hermann"}})
    assert r["delta"] == 1
