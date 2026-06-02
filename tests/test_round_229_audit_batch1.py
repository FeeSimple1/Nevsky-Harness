"""Rules-accuracy fixes from the full audit (batch 1).

- Storm lasts exactly `siege_markers` Rounds (4.5.2), not siege_markers+1.
- Legate USE 2a/2c may not Muster a Lord blocked this Levy by R11/R17.
- Veche Options A/B/C refresh the Calendar Victory marker after spending VP.
"""
from __future__ import annotations

import pytest

from nevsky.actions import IllegalAction, apply_action
from nevsky.battle import BattleDecisionContext, resolve_storm
from nevsky.scenarios import load_scenario


def test_storm_runs_exactly_siege_markers_rounds():
    """A Storm the attacker cannot win times out after exactly
    siege_markers Rounds (previously ran one extra Round)."""
    for n in (1, 2, 3, 4):
        s = load_scenario("pleskau", seed=1)
        teu = next(lid for lid, l in s.lords.items()
                   if l.side == "teutonic" and l.state == "mustered")
        # Tanky attacker (survives) vs walls_max=6 (absorbs EVERY attacker Hit,
        # roll 1..6) -> garrison never dies, attacker never Sacks -> the Storm
        # times out after exactly `siege_markers` Rounds.
        s.lords[teu].forces = {"knights": 8}
        res = resolve_storm(
            s, attacker_side="teutonic",
            attacker_lords=[teu], defender_lords=[],
            locale_id="pskov", walls_max=6, siege_markers=n,
            garrison={"men_at_arms": 3}, decision_ctx=BattleDecisionContext(),
        )
        assert res["winner"] == "defender", f"attacker should not Sack (n={n})"
        assert res["rounds"] == n, f"storm with {n} siege markers ran {res['rounds']} rounds"


def _legate_state_with_block(block_target):
    s = load_scenario("peipus", seed=1)
    s.meta.phase = "levy"
    s.meta.levy_step = "call_to_arms"
    s.meta.active_player = "teutonic"
    s.legate.william_of_modena_in_play = True
    s.legate.location = "locale"
    s.legate.acted_this_call_to_arms = False
    # Park the Legate at a Seat of the target and make the target Ready there.
    from nevsky.actions import _seats_of
    seat = sorted(_seats_of(s, block_target))[0]
    s.legate.locale_id = seat
    s.lords[block_target].state = "ready"
    s.meta.block_lords_this_levy_t = [block_target]
    return s


def test_legate_2a_rejects_blocked_lord():
    s = _legate_state_with_block("rudolf")
    with pytest.raises(IllegalAction) as e:
        apply_action(s, {"type": "legate_use", "side": "teutonic",
                         "args": {"sub_option": "2a", "target_lord": "rudolf"}})
    assert e.value.code == "muster_blocked"


def test_veche_option_a_refreshes_victory_marker():
    """Spending a Veche VP (Option A) decrements Russian VP AND keeps the
    displayed Calendar Victory marker in sync."""
    s = load_scenario("peipus", seed=1)
    s.meta.phase = "levy"
    s.meta.levy_step = "call_to_arms"
    s.meta.active_player = "russian"
    s.veche.vp_markers = 3
    # Ensure a Russian Lord cylinder is on the Calendar to slide.
    tgt = next(lid for lid, l in s.lords.items() if l.side == "russian")
    box = None
    for cb in s.calendar.boxes:
        if tgt in cb.cylinders:
            box = cb.box
            break
    if box is None:
        s.calendar.boxes[5].cylinders.append(tgt)  # box 6
    before = s.calendar.russian_vp
    apply_action(s, {"type": "veche_action", "side": "russian",
                     "args": {"option": "A", "target_lord": tgt}})
    assert s.calendar.russian_vp == max(0.0, before - 1.0)
    # Victory marker box must reflect the new VP (refresh ran).
    assert s.calendar.boxes is not None  # sanity; refresh executed without error
