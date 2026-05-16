"""SMOKE-076 (Round 78): T17 Stonemasons doesn't reject locales that
already have a Castle marker.

Per AoW Reference T17 Tip: "The Castle marker REPLACES the Fort or Town
at its Locale." The replacement is of the base Stronghold (Fort/Town),
not of an existing Castle marker.

The previous _h_cmd_stonemasons unconditionally set teutonic_castle=True
on the target Locale. If a russian_castle marker was already there
(e.g. via initial scenario setup or post-flip-on-Conquest dance), the
build resulted in BOTH russian_castle and teutonic_castle being True
simultaneously — invalid game state. Same problem if a teutonic_castle
was already present (build would be a wasteful no-op but still spend
6 Provender and tick the 2-Castle cap).

Fix: reject the build with code 'castle_exists' when any Castle marker
already overlays the Locale.
"""
from __future__ import annotations

import pytest

import nevsky.actions  # noqa: F401 — register handlers
from nevsky.actions import IllegalAction
from nevsky.campaign import _h_cmd_stonemasons
from nevsky.scenarios import load_scenario


def _setup_hermann_at_fort(s, fort="velikiye_luki"):
    """Place Hermann at a Russian Fort with full command, 6 Provender, T17 tucked."""
    hermann = s.lords["hermann"]
    hermann.location = fort
    hermann.state = "mustered"
    hermann.in_stronghold = False
    hermann.moved_fought = False
    hermann.assets = {"provender": 6}
    hermann.this_lord_capabilities = ["T17"]
    # Clear any Russian Lords at the Fort (Stonemasons requires not under enemy siege).
    for lid, l in s.lords.items():
        if l.side == "russian" and l.location == fort:
            l.location = None
    s.campaign_turn.active_lord = "hermann"
    s.campaign_turn.actions_remaining = 5
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.campaign_turn.in_feed_pay_disband = False
    s.locales[fort].siege_markers = 0
    s.locales[fort].russian_conquered = 0
    s.locales[fort].teutonic_conquered = 0
    s.locales[fort].russian_castle = False
    s.locales[fort].teutonic_castle = False


def test_stonemasons_rejects_when_russian_castle_already_present():
    """A Russian Castle already on the Fort blocks Stonemasons (no
    overlay of two castles)."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    _setup_hermann_at_fort(s)
    s.locales["velikiye_luki"].russian_castle = True
    with pytest.raises(IllegalAction) as e:
        _h_cmd_stonemasons(s, "teutonic", {"lord_id": "hermann"})
    assert e.value.code == "castle_exists"
    # State should be unchanged: russian_castle still True, no teutonic_castle.
    assert s.locales["velikiye_luki"].russian_castle is True
    assert s.locales["velikiye_luki"].teutonic_castle is False


def test_stonemasons_rejects_when_teutonic_castle_already_present():
    """A Teutonic Castle already on the Fort blocks Stonemasons (no
    duplicate own Castle)."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    _setup_hermann_at_fort(s)
    s.locales["velikiye_luki"].teutonic_castle = True
    with pytest.raises(IllegalAction) as e:
        _h_cmd_stonemasons(s, "teutonic", {"lord_id": "hermann"})
    assert e.value.code == "castle_exists"
    # State preserved.
    assert s.locales["velikiye_luki"].teutonic_castle is True


def test_stonemasons_succeeds_at_plain_fort():
    """Regression: Stonemasons still builds at a plain Fort with no
    existing Castle marker."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    _setup_hermann_at_fort(s)
    # No castle markers (default).
    result, _ = _h_cmd_stonemasons(s, "teutonic", {"lord_id": "hermann"})
    assert result["castle_built"] is True
    assert s.locales["velikiye_luki"].teutonic_castle is True
    assert s.locales["velikiye_luki"].russian_castle is False


def test_stonemasons_succeeds_at_plain_town():
    """Regression: Stonemasons builds at a Town in Rus with no existing Castle marker."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    # ostrov is a Town in Rus
    _setup_hermann_at_fort(s, fort="ostrov")
    result, _ = _h_cmd_stonemasons(s, "teutonic", {"lord_id": "hermann"})
    assert result["castle_built"] is True
    assert s.locales["ostrov"].teutonic_castle is True
