"""Follow-up C regression tests: Adjust Rows mid-Relief-Sally
(4.4.2 page 15, 2E).

Tests the four Adjust Rows sub-rules:
  1. No Sallying remain -> Rearguard becomes Reserve.
  2. No Rearguard -> Sallying Lords Flank Defenders. (Already covered
     by _strike_target; verified in test_q006.)
  3. No Front Defenders -> Rearguard faces about as Front.
  4. No Front Attackers -> Defender Front -> Reserve (Rearguard stays
     and engages Sally).
"""

from __future__ import annotations

import pytest

from nevsky.battle import _adjust_rows_for_relief_sally
from nevsky.scenarios import load_scenario


def test_adjust_rows_no_sallying_remain_rearguard_to_reserve() -> None:
    """Rule 1: 'If no Sallying Lords remain, Rearguard becomes Reserve.'"""
    s = load_scenario("watland", seed=1)
    teus = [lid for lid, l in s.lords.items() if l.side == "teutonic"][:2]
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian")
    for t in teus:
        s.lords[t].state = "mustered"
        s.lords[t].forces = {"sergeants": 1}
    # Sally row Lord exists in state but has 0 Forces (Routed).
    s.lords[rus].state = "mustered"
    s.lords[rus].forces = {}  # Routed
    atk_pos = {rus: "sally_center"}
    def_pos = {teus[0]: "center", teus[1]: "rearguard_center"}
    transitions = _adjust_rows_for_relief_sally(s, atk_pos, def_pos)
    # Rearguard Lord moves to reserve.
    assert def_pos[teus[1]] == "reserve"
    assert any(t["rule"] == "no_sally_remain" for t in transitions)


def test_adjust_rows_no_front_defenders_rearguard_to_front() -> None:
    """Rule 3: 'If no Front Defenders, Rearguard faces about as Front.'"""
    s = load_scenario("watland", seed=1)
    teus = [lid for lid, l in s.lords.items() if l.side == "teutonic"][:2]
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian")
    s.lords[rus].state = "mustered"
    s.lords[rus].forces = {"militia": 1}
    for t in teus:
        s.lords[t].state = "mustered"
    # Front Defender Routed (no Forces).
    s.lords[teus[0]].forces = {}
    s.lords[teus[1]].forces = {"sergeants": 1}
    atk_pos = {rus: "sally_center"}
    def_pos = {teus[0]: "center", teus[1]: "rearguard_center"}
    transitions = _adjust_rows_for_relief_sally(s, atk_pos, def_pos)
    # Rearguard Lord becomes Front center.
    assert def_pos[teus[1]] == "center"
    assert any(t["rule"] == "no_front_defenders" for t in transitions)


def test_adjust_rows_no_front_attackers_defender_front_to_reserve() -> None:
    """Rule 4: 'If no Front Attackers, ... original Front Defenders
    face about as Reserve.'"""
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic")
    rus_lords: list[str] = []
    for lid, l in s.lords.items():
        if l.side == "russian":
            l.state = "mustered"
            l.forces = {"militia": 1}
            rus_lords.append(lid)
            if len(rus_lords) == 2:
                break
    s.lords[teu].state = "mustered"
    # Front Attacker Routed.
    s.lords[teu].forces = {}
    atk_pos = {teu: "center"}
    def_pos = {rus_lords[0]: "center", rus_lords[1]: "rearguard_center"}
    # Need at least one Sally Lord to mark this as Relief Sally.
    teu2 = next(
        lid for lid, l in s.lords.items()
        if l.side == "teutonic" and lid != teu
    )
    s.lords[teu2].state = "mustered"
    s.lords[teu2].forces = {"sergeants": 1}
    atk_pos[teu2] = "sally_center"
    transitions = _adjust_rows_for_relief_sally(s, atk_pos, def_pos)
    # Defender Front Lord goes to reserve.
    assert def_pos[rus_lords[0]] == "reserve"
    assert any(t["rule"] == "no_front_attackers" for t in transitions)


def test_adjust_rows_no_op_when_not_relief_sally() -> None:
    """Outside Relief Sally (no sally_* / rearguard_* positions),
    Adjust Rows is a no-op."""
    s = load_scenario("watland", seed=1)
    teus = [lid for lid, l in s.lords.items() if l.side == "teutonic"][:1]
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian")
    s.lords[teus[0]].state = "mustered"
    s.lords[teus[0]].forces = {"sergeants": 1}
    s.lords[rus].state = "mustered"
    s.lords[rus].forces = {"militia": 1}
    atk_pos = {teus[0]: "center"}
    def_pos = {rus: "center"}
    transitions = _adjust_rows_for_relief_sally(s, atk_pos, def_pos)
    assert transitions == []


def test_adjust_rows_all_three_rearguard_slots_promote_to_front() -> None:
    """When all three Front Defenders Routed and three Rearguard Lords
    exist, all three rearguard_left/center/right -> left/center/right."""
    s = load_scenario("watland", seed=1)
    teus = [lid for lid, l in s.lords.items() if l.side == "teutonic"][:6]
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian")
    s.lords[rus].state = "mustered"
    s.lords[rus].forces = {"militia": 1}
    for t in teus:
        s.lords[t].state = "mustered"
    # All three Front Defenders Routed.
    for i in (0, 1, 2):
        s.lords[teus[i]].forces = {}
    # Three Rearguard Defenders alive.
    for i in (3, 4, 5):
        s.lords[teus[i]].forces = {"sergeants": 1}
    atk_pos = {rus: "sally_center"}
    def_pos = {
        teus[0]: "left", teus[1]: "center", teus[2]: "right",
        teus[3]: "rearguard_left", teus[4]: "rearguard_center", teus[5]: "rearguard_right",
    }
    _adjust_rows_for_relief_sally(s, atk_pos, def_pos)
    assert def_pos[teus[3]] == "left"
    assert def_pos[teus[4]] == "center"
    assert def_pos[teus[5]] == "right"
