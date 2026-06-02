"""T6/R6 Ambush, Round 1 targeting (rules-accuracy fix).

Per the Arts of War Reference T6/R6 Tips: when Ambush is played for
Round 1, "Lords of that side who are at left or right front would Flank
the enemy's center Lord, while any enemy Lords at left or right front
would be uninvolved (so could not absorb Hits nor Rout in Round 1)."

The harness previously DROPPED an ambushing-side Striker whose target
resolved to an uninvolved enemy left/right Lord, silently losing those
Hits. The rules say such a flank Lord instead strikes the enemy CENTER.
This test verifies the ambushing side's left/right Lords now route their
Hits onto the enemy center Lord rather than contributing nothing.
"""
from __future__ import annotations

from nevsky.battle import BattleDecisionContext, resolve_battle
from nevsky.scenarios import load_scenario


def _three_v_three():
    s = load_scenario("watland", seed=1)
    teus = [lid for lid, l in s.lords.items() if l.side == "teutonic"][:3]
    rus = [lid for lid, l in s.lords.items() if l.side == "russian"][:3]
    for lid in teus + rus:
        s.lords[lid].state = "mustered"
        s.lords[lid].location = "pskov"
        s.lords[lid].forces = {"sergeants": 2, "men_at_arms": 2}
    s.meta.box = 1
    return s, teus, rus


def test_ambush_side_flank_lords_strike_enemy_center():
    s, teus, rus = _three_v_three()
    # Russian plays R6 -> Teutonic (attacker) left/right are uninvolved;
    # Russian (defender) is the ambushing side and its left/right Lords
    # Flank the Teutonic center.
    res = resolve_battle(
        s, attacker_side="teutonic",
        attacker_lords=teus, defender_lords=rus,
        max_rounds=1, decision_ctx=BattleDecisionContext(),
        holds={"ambush": "R6"},
    )
    rd1 = res["log"][0]
    flank_strikers_seen = 0
    flank_targets = set()
    for st in rd1["steps"]:
        for entry in st.get("per_striker", []):
            if entry["striker"] in rus and entry["striker_slot"] in ("left", "right"):
                flank_strikers_seen += 1
                # The fix: a flank Lord Strikes the enemy CENTER Lord
                # (per T6/R6), rather than its Hits being dropped.
                assert entry["target_slot"] == "center", (
                    f"Russian flank Lord {entry['striker']} struck slot "
                    f"{entry.get('target_slot')}; expected enemy center"
                )
                flank_targets.add(entry["target"])
    assert flank_strikers_seen > 0, (
        "expected the ambushing side's left/right Lords to Strike "
        "(Flank the center) in Round 1 -- previously their Hits were dropped"
    )
    # All flank Lords converge on the single enemy center Lord.
    assert len(flank_targets) == 1, flank_targets
