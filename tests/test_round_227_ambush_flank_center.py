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

from nevsky.actions import apply_action
from nevsky.battle import BattleDecisionContext, resolve_battle
from nevsky.scenarios import load_scenario
from nevsky.state import GameState
from tests.test_cross_game_relief_retreat import place, position, stand
from tests.test_round7_combat_limits import _place_with_vassals


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


def _march_into_ambush(seed, *, spillover):
    state = position(seed=seed, box=9)
    andreas = _place_with_vassals(state, "andreas", "andreas_teutonic_vassals")
    andreas.location = "ostrov"
    andreas.forces = {"men_at_arms": 3} if spillover else {"knights": 1}
    place(state, "hermann", {"militia": 1} if spillover else {"men_at_arms": 1}).location = "ostrov"
    gavrilo = place(state, "gavrilo", {"militia": 1 if spillover else 2})
    place(state, "aleksandr", {"knights": 1})
    if spillover:
        state.decks.teutonic.deck.remove("T4")
        andreas.this_lord_capabilities = ["T4"]
        state.decks.teutonic.capabilities_in_play.append("T4")
    else:
        state.decks.russian.deck.remove("R1")
        gavrilo.this_lord_capabilities = ["R1"]
        state.decks.russian.capabilities_in_play.append("R1")
    state.decks.teutonic.deck.remove("T6")
    state.decks.teutonic.holds.append("T6")
    state.campaign_turn.active_card = state.campaign_turn.active_lord = "andreas"
    apply_action(state, {"type": "cmd_march", "side": "teutonic", "args": {
        "lord_id": "andreas", "to": "pskov", "way_type": "waterway", "group": ["hermann"],
    }})
    return state.model_dump_json()


def _stand_in_ambush(checkpoint, *, ambush, extra_decisions=()):
    return stand(
        GameState.model_validate_json(checkpoint),
        holds={"ambush": "T6"} if ambush else {},
        scripted_decisions=[
            {"type": "initial_placement_attacker", "chosen": "left"},
            {"type": "initial_placement_defender", "chosen": "gavrilo"},
            *extra_decisions,
        ],
    )["battle"]


def test_ambush_protects_uninvolved_lord_from_spillover():
    checkpoint = _march_into_ambush(seed=5, spillover=True)
    ordinary = _stand_in_ambush(checkpoint, ambush=False)
    ambush = _stand_in_ambush(checkpoint, ambush=True)
    ordinary_hits = ordinary["log"][0]["steps"][0]["distribution"]
    ambush_hits = ambush["log"][0]["steps"][0]["distribution"]
    assert ordinary_hits[1]["lord"] == "aleksandr" and ordinary_hits[1]["spillover"]
    assert ambush_hits == ordinary_hits[:1]
    assert ambush_hits[0]["lord"] == "gavrilo" and ambush_hits[0]["applied"] == 1


def test_ambush_allows_legal_flanking_absorption():
    checkpoint = _march_into_ambush(seed=1, spillover=False)
    ordinary = _stand_in_ambush(checkpoint, ambush=False)
    ambush = _stand_in_ambush(checkpoint, ambush=True, extra_decisions=[
        {"type": "flank_absorb", "chosen": "hermann"},
    ])
    assert not any(decision["type"] == "flank_absorb" for decision in ordinary["decisions"])
    choice = next(decision for decision in ambush["decisions"] if decision["type"] == "flank_absorb")
    assert choice["options"] == ["andreas", "hermann"] and choice["chosen"] == "hermann"
    assert ambush["log"][0]["steps"][0]["distribution"][0]["lord"] == "hermann"
