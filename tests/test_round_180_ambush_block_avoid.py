"""SMOKE-115 (Round 180): T6/R6 Ambush "Block Avoid Battle" mode
was documented as a known feature gap but not implemented.

Per AoW Reference T6/R6 card text: "Play to block Avoid Battle OR
ignore Russian left and right in Battle Round 1". Pre-fix only the
second mode (Round 1 ignore left/right) was wired; the first
(block Avoid Battle) had no harness path.

Implementation adds:
  - `CombatPending.ambush_block_pending: bool` flag
  - `CombatPending.pending_avoid_args: dict` to stage the avoid args
  - `_h_avoid_battle` checks if attacker has the relevant Ambush
    hold (T6 for Teutonic attacker, R6 for Russian); if so, enters
    an interrupt window with attacker active.
  - `play_ambush_block` action: consumes the card, blocks the
    avoid, returns baton to defender for Stand/Withdraw.
  - `decline_ambush_block` action: re-fires avoid_battle with
    a sentinel arg that skips the interrupt check.
"""
from __future__ import annotations

import inspect

import nevsky.actions  # noqa: F401
import nevsky.campaign as camp
import nevsky.state as state_mod


def test_smoke_115_marker_in_avoid_battle():
    src = inspect.getsource(camp._h_avoid_battle)
    assert "SMOKE-115" in src
    assert "ambush_block_pending" in src


def test_smoke_115_play_ambush_block_handler_exists():
    assert hasattr(camp, "_h_play_ambush_block")
    src = inspect.getsource(camp._h_play_ambush_block)
    assert "SMOKE-115" in src
    assert "ambush_blocked" in src


def test_smoke_115_decline_ambush_block_handler_exists():
    assert hasattr(camp, "_h_decline_ambush_block")
    src = inspect.getsource(camp._h_decline_ambush_block)
    assert "SMOKE-115" in src


def test_smoke_115_state_fields_present():
    src = inspect.getsource(state_mod.CombatPending)
    assert "ambush_block_pending" in src
    assert "pending_avoid_args" in src


def test_smoke_115_handlers_registered():
    assert "play_ambush_block" in camp.HANDLERS
    assert "decline_ambush_block" in camp.HANDLERS


def test_smoke_115_t6_in_holds_triggers_interrupt_on_avoid():
    """Behavior: defender declares avoid_battle; if attacker
    (Teutonic) has T6 in holds, an interrupt window opens."""
    from nevsky.actions import apply_action
    from nevsky.scenarios import load_scenario
    s = load_scenario("watland", seed=1)
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "russian"
    rus = next(lid for lid, l in s.lords.items()
               if l.side == "russian" and l.state == "mustered")
    teu = next(lid for lid, l in s.lords.items()
               if l.side == "teutonic" and l.state == "mustered")
    s.lords[rus].location = "izborsk"
    s.lords[teu].location = "pskov"
    s.lords[teu].in_stronghold = False
    s.lords[teu].assets.pop("loot", None)
    s.lords[teu].assets.pop("provender", None)
    s.campaign_turn.active_card = rus
    s.campaign_turn.active_lord = rus
    s.campaign_turn.actions_remaining = 3
    s.combat_pending = None
    # Russian marches into pskov (Teutonic at pskov)
    apply_action(s, {"type": "cmd_march", "side": "russian",
                      "args": {"lord_id": rus, "to": "pskov"}})
    # Combat is pending; defender (teutonic) needs to respond
    assert s.combat_pending is not None
    assert s.combat_pending.pending_response_by == "teutonic"
    # Give Russian attacker R6 (since Russian is attacker here)
    s.decks.russian.holds.append("R6")
    # Find an adjacent locale to pskov for the avoid
    from nevsky.static_data import load_ways
    adj = []
    for w in load_ways():
        if w["a"] == "pskov":
            adj.append(w["b"])
        elif w["b"] == "pskov":
            adj.append(w["a"])
    # Pick first non-Russian non-blocked locale
    dest_options = [x for x in adj if x != "izborsk"]
    if not dest_options:
        return  # skip if no valid dest
    # Teutonic defender attempts avoid
    res = apply_action(s, {"type": "avoid_battle", "side": "teutonic",
                            "args": {"to": dest_options[0]}})
    # Should have entered the interrupt window
    assert res.get("ambush_interrupt") is True
    assert res.get("ambush_card") == "R6"
    assert s.combat_pending.ambush_block_pending is True
    assert s.combat_pending.pending_response_by == "russian"
    assert s.meta.active_player == "russian"


def test_smoke_115_no_interrupt_when_no_ambush_in_holds():
    """If attacker has no Ambush in holds, avoid resolves normally."""
    from nevsky.actions import apply_action
    from nevsky.scenarios import load_scenario
    s = load_scenario("watland", seed=1)
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "russian"
    rus = next(lid for lid, l in s.lords.items()
               if l.side == "russian" and l.state == "mustered")
    teu = next(lid for lid, l in s.lords.items()
               if l.side == "teutonic" and l.state == "mustered")
    s.lords[rus].location = "izborsk"
    s.lords[teu].location = "pskov"
    s.lords[teu].in_stronghold = False
    s.lords[teu].assets.pop("loot", None)
    s.lords[teu].assets.pop("provender", None)
    s.campaign_turn.active_card = rus
    s.campaign_turn.active_lord = rus
    s.campaign_turn.actions_remaining = 3
    s.combat_pending = None
    apply_action(s, {"type": "cmd_march", "side": "russian",
                      "args": {"lord_id": rus, "to": "pskov"}})
    # Russian has NO R6 in holds
    s.decks.russian.holds = [c for c in s.decks.russian.holds if c != "R6"]
    from nevsky.static_data import load_ways
    adj = []
    for w in load_ways():
        if w["a"] == "pskov":
            adj.append(w["b"])
        elif w["b"] == "pskov":
            adj.append(w["a"])
    dest_options = [x for x in adj if x != "izborsk"]
    if not dest_options:
        return
    res = apply_action(s, {"type": "avoid_battle", "side": "teutonic",
                            "args": {"to": dest_options[0]}})
    # Avoid resolves; no interrupt
    assert res.get("ambush_interrupt") is None or res.get("ambush_interrupt") is False
    # combat_pending should be cleared if the avoid succeeded
    if s.combat_pending is not None:
        assert s.combat_pending.ambush_block_pending is False
