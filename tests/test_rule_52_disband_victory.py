"""Rule 5.2 Campaign Victory must fire when a side's FINAL Mustered Lord
leaves the map via an at-limit Service Disband (3.3.2), identically to a
permanent removal (3.3.1).

Regression for the bug report: a side could lose its last Mustered Lord
through an ordinary service-limit Disband while the Campaign stayed live
and kept accepting actions. The fix funnels every Lord-removal path through
the shared _apply_immediate_campaign_victory check.

Also covers two no-op-loop fixes flagged in the same report:
  - legate_skip must not stay selectable/executable once the Legate has
    acted this Call to Arms.
  - disband_resolve must not stay selectable once no Disband would fire.
"""

from __future__ import annotations

import pytest

from nevsky.actions import (
    IllegalAction,
    _disband_at_limit,
    _remove_lord_permanently,
    apply_action,
)
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import determine_scenario_winner, load_scenario
from nevsky.state import GameState
from nevsky.static_data import load_lords


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _into_campaign(s: GameState) -> None:
    s.meta.phase = "campaign"            # type: ignore[assignment]
    s.meta.campaign_step = "command"     # type: ignore[assignment]


def _mustered(s: GameState, side: str) -> list[str]:
    return [lid for lid, l in s.lords.items()
            if l.side == side and l.state == "mustered"]


def _keep_only(s: GameState, side: str, n: int) -> list[str]:
    """Leave exactly `n` Mustered Lords on `side`; set the rest Ready."""
    ids = _mustered(s, side)
    assert len(ids) >= n
    for lid in ids[n:]:
        s.lords[lid].state = "ready"     # type: ignore[assignment]
    return ids[:n]


def _levy_box(s: GameState) -> int:
    for cb in s.calendar.boxes:
        if cb.has_levy_campaign_marker:
            return cb.box
    raise AssertionError("no Levy/Campaign marker on Calendar")


def _service_to(s: GameState, lid: str, box: int) -> None:
    for cb in s.calendar.boxes:
        if lid in cb.service_markers:
            cb.service_markers.remove(lid)
    for roster in (s.calendar.off_left_service, s.calendar.off_right_service):
        if lid in roster:
            roster.remove(lid)
    if 1 <= box <= 16:
        s.calendar.boxes[box - 1].service_markers.append(lid)
    elif box < 1:
        s.calendar.off_left_service.append(lid)
    else:
        s.calendar.off_right_service.append(lid)


# --------------------------------------------------------------------------
# Case 1: final Teutonic Lord disbands at Service limit -> Russia wins
# --------------------------------------------------------------------------
def test_case1_final_teutonic_disband_russia_wins() -> None:
    s = load_scenario("pleskau", seed=1)
    _into_campaign(s)
    (keep,) = _keep_only(s, "teutonic", 1)
    assert len(_mustered(s, "teutonic")) == 1

    _disband_at_limit(s, keep, 9)

    assert s.lords[keep].state == "disbanded"
    assert len(_mustered(s, "teutonic")) == 0
    # campaign is terminal
    assert s.meta.phase == "campaign" and s.meta.campaign_step == "done"
    w = determine_scenario_winner(s)
    assert w["winner"] == "russian"
    assert w["applied_override"] == "campaign_victory"
    # terminal outcome recorded on the single game_over flag
    assert s.meta.game_over is True
    assert s.meta.winner == "russian"
    assert s.meta.victory_reason and "5.2" in s.meta.victory_reason
    # no further actions accepted
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "end_card", "side": "russian", "args": {}})
    assert exc.value.code == "game_over"


# --------------------------------------------------------------------------
# Case 2: final Russian Lord disbands at Service limit -> Teutons win
# --------------------------------------------------------------------------
def test_case2_final_russian_disband_teutons_win() -> None:
    s = load_scenario("pleskau", seed=1)
    _into_campaign(s)
    (keep,) = _keep_only(s, "russian", 1)
    assert len(_mustered(s, "russian")) == 1

    _disband_at_limit(s, keep, 9)

    assert s.lords[keep].state == "disbanded"
    assert len(_mustered(s, "russian")) == 0
    assert s.meta.phase == "campaign" and s.meta.campaign_step == "done"
    w = determine_scenario_winner(s)
    assert w["winner"] == "teutonic"
    assert w["applied_override"] == "campaign_victory"
    assert s.meta.game_over is True
    assert s.meta.winner == "teutonic"
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "end_card", "side": "teutonic", "args": {}})
    assert exc.value.code == "game_over"


# --------------------------------------------------------------------------
# Case 3: one Lord disbands but another remains -> campaign stays active
# --------------------------------------------------------------------------
def test_case3_one_disbands_other_remains_active() -> None:
    s = load_scenario("pleskau", seed=1)
    _into_campaign(s)
    keep = _keep_only(s, "teutonic", 2)
    assert len(keep) == 2

    _disband_at_limit(s, keep[0], 9)

    assert s.lords[keep[0]].state == "disbanded"
    assert s.lords[keep[1]].state == "mustered"
    # NOT terminal
    assert s.meta.campaign_step == "command"
    assert len(_mustered(s, "teutonic")) >= 1
    assert len(_mustered(s, "russian")) >= 1


# --------------------------------------------------------------------------
# Case 4: Disband during Campaign FPD must NOT advance phase/calendar
# --------------------------------------------------------------------------
def test_case4_fpd_resolve_does_not_advance_after_final_disband() -> None:
    s = load_scenario("pleskau", seed=1)
    _into_campaign(s)
    (keep,) = _keep_only(s, "teutonic", 1)
    box_before = s.meta.box
    lb = _levy_box(s)
    _service_to(s, keep, lb)            # at limit -> Disband fires
    s.lords[keep].assets = {}           # no payable resource -> no Pay window
    s.lords[keep].moved_fought = False

    # enter the 4.8 Feed/Pay/Disband sub-step for Teutonic
    s.campaign_turn.in_feed_pay_disband = True
    s.campaign_turn.fpd_completed_t = False
    s.campaign_turn.fpd_completed_r = False
    s.campaign_turn.fpd_pay_window_side = None
    s.meta.active_player = "teutonic"

    res = apply_action(s, {"type": "fpd_resolve", "side": "teutonic", "args": {}})

    assert res.get("game_over") is True
    assert res.get("advanced") is False
    # terminal, and the engine did NOT move on
    assert s.meta.phase == "campaign" and s.meta.campaign_step == "done"
    assert s.meta.box == box_before            # calendar did not advance
    assert s.campaign_turn.fpd_completed_t is False   # side not marked complete
    w = determine_scenario_winner(s)
    assert w["winner"] == "russian"
    assert w["applied_override"] == "campaign_victory"
    assert s.meta.game_over is True


# --------------------------------------------------------------------------
# Case 5: existing permanent-removal path still triggers 5.2
# --------------------------------------------------------------------------
def test_case5_permanent_removal_last_lord_still_wins() -> None:
    s = load_scenario("pleskau", seed=1)
    _into_campaign(s)
    (keep,) = _keep_only(s, "russian", 1)
    static = load_lords()

    _remove_lord_permanently(s, keep, static[keep])

    assert s.lords[keep].state == "removed"
    assert s.meta.phase == "campaign" and s.meta.campaign_step == "done"
    w = determine_scenario_winner(s)
    assert w["winner"] == "teutonic"
    assert w["applied_override"] == "campaign_victory"


# --------------------------------------------------------------------------
# Parity: at-limit Disband and permanent removal end the game identically
# --------------------------------------------------------------------------
def test_disband_and_removal_parity() -> None:
    s1 = load_scenario("pleskau", seed=1)
    _into_campaign(s1)
    (k1,) = _keep_only(s1, "teutonic", 1)
    _disband_at_limit(s1, k1, 9)

    s2 = load_scenario("pleskau", seed=1)
    _into_campaign(s2)
    (k2,) = _keep_only(s2, "teutonic", 1)
    _remove_lord_permanently(s2, k2, load_lords()[k2])

    w1 = determine_scenario_winner(s1)
    w2 = determine_scenario_winner(s2)
    assert (s1.meta.campaign_step == "done") == (s2.meta.campaign_step == "done") == True
    assert w1["winner"] == w2["winner"] == "russian"
    assert w1["applied_override"] == w2["applied_override"] == "campaign_victory"


# --------------------------------------------------------------------------
# 5.2 is Campaign-only: an at-limit Disband during Levy does not end the game
# --------------------------------------------------------------------------
def test_disband_during_levy_does_not_trigger_5_2() -> None:
    s = load_scenario("pleskau", seed=1)
    # stay in Levy phase
    (keep,) = _keep_only(s, "teutonic", 1)
    _disband_at_limit(s, keep, 9)
    assert s.lords[keep].state == "disbanded"
    # Levy phase: no Campaign Victory short-circuit
    assert s.meta.phase == "levy"
    assert s.meta.campaign_step != "done"


# --------------------------------------------------------------------------
# No-op fix: legate_skip
# --------------------------------------------------------------------------
def test_legate_skip_rejected_after_acting() -> None:
    s = load_scenario("pleskau", seed=1)
    s.meta.phase = "levy"                       # type: ignore[assignment]
    s.meta.levy_step = "call_to_arms"           # type: ignore[assignment]
    s.meta.active_player = "teutonic"
    s.legate.acted_this_call_to_arms = False

    apply_action(s, {"type": "legate_skip", "side": "teutonic", "args": {}})
    assert s.legate.acted_this_call_to_arms is True

    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "legate_skip", "side": "teutonic", "args": {}})
    assert exc.value.code == "already_acted"


def test_legate_skip_not_offered_after_acting() -> None:
    s = load_scenario("pleskau", seed=1)
    s.meta.phase = "levy"                       # type: ignore[assignment]
    s.meta.levy_step = "call_to_arms"           # type: ignore[assignment]
    s.meta.active_player = "teutonic"
    s.legate.acted_this_call_to_arms = False

    assert "legate_skip" in {m["type"] for m in legal_moves(s)}
    s.legate.acted_this_call_to_arms = True
    assert "legate_skip" not in {m["type"] for m in legal_moves(s)}


# --------------------------------------------------------------------------
# No-op fix: disband_resolve
# --------------------------------------------------------------------------
def test_disband_resolve_only_offered_when_pending() -> None:
    s = load_scenario("pleskau", seed=1)
    s.meta.phase = "levy"                       # type: ignore[assignment]
    s.meta.levy_step = "disband"                # type: ignore[assignment]
    s.meta.active_player = "teutonic"
    lb = _levy_box(s)

    # push every Teutonic Service marker right of the Levy box -> no Disband
    for lid in _mustered(s, "teutonic"):
        _service_to(s, lid, 16)
    assert "disband_resolve" not in {m["type"] for m in legal_moves(s)}

    # one Lord at the limit -> the action reappears
    keep = _mustered(s, "teutonic")[0]
    _service_to(s, keep, lb)
    assert "disband_resolve" in {m["type"] for m in legal_moves(s)}


# --------------------------------------------------------------------------
# No-op fix: disband_resolve repeat is rejected (strict reading)
# --------------------------------------------------------------------------
def test_disband_resolve_repeat_rejected() -> None:
    """A side resolves Disband in one pass; a second disband_resolve in the
    same Disband step is a no-op loop and is rejected."""
    s = load_scenario("pleskau", seed=1)
    s.meta.phase = "levy"                       # type: ignore[assignment]
    s.meta.levy_step = "disband"                # type: ignore[assignment]
    s.meta.active_player = "teutonic"
    s.meta.disband_resolved_t = False

    apply_action(s, {"type": "disband_resolve", "side": "teutonic", "args": {}})
    assert s.meta.disband_resolved_t is True

    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "disband_resolve", "side": "teutonic", "args": {}})
    assert exc.value.code == "already_resolved"


def test_disband_resolved_latch_resets_each_disband_step() -> None:
    """Advancing into a fresh Disband step clears the per-side latch so the
    next Levy's Disband can be resolved again."""
    s = load_scenario("pleskau", seed=1)
    s.meta.phase = "levy"                       # type: ignore[assignment]
    s.meta.levy_step = "pay"                    # type: ignore[assignment]
    s.meta.active_player = "teutonic"
    s.meta.disband_resolved_t = True            # stale from a prior step
    s.meta.disband_resolved_r = True
    # advance pay -> disband (T then R) re-enters the Disband step
    apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "advance_step", "side": "russian", "args": {}})
    assert s.meta.levy_step == "disband"
    assert s.meta.disband_resolved_t is False
    assert s.meta.disband_resolved_r is False


# --------------------------------------------------------------------------
# 5.3 End of Scenario also sets the terminal flag and records the winner
# --------------------------------------------------------------------------
def test_end_of_scenario_sets_game_over_and_records_winner() -> None:
    s = load_scenario("pleskau", seed=1)
    # both sides keep Mustered Lords -> this is a 5.3 VP end, not 5.2
    assert len(_mustered(s, "teutonic")) >= 1
    assert len(_mustered(s, "russian")) >= 1
    s.meta.phase = "campaign"                   # type: ignore[assignment]
    s.meta.campaign_step = "end_campaign"       # type: ignore[assignment]
    s.meta.box = s.meta.span_end_box            # final 40-Days
    s.meta.active_player = "teutonic"
    s.meta.end_campaign_completed_t = False
    s.meta.end_campaign_completed_r = False
    s.calendar.teutonic_vp = 3.0
    s.calendar.russian_vp = 1.0

    apply_action(s, {"type": "end_campaign_resolve", "side": "teutonic", "args": {}})
    res = apply_action(s, {"type": "end_campaign_resolve", "side": "russian", "args": {}})

    assert res.get("game_over") is True
    assert s.meta.game_over is True
    assert s.meta.campaign_step == "done"
    assert s.meta.winner in ("teutonic", "russian", "draw")
    assert s.meta.victory_reason
    # engine is now terminal: no further actions
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "end_card", "side": "teutonic", "args": {}})
    assert exc.value.code == "game_over"
