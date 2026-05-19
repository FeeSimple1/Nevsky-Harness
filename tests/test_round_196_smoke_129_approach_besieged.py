"""SMOKE-129 (R196): Approach must not fire on besieged-inside enemies.

Per 4.3.4, Approach triggers when a marching Lord enters a Locale
with enemy Lord(s) NOT in a Stronghold. A besieged-inside enemy
(in_stronghold=True) is already at-bay; the arriving Lord simply
joins the siege.

Pre-fix: _enemies_at returned every mustered enemy at the dest
regardless of in_stronghold, so a Lord marching to join an
existing siege incorrectly triggered a fresh Approach with the
besieged Lord as defender. Surfaced in the Round 195 LLM
self-play of Pleskau: Rudolf marching Lettgallia→Izborsk fired a
spurious Approach with Gavrilo (already Withdrawn-inside) as
target.
"""
from __future__ import annotations

import nevsky.actions  # noqa: F401
from nevsky.actions import apply_action
from nevsky.scenarios import load_scenario


def test_smoke_129_no_approach_against_besieged_enemy():
    """Set up: Russian Gavrilo besieged inside Izborsk; Teutonic
    Rudolf at Lettgallia with a valid March → Izborsk Way.
    Hermann already at Izborsk as besieger. Rudolf's March must
    place him at Izborsk without triggering combat_pending."""
    s = load_scenario("pleskau", seed=1)
    # Place Hermann as the existing besieger at Izborsk.
    s.lords["hermann"].location = "izborsk"
    s.lords["hermann"].in_stronghold = False
    # Gavrilo besieged inside.
    s.lords["gavrilo"].location = "izborsk"
    s.lords["gavrilo"].in_stronghold = True
    # Place a siege marker at Izborsk to make this a real siege.
    s.locales["izborsk"].siege_markers = 1
    # Rudolf mustered at Lettgallia.
    s.lords["rudolf"].state = "mustered"
    s.lords["rudolf"].location = "lettgallia"
    s.lords["rudolf"].in_stronghold = False
    # Set up command-execution context for Rudolf.
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "teutonic"
    s.campaign_turn.active_lord = "rudolf"
    s.campaign_turn.actions_remaining = 2
    s.campaign_turn.in_feed_pay_disband = False
    # Card revealed; just to satisfy any reveal-state invariants
    # we leave next_to_reveal and decks alone.
    res = apply_action(s, {
        "type": "cmd_march", "side": "teutonic",
        "args": {"lord_id": "rudolf", "to": "izborsk"},
    })
    # No Approach: combat_pending must be None.
    assert s.combat_pending is None, (
        f"Approach triggered against besieged enemy; combat_pending="
        f"{s.combat_pending!r}"
    )
    # Rudolf actually moved.
    assert s.lords["rudolf"].location == "izborsk"


def test_smoke_129_approach_still_fires_on_open_enemy():
    """Positive control: enemy Lord in the OPEN at the destination
    must still trigger Approach. Confirms the fix narrows correctly
    and doesn't silence Approach across the board."""
    s = load_scenario("pleskau", seed=1)
    # Place Gavrilo in the open at izborsk (not in stronghold).
    s.lords["gavrilo"].location = "izborsk"
    s.lords["gavrilo"].in_stronghold = False
    # Hermann at ugaunia, marching to izborsk.
    s.lords["hermann"].location = "ugaunia"
    s.lords["hermann"].in_stronghold = False
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "teutonic"
    s.campaign_turn.active_lord = "hermann"
    s.campaign_turn.actions_remaining = 2
    s.campaign_turn.in_feed_pay_disband = False
    apply_action(s, {
        "type": "cmd_march", "side": "teutonic",
        "args": {"lord_id": "hermann", "to": "izborsk"},
    })
    # Approach fires.
    assert s.combat_pending is not None
    assert "gavrilo" in s.combat_pending.defender_lords


def test_smoke_129_marker_present_in_source():
    """Source-marker guardrail."""
    import inspect
    import nevsky.campaign as c
    assert "SMOKE-129" in inspect.getsource(c)
