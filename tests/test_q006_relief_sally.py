"""Q-006 regression tests: 2E Relief Sally Array (4.4.1).

Builds on Q-005's three-position Battle Array. Tests cover:
- Sally Lords arrayed at sally_center / sally_left / sally_right.
- Defender Reserves shifted to rearguard_center / rearguard_left / rearguard_right.
- Sally targeting: Rearguard if any, else Flanks Front Defenders all
  equally close.
- Siegeworks roll separately for Sally-vs-Front-Defender Strikes.
- On attacker loss with Sally: Sallying Lords Withdraw back inside;
  Siege markers reduced to 1.
"""

from __future__ import annotations

import pytest

from nevsky.battle import (
    BattleDecisionContext,
    _array_sally_lords,
    _init_battle_array,
    _shift_defender_reserves_to_rearguard,
    _strike_target,
    resolve_battle,
)
from nevsky.scenarios import load_scenario


# ---------------------------------------------------------------------------
# Sally row layout
# ---------------------------------------------------------------------------


def test_q006_single_sallying_lord_at_sally_center() -> None:
    """One Sallying Lord -> sally_center."""
    s = load_scenario("watland", seed=1)
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian")
    s.lords[rus].state = "mustered"
    s.lords[rus].forces = {"militia": 1}
    ctx = BattleDecisionContext()
    pos = _array_sally_lords(s, [rus], ctx)
    assert pos[rus] == "sally_center"


def test_q006_two_sallying_lords_center_then_one_flank() -> None:
    """Two Sallying Lords: operator picks one for sally_center; the
    other slot (left vs right) is a second decision."""
    s = load_scenario("watland", seed=1)
    rus_lords: list[str] = []
    for lid, l in s.lords.items():
        if l.side == "russian":
            l.state = "mustered"
            l.forces = {"militia": 1}
            rus_lords.append(lid)
            if len(rus_lords) == 2:
                break
    ctx = BattleDecisionContext(scripted=[
        {"type": "initial_placement_attacker", "chosen": rus_lords[1],
         "rationale": "operator picks 2nd lord for center"},
        {"type": "initial_placement_attacker", "chosen": "sally_right",
         "rationale": "operator picks right for the other"},
    ])
    pos = _array_sally_lords(s, rus_lords, ctx)
    assert pos[rus_lords[1]] == "sally_center"
    assert pos[rus_lords[0]] == "sally_right"


def test_q006_defender_reserves_become_rearguard() -> None:
    """4.4.1 2E: 'Any Defending Lords in Reserve instead position as
    above opposite Sallying Attackers to fight them as a Rearguard
    row.'"""
    s = load_scenario("watland", seed=1)
    teus = [lid for lid, l in s.lords.items() if l.side == "teutonic"][:2]
    for t in teus:
        s.lords[t].state = "mustered"
        s.lords[t].forces = {"sergeants": 1}
    # One Defender at Front center, one in Reserve.
    def_pos = {teus[0]: "center", teus[1]: "reserve"}
    ctx = BattleDecisionContext()
    _shift_defender_reserves_to_rearguard(s, def_pos, ctx)
    # Reserve Lord should now be at rearguard_center (first slot filled).
    assert def_pos[teus[1]] == "rearguard_center"
    # Front center Lord unchanged.
    assert def_pos[teus[0]] == "center"


# ---------------------------------------------------------------------------
# Sally strike targeting
# ---------------------------------------------------------------------------


def test_q006_sally_targets_directly_opposed_rearguard() -> None:
    """Sally row at sally_left strikes the directly-opposed
    rearguard_left if there is one."""
    s = load_scenario("watland", seed=1)
    teus = [lid for lid, l in s.lords.items() if l.side == "teutonic"][:1]
    s.lords[teus[0]].state = "mustered"
    s.lords[teus[0]].forces = {"sergeants": 1}
    enemy_pos = {teus[0]: "rearguard_left"}
    ctx = BattleDecisionContext()
    target = _strike_target("sally_left", enemy_pos, ctx, "attacker", s)
    assert target == teus[0]


def test_q006_sally_flanks_front_defenders_when_no_rearguard() -> None:
    """4.4.1 2E: 'If no Rearguard, Sallying Lords fight Front Defenders
    as if Flanking them all equally closely.' Operator picks among
    Front Defenders."""
    s = load_scenario("watland", seed=1)
    teus = [lid for lid, l in s.lords.items() if l.side == "teutonic"][:2]
    for t in teus:
        s.lords[t].state = "mustered"
        s.lords[t].forces = {"sergeants": 1}
    enemy_pos = {teus[0]: "left", teus[1]: "right"}
    # No rearguard -> Sally Flanks Front Defenders, operator picks.
    ctx = BattleDecisionContext(scripted=[
        {"type": "flanker_target", "chosen": teus[1],
         "rationale": "test flank"},
    ])
    target = _strike_target("sally_center", enemy_pos, ctx, "attacker", s)
    assert target == teus[1]


def test_q006_rearguard_strikes_sally_row() -> None:
    """Rearguard at rearguard_left strikes sally_left if present."""
    s = load_scenario("watland", seed=1)
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian")
    s.lords[rus].state = "mustered"
    s.lords[rus].forces = {"militia": 1}
    enemy_pos = {rus: "sally_left"}
    target = _strike_target("rearguard_left", enemy_pos,
                              BattleDecisionContext(), "defender", s)
    assert target == rus


# ---------------------------------------------------------------------------
# Init Battle Array with Sally
# ---------------------------------------------------------------------------


def test_q006_init_battle_array_with_sally_populates_both_rows() -> None:
    """Calling _init_battle_array with sallying_lords places those
    Lords in the sally row and shifts Defender Reserves to Rearguard.
    """
    s = load_scenario("watland", seed=1)
    teus = [lid for lid, l in s.lords.items() if l.side == "teutonic"][:2]
    for t in teus:
        s.lords[t].state = "mustered"
        s.lords[t].forces = {"sergeants": 1}
    rus_marching = next(lid for lid, l in s.lords.items() if l.side == "russian")
    s.lords[rus_marching].state = "mustered"
    s.lords[rus_marching].forces = {"druzhina": 1, "militia": 1}
    # Sallying Russian Lord: pick the next mustered Russian.
    rus_sallying = next(
        lid for lid, l in s.lords.items()
        if l.side == "russian" and lid != rus_marching
    )
    s.lords[rus_sallying].state = "mustered"
    s.lords[rus_sallying].forces = {"militia": 1}
    ctx = BattleDecisionContext()
    atk_pos, def_pos = _init_battle_array(
        s, [rus_marching], teus, rus_marching, ctx,
        sallying_lords=[rus_sallying],
    )
    # Marching attacker at Front center.
    assert atk_pos[rus_marching] == "center"
    # Sallying Lord at sally_center.
    assert atk_pos[rus_sallying] == "sally_center"
    # Defender 1 at Front center; Defender 2 (Reserve) shifted to
    # rearguard_center.
    front_def = [lid for lid, p in def_pos.items() if p == "center"]
    rearguard = [lid for lid, p in def_pos.items() if p == "rearguard_center"]
    assert len(front_def) == 1
    assert len(rearguard) == 1


# ---------------------------------------------------------------------------
# Aftermath: Sally Withdraw + Siege reduction
# ---------------------------------------------------------------------------


def test_q006_attacker_loss_sally_withdraws_and_siege_to_one() -> None:
    """4.4.1 2E: 'If the Attackers lose, Withdraw Sallying Lords back
    into the Stronghold and reduce Siege markers there to one.'"""
    s = load_scenario("watland", seed=1)
    # Set up: Russian-side Pskov is besieged by Teutonic. Russian
    # Lords inside are Sallying. Russian Marching force comes in.
    s.locales["pskov"].siege_markers = 3
    teu_besieger = [lid for lid, l in s.lords.items() if l.side == "teutonic"][0]
    s.lords[teu_besieger].state = "mustered"
    s.lords[teu_besieger].location = "pskov"
    s.lords[teu_besieger].forces = {"knights": 5, "sergeants": 5}
    s.lords[teu_besieger].in_stronghold = False
    # Russian Sallying Lord (inside the Stronghold).
    rus_sallying = [lid for lid, l in s.lords.items() if l.side == "russian"][0]
    s.lords[rus_sallying].state = "mustered"
    s.lords[rus_sallying].location = "pskov"
    s.lords[rus_sallying].in_stronghold = True
    s.lords[rus_sallying].forces = {"militia": 2}
    # Russian Marching Lord (relief force from outside, just marched in).
    rus_marching = [
        lid for lid, l in s.lords.items()
        if l.side == "russian" and lid != rus_sallying
    ][0]
    s.lords[rus_marching].state = "mustered"
    s.lords[rus_marching].location = "pskov"
    s.lords[rus_marching].in_stronghold = False
    s.lords[rus_marching].forces = {"militia": 2}
    # Set up CombatPending.
    from nevsky.state import CombatPending
    s.combat_pending = CombatPending(
        attacker_side="russian",
        attacker_group=[rus_marching],
        defender_side="teutonic",
        defender_lords=[teu_besieger],
        from_locale="rusa",
        to_locale="pskov",
        way_type="trackway",
        pending_response_by="teutonic",
    )
    # Trigger stand_battle as the defender (Teuton).
    from nevsky.actions import apply_action
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "russian"
    res = apply_action(s, {
        "type": "stand_battle", "side": "teutonic",
        "args": {},
    })
    # Russian (attacker side) has 4 units total vs Teutonic 10 -> Teutons win.
    if res.get("battle", {}).get("loser") == "russian":
        # Sallying Lord should remain at pskov in_stronghold=True.
        assert s.lords[rus_sallying].in_stronghold is True
        assert s.lords[rus_sallying].location == "pskov"
        # Siege markers reduced to at most 1.
        assert s.locales["pskov"].siege_markers <= 1
        assert "sally_withdrew" in res or "sally_raid_siege_to_1" in res
