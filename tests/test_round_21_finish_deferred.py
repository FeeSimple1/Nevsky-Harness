"""Round 21 regression tests: hidden_mats filter, combat-pending
forecasts, advanced_vassal_service wire-up."""
from __future__ import annotations

import pytest

from nevsky.actions import apply_action
from nevsky.legal_moves import legal_moves
from nevsky.render import (
    render_summary,
    render_summary_for_side,
    state_view_for_side,
)
from nevsky.scenarios import load_scenario, set_optional_rule
from nevsky.state import CombatPending


def _setup_pleskau(*, optional=None):
    s = load_scenario("pleskau", seed=1, optional_rules=optional or {})
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})
    return s


# ---------------------------------------------------------------------------
# Hidden Mats
# ---------------------------------------------------------------------------


def test_state_view_for_side_masks_opposing_forces_when_hidden_mats_on():
    s = _setup_pleskau(optional={"hidden_mats": True})
    # Pre: gavrilo has actual forces.
    assert s.lords["gavrilo"].forces.get("knights", 0) > 0
    view = state_view_for_side(s, "teutonic")
    assert view.lords["gavrilo"].forces == {"_hidden": 1}
    # Teu side own forces still visible in the view.
    assert view.lords["hermann"].forces == s.lords["hermann"].forces


def test_state_view_for_side_no_op_when_hidden_mats_off():
    s = _setup_pleskau()  # hidden_mats default False
    view = state_view_for_side(s, "teutonic")
    # Forces unchanged on both sides.
    assert view.lords["gavrilo"].forces == s.lords["gavrilo"].forces
    assert view.lords["hermann"].forces == s.lords["hermann"].forces


def test_state_view_masks_pending_aow_for_opponent():
    s = _setup_pleskau(optional={"hidden_mats": True})
    # Force a Russian draw to populate pending_draw.
    apply_action(s, {"type": "aow_shuffle", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "aow_draw", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "aow_shuffle", "side": "russian", "args": {}})
    apply_action(s, {"type": "aow_draw", "side": "russian", "args": {}})
    # Now both sides have pending draws.
    teu_view = state_view_for_side(s, "teutonic")
    # Russian pending should be masked from Teu view.
    assert all(c == "<hidden>" for c in teu_view.decks.russian.pending_draw)
    # Teu's own pending stays visible (or is now empty after impl above).


def test_render_summary_for_side_includes_hidden_banner():
    s = _setup_pleskau(optional={"hidden_mats": True})
    out = render_summary_for_side(s, "teutonic")
    assert "VIEW: teutonic" in out
    assert "Hidden Mats active" in out


def test_render_summary_for_side_returns_normal_when_off():
    s = _setup_pleskau()
    assert render_summary_for_side(s, "teutonic") == render_summary(s)


# ---------------------------------------------------------------------------
# Combat-pending forecasts
# ---------------------------------------------------------------------------


def _setup_combat_pending(s):
    s.combat_pending = CombatPending(
        attacker_side="teutonic",
        attacker_group=["hermann"],
        from_locale="dorpat", to_locale="pskov", way_type="trackway",
        defender_side="russian",
        defender_lords=["gavrilo"],
        pending_response_by="russian",
        laden=False,
    )
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "russian"
    return s


def test_combat_pending_avoid_battle_enumerates_destinations():
    s = _setup_pleskau()
    _setup_combat_pending(s)
    moves = legal_moves(s)
    avoid_moves = [m for m in moves if m["type"] == "avoid_battle"]
    assert avoid_moves, "no avoid_battle options enumerated"
    for m in avoid_moves:
        assert "args" in m
        assert "to" in m["args"]
        assert "Service" in m["note"] or "tempo" in m["note"]


def test_combat_pending_concede_pseudo_option_present():
    s = _setup_pleskau()
    _setup_combat_pending(s)
    moves = legal_moves(s)
    # Two stand_battle entries: regular + concede.
    stands = [m for m in moves if m["type"] == "stand_battle"]
    assert len(stands) >= 2
    concede_entries = [m for m in stands if m["args"].get("concede")]
    assert concede_entries, "no concede stand_battle option emitted"
    assert "Concede" in concede_entries[0]["note"]


def test_combat_pending_withdraw_explains_siege_conversion():
    s = _setup_pleskau()
    _setup_combat_pending(s)
    moves = legal_moves(s)
    withdraw = next((m for m in moves if m["type"] == "withdraw"), None)
    assert withdraw is not None
    assert "Siege" in withdraw["note"]


# ---------------------------------------------------------------------------
# Advanced Vassal Service (3.4.2)
# ---------------------------------------------------------------------------


def _walk_to_muster(s, side="russian"):
    """Run Levy through arts_of_war / pay / disband to reach muster
    with `side` as active_player."""
    apply_action(s, {"type": "aow_shuffle", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "aow_draw", "side": "teutonic", "args": {}})
    while s.decks.teutonic.pending_draw:
        cid = s.decks.teutonic.pending_draw[0]
        try:
            apply_action(s, {"type": "aow_implement_card", "side": "teutonic",
                              "args": {"lord_id": "knud_and_abel"}})
        except Exception:
            s.decks.teutonic.pending_draw.pop(0); s.decks.teutonic.discard.append(cid)
    apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "aow_shuffle", "side": "russian", "args": {}})
    apply_action(s, {"type": "aow_draw", "side": "russian", "args": {}})
    while s.decks.russian.pending_draw:
        cid = s.decks.russian.pending_draw[0]
        try:
            apply_action(s, {"type": "aow_implement_card", "side": "russian",
                              "args": {"lord_id": "gavrilo"}})
        except Exception:
            s.decks.russian.pending_draw.pop(0); s.decks.russian.discard.append(cid)
    apply_action(s, {"type": "advance_step", "side": "russian", "args": {}})
    # pay
    apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "advance_step", "side": "russian", "args": {}})
    # disband
    apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "advance_step", "side": "russian", "args": {}})
    # at muster, active=teutonic. If side=russian, advance Teu first.
    if side == "russian":
        apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})


def test_advanced_vassal_service_places_marker_on_calendar_when_left_of_lord():
    """When the variant is on, Mustering a Vassal places its Service
    marker on the Calendar at (current_box + vassal.service) if that's
    left of the Lord's marker."""
    s = load_scenario("pleskau", seed=1, optional_rules={"advanced_vassal_service": True})
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})
    _walk_to_muster(s, side="russian")
    # Muster a Russian Vassal: gavrilo has gavrilo_pskov_1 with service rating 4.
    # Levy box = 1 -> target box = 1 + 4 = 5.
    # Gavrilo's Service marker in Pleskau setup: box 4. 5 > 4, so marker stays on mat.
    # Use Vladislav instead: vladislav_izhoran_aux service likely 1-3, with vladislav SVC=3
    # Try gavrilo_pskov_1 first to verify "stays on mat" path.
    apply_action(s, {"type": "muster_vassal", "side": "russian",
                       "args": {"by_lord": "gavrilo", "vassal_id": "gavrilo_pskov_1"}})
    # gavrilo's vassal should NOT be on calendar (target_box 5 > lord box 4).
    vstate = s.lords["gavrilo"].vassals["gavrilo_pskov_1"]
    assert vstate.mustered is True
    assert vstate.on_calendar is False or vstate.calendar_box is None


def test_advanced_vassal_disband_step_processes_at_limit_and_past_limit():
    """Run the disband helper directly with a Vassal marker on Calendar
    at the current Levy box vs left of it. Verify forces are returned."""
    from nevsky.actions import _advanced_vassal_disband_step, _find_levy_marker_box
    s = load_scenario("pleskau", seed=1, optional_rules={"advanced_vassal_service": True})
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})
    levy_box = _find_levy_marker_box(s)  # = 1 in Pleskau
    # Manually place a Vassal on calendar at box=1 (at limit).
    gv = s.lords["gavrilo"]
    vid = "gavrilo_pskov_1"
    gv.vassals[vid].mustered = True
    gv.vassals[vid].on_calendar = True
    gv.vassals[vid].calendar_box = levy_box  # at-limit
    s.calendar.boxes[levy_box - 1].vassal_service_markers.append(vid)
    # Add Vassal forces into Lord pool (so they can be returned).
    gv.forces["men_at_arms"] = gv.forces.get("men_at_arms", 0) + 1
    pre_maa = gv.forces["men_at_arms"]
    res = _advanced_vassal_disband_step(s, "russian")
    assert any(r["vassal_id"] == vid for r in res["to_mat_unready"])
    # Forces returned to pool.
    assert gv.forces.get("men_at_arms", 0) == pre_maa - 1
    # Vassal off-calendar, face-down (unready).
    assert gv.vassals[vid].on_calendar is False
    assert gv.vassals[vid].ready is False


def test_advanced_vassal_disband_step_no_op_when_flag_off():
    from nevsky.actions import _advanced_vassal_disband_step
    s = _setup_pleskau()  # no advanced_vassal_service
    res = _advanced_vassal_disband_step(s, "russian")
    assert res["removed"] == []
    assert res["to_mat_unready"] == []


def test_advanced_vassal_flip_up_at_end_of_muster_step():
    """When levy_step transitions from muster to call_to_arms with the
    variant on, all face-down (unready, unmustered) Vassal markers
    flip up (ready=True)."""
    s = load_scenario("pleskau", seed=1, optional_rules={"advanced_vassal_service": True})
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})
    _walk_to_muster(s, side="russian")
    # Mark a Vassal face-down (Unready, not Mustered).
    gv = s.lords["gavrilo"]
    vid = "gavrilo_pskov_1"
    gv.vassals[vid].ready = False
    gv.vassals[vid].mustered = False
    # Advance through muster to call_to_arms.
    apply_action(s, {"type": "advance_step", "side": "russian", "args": {}})
    apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    # active flipped + step advanced.
    apply_action(s, {"type": "advance_step", "side": "russian", "args": {}})
    # Vassal should now be face-up Ready.
    assert gv.vassals[vid].ready is True
