"""Round 15 regression tests for LLM-facing interface improvements:
- Card data carries event_text + capability_text (no rules-doc lookup needed).
- render_summary shows Next-expected-action hint and pending-AoW block with text.
- legal_moves emits concrete enumerated entries for muster_lord, muster_vassal,
  levy_transport, levy_capability, plan_add_card, cmd_march, veche_action,
  legate_*.
- lord_combat_summary returns a structured per-Lord combat readout.
"""
from __future__ import annotations

from nevsky.actions import apply_action
from nevsky.legal_moves import legal_moves
from nevsky.render import lord_combat_summary, render_summary
from nevsky.scenarios import load_scenario
from nevsky.static_data import load_cards


def _setup():
    s = load_scenario("pleskau", seed=1)
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})
    return s


def test_card_data_has_event_and_capability_text():
    cards = load_cards()
    # Sample a few key cards.
    for cid in ("T1", "T4", "T9", "T12", "R1", "R8", "R15", "R18"):
        c = cards[cid]
        assert c.get("event_text"), f"{cid} missing event_text"
        assert c.get("capability_text"), f"{cid} missing capability_text"
    # T4 Balistarii capability text references Men-at-Arms / Archery.
    assert "Men-at-Arms" in cards["T4"]["capability_text"] or "Archery" in cards["T4"]["capability_text"]
    # T12 Ordensburgen mentions Commanderies.
    assert "Commanderies" in cards["T12"]["capability_text"]
    # R8 Black Sea Trade mentions Coin.
    assert "Coin" in cards["R8"]["capability_text"]


def test_render_summary_includes_next_expected_action():
    s = _setup()
    out = render_summary(s)
    assert "Next expected:" in out
    # Initially we're at arts_of_war and Teu is to act.
    assert "teutonic:" in out
    assert "aow_shuffle" in out


def test_render_summary_includes_pending_aow_with_card_text():
    s = _setup()
    apply_action(s, {"type": "aow_shuffle", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "aow_draw", "side": "teutonic", "args": {}})
    out = render_summary(s)
    # The pending block should appear with at least one card id and effect text.
    assert "Pending AoW" in out
    assert "EVENT" in out and "CAP" in out
    # The exact cards drawn depend on shuffle order; just verify text is non-empty.
    drawn = s.decks.teutonic.pending_draw
    cards = load_cards()
    for cid in drawn:
        assert cid in out
        assert cards[cid]["event_name"] in out or "—" in out


def test_render_summary_includes_plan_size_at_plan_step():
    s = _setup()
    # Walk to plan step.
    _walk_to_plan(s)
    out = render_summary(s)
    assert "Plan: required=" in out


def test_legal_moves_muster_emits_concrete_actions():
    s = _setup()
    _walk_to_muster(s, side="russian")
    moves = legal_moves(s)
    muster_actions = [m for m in moves if m["type"] == "muster_lord"]
    assert muster_actions, "no muster_lord moves emitted at Muster step"
    # Each entry must have a fully-populated args dict.
    for m in muster_actions:
        assert "args" in m, f"missing args: {m}"
        assert "by_lord" in m["args"]
        assert "target_lord" in m["args"]
        assert "seat" in m["args"]
        assert m.get("note"), f"missing note: {m}"
    # And one of them should target Domash at Novgorod via Gavrilo or Vladislav.
    assert any(
        a["args"]["target_lord"] == "domash" and a["args"]["seat"] == "novgorod"
        for a in muster_actions
    )


def test_legal_moves_plan_emits_concrete_lord_or_pass_options():
    s = _setup()
    _walk_to_plan(s)
    moves = legal_moves(s)
    plan_moves = [m for m in moves if m["type"] == "plan_add_card"]
    # Should include one entry per Mustered Lord on the active side + a pass.
    cards_offered = {m["args"]["card"] for m in plan_moves}
    # Active side is teutonic on first plan call.
    assert "hermann" in cards_offered
    assert "knud_and_abel" in cards_offered
    assert "yaroslav" in cards_offered
    assert "pass" in cards_offered
    # Each entry has a note.
    for m in plan_moves:
        assert m.get("note")


def test_legal_moves_cmd_march_lists_reachable_destinations():
    s = _setup()
    _drive_to_active_lord(s, "hermann")
    moves = legal_moves(s)
    march_moves = [m for m in moves if m["type"] == "cmd_march"]
    assert march_moves, "no cmd_march options enumerated"
    # Hermann at Dorpat — should see ugaunia, odenpah, etc.
    destinations = {m["args"]["to"] for m in march_moves}
    assert "ugaunia" in destinations or "odenpah" in destinations


def test_lord_combat_summary_returns_structured_data():
    s = _setup()
    summary = lord_combat_summary(s, "hermann")
    assert summary["lord_id"] == "hermann"
    assert summary["side"] == "teutonic"
    assert summary["ratings"]["command_base"] == 3
    assert summary["service_disband_box"] == 4  # Pleskau setup
    assert summary["forces"]["knights"] == 1
    assert "battle_strike_hits" in summary
    assert "storm_strike_hits" in summary
    assert summary["battle_strike_hits"]["melee_horse"] > 0


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------


def _implement_or_discard_all(s, side):
    deck = s.decks.teutonic if side == "teutonic" else s.decks.russian
    while deck.pending_draw:
        cid = deck.pending_draw[0]
        c = load_cards()[cid]
        scope = c.get("capability_scope")
        try:
            if scope == "side_wide":
                apply_action(s, {"type": "aow_implement_card", "side": side, "args": {}})
            elif scope == "this_lord":
                pin = "knud_and_abel" if side == "teutonic" else "gavrilo"
                apply_action(s, {"type": "aow_implement_card", "side": side, "args": {"lord_id": pin}})
            else:
                deck.pending_draw.pop(0)
                deck.discard.append(cid)
        except Exception:
            if deck.pending_draw and deck.pending_draw[0] == cid:
                deck.pending_draw.pop(0)
                deck.discard.append(cid)


def _walk_to_muster(s, side="russian"):
    """Run Levy through arts_of_war / pay / disband to reach muster, with side as active_player."""
    apply_action(s, {"type": "aow_shuffle", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "aow_draw", "side": "teutonic", "args": {}})
    _implement_or_discard_all(s, "teutonic")
    apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "aow_shuffle", "side": "russian", "args": {}})
    apply_action(s, {"type": "aow_draw", "side": "russian", "args": {}})
    _implement_or_discard_all(s, "russian")
    apply_action(s, {"type": "advance_step", "side": "russian", "args": {}})
    # pay
    apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "advance_step", "side": "russian", "args": {}})
    # disband
    apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "advance_step", "side": "russian", "args": {}})
    # at muster, active=teutonic. If side=russian, do Teu advance.
    if side == "russian":
        apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})


def _walk_to_plan(s):
    """Run Levy to completion so phase=campaign step=plan."""
    _walk_to_muster(s, side="teutonic")
    # Skip muster.
    apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "advance_step", "side": "russian", "args": {}})
    # call_to_arms
    apply_action(s, {"type": "legate_skip", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "aow_discard_this_levy", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "veche_action", "side": "russian", "args": {"option": "skip"}})
    apply_action(s, {"type": "aow_discard_this_levy", "side": "russian", "args": {}})
    apply_action(s, {"type": "advance_step", "side": "russian", "args": {}})


def _drive_to_active_lord(s, target_lord):
    """Run through plan with target_lord as the first card on Teu's plan, then
    activate Teu's plan until target_lord is the active Lord."""
    _walk_to_plan(s)
    from nevsky.campaign import _plan_target_size
    target = _plan_target_size(s.meta.box)
    plan = [target_lord] + ["pass"] * (target - 1)
    for c in plan:
        apply_action(s, {"type": "plan_add_card", "side": "teutonic", "args": {"card": c}})
    apply_action(s, {"type": "finalize_plan", "side": "teutonic", "args": {}})
    rus_plan = ["gavrilo"] + ["pass"] * (target - 1)
    for c in rus_plan:
        apply_action(s, {"type": "plan_add_card", "side": "russian", "args": {"card": c}})
    apply_action(s, {"type": "finalize_plan", "side": "russian", "args": {}})
    # Reveal until target_lord is active.
    safety = 20
    while safety > 0 and s.campaign_turn.active_lord != target_lord:
        side = s.campaign_turn.next_to_reveal
        apply_action(s, {"type": "command_reveal", "side": side, "args": {}})
        if s.campaign_turn.active_lord == target_lord:
            return
        # If a Lord is active but not target, end_card to advance.
        if s.campaign_turn.active_lord:
            try:
                apply_action(s, {"type": "cmd_pass", "side": side, "args": {"lord_id": s.campaign_turn.active_lord}})
            except Exception:
                pass
        safety -= 1
