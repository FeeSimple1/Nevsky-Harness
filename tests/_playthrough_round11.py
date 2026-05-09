"""TEST FIXTURE / engine-soundness smoke driver — NOT part of the shipped harness.

Round 11 smoke: exercise Q-005 / Q-006 / Storm Reposition / Adjust
Rows in scenarios that drive lots of combat."""

from __future__ import annotations

import sys
from typing import Any

sys.path.insert(0, "src")

from nevsky.actions import IllegalAction, apply_action
from nevsky.battle import (
    BattleDecisionContext,
    _adjust_rows_for_relief_sally,
    _init_battle_array,
    _strike_target,
    resolve_battle,
    resolve_storm,
)
from nevsky.scenarios import load_scenario
from nevsky.state import CombatPending


def _make_relief_sally_setup():
    """Construct a Relief Sally scenario:
    - Pskov (Russian city) Besieged by Teutons (3 Siege markers).
    - Russian Lords inside Pskov stronghold (Sallying).
    - Russian Lord marching from neighbor (relief force).
    - Multiple Defenders (Teutons) so Reserves shift to Rearguard.
    """
    s = load_scenario("watland", seed=1)
    s.locales["pskov"].siege_markers = 3
    teu_lords = [lid for lid, l in s.lords.items() if l.side == "teutonic"]
    rus_lords = [lid for lid, l in s.lords.items() if l.side == "russian"]
    # Two Teuton defenders at pskov (besiegers).
    for i, lid in enumerate(teu_lords[:2]):
        s.lords[lid].state = "mustered"
        s.lords[lid].location = "pskov"
        s.lords[lid].in_stronghold = False
        s.lords[lid].forces = {"knights": 4, "sergeants": 4}
    # One Russian Lord inside Pskov stronghold (Sallying). Bulk
    # forces with Armored units so he survives Round 1 and gets to
    # strike back.
    s.lords[rus_lords[0]].state = "mustered"
    s.lords[rus_lords[0]].location = "pskov"
    s.lords[rus_lords[0]].in_stronghold = True
    s.lords[rus_lords[0]].forces = {"knights": 4, "men_at_arms": 4, "militia": 4}
    # One Russian Lord marching in (relief force). Bulk similarly.
    s.lords[rus_lords[1]].state = "mustered"
    s.lords[rus_lords[1]].location = "pskov"
    s.lords[rus_lords[1]].in_stronghold = False
    s.lords[rus_lords[1]].forces = {"knights": 6, "men_at_arms": 4, "militia": 2}
    return s, teu_lords[:2], rus_lords[:2]


def smoke_relief_sally_full_battle():
    """Run a full Relief Sally Battle through resolve_battle. Verify
    sally_*/rearguard_* positions populate, Battle resolves, decisions
    trace is recorded.
    """
    s, teus, rus = _make_relief_sally_setup()
    rus_marching = rus[1]
    rus_sallying = rus[0]
    ctx = BattleDecisionContext()
    res = resolve_battle(
        s, attacker_side="russian",
        attacker_lords=[rus_marching, rus_sallying],
        defender_lords=teus,
        active_attacker=rus_marching,
        decision_ctx=ctx,
        sallying_lords=[rus_sallying],
        siegeworks_for_sally=3,
    )
    print("--- Relief Sally Battle ---")
    print(f"  rounds: {res['rounds']}")
    print(f"  winner: {res['winner']}, loser: {res['loser']}")
    print(f"  attacker positions: {res['attacker_positions']}")
    print(f"  defender positions: {res['defender_positions']}")
    print(f"  decisions logged: {len(res['decisions'])}")
    # Verify Sally placement: either alive at sally_center, or Routed.
    pos = res["attacker_positions"].get(rus_sallying)
    assert pos in ("sally_center", "routed"), f"unexpected pos {pos!r}"
    # Verify Defender Reserve shifted to Rearguard.
    rearguard = [
        lid for lid, p in res["defender_positions"].items()
        if p.startswith("rearguard_")
    ]
    print(f"  rearguard Lords: {rearguard}")
    print(f"  log rounds: {len(res['log'])}")
    # Look for a Sally striker hitting a target via the per_striker log.
    sally_strikes = []
    for rd in res["log"]:
        for step in rd["steps"]:
            for ps in step.get("per_striker", []):
                if ps["striker_slot"].startswith("sally_"):
                    sally_strikes.append(ps)
    print(f"  total Sally strikes recorded: {len(sally_strikes)}")
    # Look for siegeworks_vs_sally absorptions.
    siege_walls = []
    for rd in res["log"]:
        for step in rd["steps"]:
            for d in step.get("distribution", []):
                if d.get("target") == "siegeworks_vs_sally":
                    siege_walls.append(d)
    print(f"  Siegeworks-vs-Sally absorptions: {len(siege_walls)}")
    return res


def smoke_storm_reposition_multi_round():
    """Storm with multiple attackers; force a swap via scripted
    decision; verify Front Lord changes between rounds."""
    s = load_scenario("watland", seed=1)
    teus = [lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered"][:2]
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian")
    s.lords[rus].state = "mustered"
    s.lords[rus].location = "pskov"
    s.lords[rus].in_stronghold = True
    s.lords[rus].forces = {"men_at_arms": 1, "militia": 1}
    for t in teus:
        s.lords[t].location = "pskov"
        s.lords[t].forces = {"knights": 8, "sergeants": 4}
    ctx = BattleDecisionContext(scripted=[
        # Round 2: swap to teus[1].
        {"type": "reserve_advance", "chosen": teus[1], "rationale": "Round 2 swap"},
    ])
    res = resolve_storm(
        s, attacker_side="teutonic",
        attacker_lords=teus, defender_lords=[rus],
        locale_id="pskov", walls_max=2, siege_markers=3,
        garrison={"men_at_arms": 1},
        decision_ctx=ctx,
    )
    print("\n--- Storm Reposition smoke ---")
    print(f"  rounds: {res['rounds']}, winner: {res['winner']}")
    print(f"  end attacker positions: {res['attacker_storm_positions']}")
    print(f"  decisions: {[d for d in res['decisions'] if d['type'] == 'reserve_advance']}")
    return res


def smoke_three_position_battle_with_flanking():
    """Battle with Attacker Front center+left, Defender Front center
    only -> Attacker left Flanks Defender center."""
    s = load_scenario("watland", seed=1)
    teus = [lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered"][:2]
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian")
    s.lords[rus].state = "mustered"
    s.lords[rus].location = "pskov"
    s.lords[rus].forces = {"militia": 6}
    for t in teus:
        s.lords[t].location = "pskov"
        s.lords[t].forces = {"knights": 4, "sergeants": 2}
    ctx = BattleDecisionContext(scripted=[
        # Active at center; teus[1] picks left.
        {"type": "initial_placement_attacker", "chosen": "left",
         "rationale": "test left placement"},
    ])
    res = resolve_battle(
        s, attacker_side="teutonic",
        attacker_lords=teus, defender_lords=[rus],
        active_attacker=teus[0],
        decision_ctx=ctx,
    )
    print("\n--- Three-position Battle with Flanking ---")
    print(f"  rounds: {res['rounds']}")
    print(f"  attacker positions: {res['attacker_positions']}")
    print(f"  defender positions: {res['defender_positions']}")
    # In Round 1, teus[1] at left has no Defender directly opposite (only center occupied).
    # _strike_target should route teus[1]'s Hits to the center Lord (Flanking).
    found_flank = False
    for rd in res["log"]:
        for step in rd["steps"]:
            for ps in step.get("per_striker", []):
                if ps["striker_slot"] == "left" and ps["target_slot"] == "center":
                    found_flank = True
                    break
    print(f"  Flanking hit found: {found_flank}")
    return res


def smoke_adjust_rows_no_sally_remain():
    """Adjust Rows Rule 1: kill Sally row, verify Rearguard -> Reserve."""
    s = load_scenario("watland", seed=1)
    teus = [lid for lid, l in s.lords.items() if l.side == "teutonic"][:2]
    rus_marching = next(lid for lid, l in s.lords.items() if l.side == "russian")
    rus_sallying = next(
        lid for lid, l in s.lords.items()
        if l.side == "russian" and lid != rus_marching
    )
    for t in teus:
        s.lords[t].state = "mustered"
        s.lords[t].forces = {"sergeants": 4, "knights": 4}  # tough
    s.lords[rus_marching].state = "mustered"
    s.lords[rus_marching].forces = {"knights": 2, "militia": 4}
    s.lords[rus_sallying].state = "mustered"
    # Sallying Lord with very few units -> Routed in Round 1.
    s.lords[rus_sallying].forces = {"militia": 1}
    ctx = BattleDecisionContext()
    res = resolve_battle(
        s, attacker_side="russian",
        attacker_lords=[rus_marching, rus_sallying],
        defender_lords=teus,
        active_attacker=rus_marching,
        decision_ctx=ctx,
        sallying_lords=[rus_sallying],
        siegeworks_for_sally=2,
    )
    print("\n--- Adjust Rows: Rule 1 ---")
    print(f"  rounds: {res['rounds']}, winner: {res['winner']}")
    # Look for adjust_rows entries in round 2+.
    for rd in res["log"]:
        if rd.get("adjust_rows"):
            print(f"  Round {rd['round']} adjust_rows: {rd['adjust_rows']}")
    return res


def main():
    smoke_relief_sally_full_battle()
    smoke_storm_reposition_multi_round()
    smoke_three_position_battle_with_flanking()
    smoke_adjust_rows_no_sally_remain()
    print("\n[smoke complete]")


if __name__ == "__main__":
    main()
