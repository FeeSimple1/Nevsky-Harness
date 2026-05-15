"""SMOKE-064 (Round 69): Sail to enemy Castle (native or Castle marker
overlay) must place a Siege marker.

Previously _h_cmd_sail's inline stronghold-type check used:
  ("commandery", "fort", "city", "novgorod", "bishopric")
omitting "castle" entirely (so Sail to wesenberg etc. silently skipped
the siege placement) and omitting "town" (so a Castle marker overlaid
on a Town via T17 Stonemasons was not recognized as a Stronghold).

The fix routes Sail's siege check through _has_enemy_stronghold_at,
which is now Castle-overlay aware: a teutonic_castle / russian_castle
marker establishes the owner regardless of base type.
"""
from __future__ import annotations

from nevsky.actions import apply_action
from nevsky.scenarios import load_scenario
from nevsky.campaign import _has_enemy_stronghold_at


def _setup_sail_ready(state, lord_id, loc):
    lord = state.lords[lord_id]
    lord.state = "mustered"
    lord.location = loc
    lord.forces = {"knights": 1}
    lord.assets = {"ship": 8}
    state.meta.phase = "campaign"
    state.meta.campaign_step = "command"
    state.meta.active_player = lord.side
    state.campaign_turn.in_feed_pay_disband = False
    state.campaign_turn.next_to_reveal = lord.side
    state.campaign_turn.active_lord = lord_id
    state.campaign_turn.active_card = lord_id
    state.campaign_turn.actions_remaining = 3


def test_sail_to_enemy_castle_overlay_on_town_places_siege():
    s = load_scenario("crusade_on_novgorod", seed=1)
    # narwia is a Town + Seaport in Teutonic territory. Mark it russian_castle
    # so it represents a Russian Castle (Stonemasons overlay).
    s.locales["narwia"].russian_castle = True
    _setup_sail_ready(s, "hermann", "koporye")
    r = apply_action(s, {"type": "cmd_sail", "side": "teutonic",
                         "args": {"lord_id": "hermann", "destination": "narwia"}})
    assert r["placed_siege"] is True
    assert s.locales["narwia"].siege_markers == 1


def test_sail_to_enemy_castle_overlay_on_fort_places_siege():
    """koporye (Fort + Seaport) with russian_castle overlay = enemy Castle."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.locales["koporye"].russian_castle = True
    _setup_sail_ready(s, "hermann", "narwia")
    r = apply_action(s, {"type": "cmd_sail", "side": "teutonic",
                         "args": {"lord_id": "hermann", "destination": "koporye"}})
    assert r["placed_siege"] is True
    assert s.locales["koporye"].siege_markers == 1


def test_sail_to_friendly_castle_overlay_no_siege():
    """Sailing to OWN Castle overlay — no siege placed."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.locales["narwia"].teutonic_castle = True  # Teutons' own Castle
    _setup_sail_ready(s, "hermann", "koporye")
    r = apply_action(s, {"type": "cmd_sail", "side": "teutonic",
                         "args": {"lord_id": "hermann", "destination": "narwia"}})
    assert r["placed_siege"] is False
    assert s.locales["narwia"].siege_markers == 0


def test_has_enemy_stronghold_at_castle_overlay_on_town():
    """_has_enemy_stronghold_at recognizes Castle overlay on non-stronghold base."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.locales["narwia"].russian_castle = True
    assert _has_enemy_stronghold_at(s, "narwia", "teutonic") is True
    assert _has_enemy_stronghold_at(s, "narwia", "russian") is False


def test_has_enemy_stronghold_at_castle_overlay_flips_with_color():
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.locales["narwia"].teutonic_castle = True
    assert _has_enemy_stronghold_at(s, "narwia", "russian") is True
    assert _has_enemy_stronghold_at(s, "narwia", "teutonic") is False
