"""October review regressions: 4.4.2, 4.5.2, T4-6 and seeded replay."""
from __future__ import annotations

import itertools
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from nevsky import battle
from nevsky.actions import IllegalAction, apply_action
from nevsky.scenarios import load_scenario
from nevsky.static_data import load_lords


def _state(seed=1):
    state = load_scenario("watland", seed=seed)
    for lid in ("andreas", "hermann", "aleksandr", "domash"):
        lord = state.lords[lid]
        lord.state = "mustered"
        lord.location = "pskov"
        lord.forces = {}
        lord.routed_units = {}
        lord.this_lord_capabilities = []
    return state


def _storm(state, **kwargs):
    return battle.resolve_storm(
        state, "teutonic", ["andreas"], ["aleksandr"], "pskov",
        walls_max=kwargs.pop("walls_max", 0), siege_markers=1,
        garrison=kwargs.pop("garrison", {"men_at_arms": 1}), **kwargs,
    )


def _step(result, label):
    return next(step for step in result["log"][0]["steps"] if step["step"] == label)


def test_battle_continues_after_three_rounds_of_successful_armor():
    """4.4.2 / D-Q011: three casualty-free Rounds are not a defeat."""
    state = _state(seed=73)
    for lid in ("andreas", "aleksandr"):
        state.lords[lid].forces = {"men_at_arms": 1}
    result = battle.resolve_battle(state, "teutonic", ["andreas"], ["aleksandr"])
    assert result["rounds"] > 3
    for record in result["log"][:3]:
        assert all(hit["absorbed"] for step in record["steps"]
                   for distribution in step["distribution"] for hit in distribution["routed"])
    assert not result.get("stalemate")
    assert not state.lords["andreas"].forces or not state.lords["aleksandr"].forces


def test_unresolved_safety_limit_raises_without_assigning_victory(monkeypatch):
    """4.4.2: an emergency computation bound cannot decide the winner."""
    state = _state()
    for lid in ("andreas", "aleksandr"):
        state.lords[lid].forces = {"men_at_arms": 1}
    monkeypatch.setattr(battle, "_BATTLE_ROUND_SAFETY_CAP", 3)
    monkeypatch.setattr(battle, "roll_d6", lambda state: 1)
    with pytest.raises(IllegalAction, match="battle_resolution_limit"):
        battle.resolve_battle(state, "teutonic", ["andreas"], ["aleksandr"])
    assert state.lords["andreas"].forces == state.lords["aleksandr"].forces == {"men_at_arms": 1}


def test_explicit_partial_simulation_has_no_winner(monkeypatch):
    """4.4.2: an explicit preview bound returns an unfinished Battle."""
    state = _state()
    for lid in ("andreas", "aleksandr"):
        state.lords[lid].forces = {"men_at_arms": 1}
    monkeypatch.setattr(battle, "roll_d6", lambda state: 1)
    result = battle.resolve_battle(state, "teutonic", ["andreas"], ["aleksandr"], max_rounds=1)
    assert result["winner"] is result["loser"] is None
    assert result["incomplete"] and result["round_limit_hit"]


def test_battle_replay_is_independent_of_python_hash_seed():
    """BRIEF Determinism: target iteration cannot reassign seeded dice."""
    script = '''
import json
from nevsky.scenarios import load_scenario
from nevsky.battle import resolve_battle
s = load_scenario("watland", seed=1)
a = ["andreas", "hermann"]
d = ["aleksandr", "domash"]
for lid in a + d:
    l = s.lords[lid]
    l.state = "mustered"
    l.location = "pskov"
    l.forces = {"men_at_arms": 3}
    l.routed_units = {}
    l.this_lord_capabilities = []
r = resolve_battle(s, "teutonic", a, d, max_rounds=1,
    attacker_positions={a[0]: "center", a[1]: "left"},
    defender_positions={d[0]: "center", d[1]: "left"})
print(json.dumps({"result": r, "state": s.model_dump(mode="json")}, sort_keys=True))
'''
    env = dict(os.environ, PYTHONPATH=str(Path(battle.__file__).resolve().parents[1]))
    results = [
        json.loads(subprocess.check_output(
            [sys.executable, "-c", script],
            env=dict(env, PYTHONHASHSEED=str(seed)), text=True,
        )) for seed in (1, 3)
    ]
    assert results[0] == results[1]


def test_storm_melee_counts_only_units_surviving_earlier_strikes(monkeypatch):
    """4.5.2 / 4.4.2: Routed units cannot Strike later in the Round."""
    state = _state()
    state.lords["andreas"].forces = {"men_at_arms": 4}
    state.lords["aleksandr"].forces = {"militia": 2}
    monkeypatch.setattr(battle, "roll_d6", lambda state: 6)
    result = _storm(state)
    assert state.lords["andreas"].forces == {"men_at_arms": 1}
    assert _step(result, "melee_attacker")["hits_after_walls"] == 1
    assert state.lords["aleksandr"].forces == {"militia": 2}
    assert result["winner"] == "defender"


def test_storm_attacking_archery_uses_survivors_of_defending_archery(monkeypatch):
    """4.5.2 initiative: defender Archery casualties reduce attacker Archery."""
    state = _state()
    state.lords["andreas"].forces = {"men_at_arms": 3}
    state.lords["andreas"].this_lord_capabilities = ["T4"]
    state.lords["aleksandr"].forces = {"militia": 2}
    monkeypatch.setattr(battle, "roll_d6", lambda state: 6)
    result = _storm(state, garrison={"men_at_arms": 3})
    assert _step(result, "archery_defender")["hits_after_walls"] == 2
    assert _step(result, "archery_attacker")["hits_after_walls"] == 1


def test_crossbows_reduce_garrison_armor_and_routed_garrison_stops_striking(monkeypatch):
    """T4-6 / 4.5.2: Garrison MaA Armor 1-3 becomes 1 against Crossbows."""
    state = _state()
    state.lords["andreas"].forces = {"men_at_arms": 2}
    state.lords["andreas"].this_lord_capabilities = ["T4"]
    state.lords["aleksandr"].forces = {"militia": 2}
    monkeypatch.setattr(battle, "roll_d6", lambda state: 2)
    result = _storm(state)
    archery = _step(result, "archery_attacker")
    assert archery["distribution"] == [
        {"target": "garrison", "unit": "men_at_arms", "absorbed": False}
    ]
    assert _step(result, "melee_defender")["hits_after_walls"] == 1


def test_garrison_does_not_pass_consumed_crossbow_penalty_to_lord(monkeypatch):
    """Q-007: one Crossbow Hit consumed by Garrison leaves ordinary Archery."""
    state = _state()
    state.lords["andreas"].forces = {"men_at_arms": 1, "asiatic_horse": 3}
    state.lords["andreas"].this_lord_capabilities = ["T4"]
    state.lords["aleksandr"].forces = {"knights": 1}
    rolls = itertools.chain([1, 6, 3], itertools.repeat(1))
    monkeypatch.setattr(battle, "roll_d6", lambda state: next(rolls))
    result = _storm(state)
    distribution = _step(result, "archery_attacker")["distribution"]
    assert distribution[0] == {"target": "garrison", "unit": "men_at_arms", "absorbed": False}
    assert distribution[1]["routed"] == [{"unit": "knights", "absorbed": True}]


def test_storm_front_is_active_lord_even_when_other_besieger_is_listed_first():
    """4.5.2: the Commanding Lord occupies Storm Front, others Reserve."""
    state = _state()
    for lid in ("andreas", "hermann"):
        state.lords[lid].forces = {"men_at_arms": 3}
    state.lords["aleksandr"].forces = {"militia": 2}
    state.lords["aleksandr"].in_stronghold = True
    state.lords["domash"].location = "novgorod"
    state.locales["pskov"].siege_markers = 1
    state.locales["pskov"].teutonic_conquered = 0
    state.meta.phase = "campaign"
    state.meta.campaign_step = "command"
    state.meta.active_player = "teutonic"
    state.campaign_turn.next_to_reveal = "teutonic"
    state.campaign_turn.active_card = "hermann"
    state.campaign_turn.active_lord = "hermann"
    state.campaign_turn.actions_remaining = load_lords()["hermann"]["ratings"]["command"]
    state.campaign_turn.in_feed_pay_disband = False
    result = apply_action(state, {
        "type": "cmd_storm", "side": "teutonic",
        "args": {"lord_id": "hermann", "concede": True},
    })
    assert result["battle"]["attacker_storm_positions"]["hermann"] == "storm_front"
    assert result["battle"]["attacker_storm_positions"]["andreas"] == "storm_reserve"


@pytest.mark.parametrize("explicit_array", [False, True])
def test_relief_sally_front_rout_refaces_rows_without_losing_siegeworks(
    monkeypatch, explicit_array,
):
    """4.4.2: refacing permits Strikes and retains the original Sally's Walls."""
    state = _state()
    state.lords["aleksandr"].forces = {"serfs": 1}  # relief Front Routs immediately
    state.lords["domash"].forces = {"men_at_arms": 2}  # Sally remains
    state.lords["andreas"].forces = {"men_at_arms": 2}
    monkeypatch.setattr(battle, "roll_d6", lambda state: 1)
    array = ({"attacker_positions": {"aleksandr": "center", "domash": "sally_center"},
              "defender_positions": {"andreas": "center"}}
             if explicit_array else {"sallying_lords": ["domash"]})
    result = battle.resolve_battle(
        state, "russian", ["aleksandr", "domash"], ["andreas"],
        active_attacker="aleksandr", siegeworks_for_sally=1,
        concede_decisions={3: "attacker"}, **array,
    )
    second_round = result["log"][1]
    assert second_round["attacker_positions"]["domash"] == "center"
    assert second_round["defender_positions"]["andreas"] == "center"
    assert second_round["steps"][0]["step"] == "melee_foot_defender"
    assert second_round["steps"][0]["per_striker"][0]["target"] == "domash"
    assert any(d.get("target") == "siegeworks_vs_sally"
               for step in second_round["steps"] for d in step["distribution"])
    assert result["rounds"] == 3 and result["conceded"] == "attacker"
