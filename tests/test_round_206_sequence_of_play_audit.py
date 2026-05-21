"""Round 206: Sequence-of-Play clause-by-clause audit findings.

SMOKE-143: Legate Command bonus (4.2) was not implemented; campaign.py
even asserted "there is no separate Legate +1 Command rule." Per the
Misc Rules Reference (4.2 LEGATE) and Sequence of Play, a Teutonic Lord
starting his card co-located with the on-map Legate may add +1 Command
action; the pawn returns to William of Modena only when the extra action
is actually used.

SMOKE-144: the 4.8.1 Unfed penalty shifted the Lord's Service marker left
but, under the advanced_vassal_service optional rule (3.4.2), failed to
cascade the shift to his on-Calendar Vassal markers (Pay already did).
"""
from __future__ import annotations

from nevsky.actions import IllegalAction, apply_action
import nevsky.campaign as camp
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import load_scenario
from nevsky.state import GameState


def _types(s: GameState, side: str) -> set[str]:
    return {m["type"] for m in legal_moves(s, with_previews=False) if m.get("side") == side}


def _setup_legate(seed: int = 1):
    s = load_scenario("crusade_on_novgorod", seed=seed)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    loc = s.lords[teu].location
    s.legate.william_of_modena_in_play = True
    s.legate.location = "locale"
    s.legate.locale_id = loc
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "teutonic"
    s.campaign_turn.active_lord = teu
    s.campaign_turn.next_to_reveal = "teutonic"
    s.campaign_turn.in_feed_pay_disband = False
    base = camp._effective_command_rating(s, teu)
    s.campaign_turn.actions_remaining = base
    s.campaign_turn.actions_used_this_card = 0
    s.campaign_turn.legate_bonus_available = True
    s.campaign_turn.legate_bonus_elected = False
    s.campaign_turn.legate_bonus_base = 0
    return s, teu, base


# --- SMOKE-143 Legate Command bonus --------------------------------------

def test_legate_bonus_enumerated_and_grants_action():
    s, teu, base = _setup_legate()
    assert "legate_command_bonus" in _types(s, "teutonic")
    r = apply_action(s, {"type": "legate_command_bonus", "side": "teutonic",
                         "args": {"lord_id": teu}})
    assert s.campaign_turn.actions_remaining == base + 1
    assert s.campaign_turn.legate_bonus_elected is True
    assert s.legate.location == "locale"  # pawn not yet removed


def test_legate_bonus_pawn_returns_when_extra_action_used():
    s, teu, base = _setup_legate()
    apply_action(s, {"type": "legate_command_bonus", "side": "teutonic",
                     "args": {"lord_id": teu}})
    camp._consume_actions(s, base + 1)  # spend the whole enlarged card
    assert s.legate.location == "card"
    assert s.legate.locale_id is None


def test_legate_bonus_pawn_stays_when_extra_action_unused():
    s, teu, base = _setup_legate()
    apply_action(s, {"type": "legate_command_bonus", "side": "teutonic",
                     "args": {"lord_id": teu}})
    camp._consume_actions(s, base)  # used only base; one (extra) action left
    apply_action(s, {"type": "cmd_pass", "side": "teutonic", "args": {"lord_id": teu}})
    assert s.legate.location == "locale"  # wasted election keeps the pawn


def test_legate_bonus_unavailable_when_not_co_located():
    s, teu, base = _setup_legate()
    s.campaign_turn.legate_bonus_available = False  # did not start co-located
    assert "legate_command_bonus" not in _types(s, "teutonic")
    try:
        apply_action(s, {"type": "legate_command_bonus", "side": "teutonic",
                         "args": {"lord_id": teu}})
        raise AssertionError("expected legate_unavailable")
    except IllegalAction as e:
        assert str(e.args[0]).startswith("legate_unavailable")


def test_legate_bonus_cannot_be_taken_twice():
    s, teu, base = _setup_legate()
    apply_action(s, {"type": "legate_command_bonus", "side": "teutonic",
                     "args": {"lord_id": teu}})
    try:
        apply_action(s, {"type": "legate_command_bonus", "side": "teutonic",
                         "args": {"lord_id": teu}})
        raise AssertionError("expected already_elected")
    except IllegalAction as e:
        assert str(e.args[0]).startswith("already_elected")


# --- SMOKE-144 Unfed penalty cascades to Calendar Vassals ----------------

def test_unfed_penalty_cascades_vassal_markers_left():
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.optional_rules["advanced_vassal_service"] = True
    # Pick a Teutonic Lord with at least one vassal; put one vassal on the
    # Calendar at a known box, and force the Lord Unfed in FPD.
    lord_id = next(lid for lid, l in s.lords.items()
                   if l.side == "teutonic" and l.state == "mustered" and l.vassals)
    vid = next(iter(s.lords[lord_id].vassals))
    vstate = s.lords[lord_id].vassals[vid]
    vstate.on_calendar = True
    vstate.calendar_box = 5
    s.calendar.boxes[4].vassal_service_markers.append(vid)
    # Place the Lord's Service marker somewhere it can shift left.
    for cb in s.calendar.boxes:
        if lord_id in cb.service_markers:
            cb.service_markers.remove(lord_id)
    s.calendar.boxes[7].service_markers.append(lord_id)  # box 8
    # Force Unfed: MOVED_FOUGHT with units but zero Provender/Loot anywhere.
    s.lords[lord_id].moved_fought = True
    s.lords[lord_id].forces.clear()
    s.lords[lord_id].forces["sergeants"] = 2  # 2 units -> needs 1 feed
    s.lords[lord_id].assets.pop("provender", None)
    s.lords[lord_id].assets.pop("loot", None)
    for l in s.lords.values():  # no co-located helper provender
        if l.side == "teutonic" and l.location == s.lords[lord_id].location:
            l.assets.pop("provender", None)
            l.assets.pop("loot", None)
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "teutonic"
    s.campaign_turn.in_feed_pay_disband = True
    s.campaign_turn.fpd_completed_t = False
    s.campaign_turn.fpd_completed_r = False
    apply_action(s, {"type": "fpd_resolve", "side": "teutonic", "args": {}})
    # Lord shifted 8 -> 7; vassal must have cascaded 5 -> 4.
    assert vstate.calendar_box == 4
    assert vid in s.calendar.boxes[3].vassal_service_markers
    assert vid not in s.calendar.boxes[4].vassal_service_markers
