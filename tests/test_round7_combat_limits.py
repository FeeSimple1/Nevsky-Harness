"""N7-01/02 regression cases through the public combat actions."""

import pytest

from nevsky.actions import apply_action
from nevsky.state import GameState
from nevsky.static_data import load_lords
from tests.test_cross_game_relief_retreat import place, position


def _place_with_vassals(state, lord_id, *vassal_ids):
    printed = load_lords()[lord_id]
    lord = place(state, lord_id, dict(printed["starting_forces"]))
    for vassal in printed["vassals"]:
        if vassal["vassal_id"] in vassal_ids:
            lord.vassals[vassal["vassal_id"]].mustered = True
            for unit, count in vassal["forces"].items():
                lord.forces[unit] = lord.forces.get(unit, 0) + count
    return lord


def _monks_battle(state, *co_marchers):
    andreas = _place_with_vassals(state, "andreas", "andreas_teutonic_vassals")
    andreas.location = "ostrov"
    andreas.this_lord_capabilities = ["T7"]
    state.decks.teutonic.deck.remove("T7")
    state.campaign_turn.active_card = state.campaign_turn.active_lord = "andreas"
    apply_action(state, {"type": "cmd_march", "side": "teutonic", "args": {
        "lord_id": "andreas", "to": "pskov", "way_type": "waterway",
        "group": list(co_marchers), "absorption_policy": ["knights", "sergeants", "men_at_arms"],
    }})
    state = GameState.model_validate_json(state.model_dump_json())
    result = apply_action(state, {"type": "stand_battle", "side": "russian", "args": {
        "concede": "attacker",
    }})["battle"]
    assert result["rounds"] == 1
    return {step["step"]: step["distribution"] for step in result["log"][0]["steps"]}


def test_warrior_monks_shares_the_melee_reroll_between_horse_and_foot():
    state = position(seed=6, box=9)
    _place_with_vassals(state, "gavrilo", "gavrilo_pskov_1", "gavrilo_pskov_2",
                        "gavrilo_borderland_russians")
    steps = _monks_battle(state)

    # The Horse Melee reroll fails. The next failed Knight roll in Foot
    # Melee still uses the same Round's allowance and must Rout the Knight.
    assert steps["melee_horse_defender"][0]["routed"][0] == {"unit": "knights", "absorbed": False}
    assert steps["melee_foot_defender"][0]["routed"][0] == {"unit": "knights", "absorbed": False}


def test_warrior_monks_shares_the_melee_reroll_with_flanking_spillover():
    state = position(seed=9, box=9)
    place(state, "hermann", {"militia": 1}).location = "ostrov"
    place(state, "aleksandr", {"knights": 1})
    place(state, "gavrilo", {"knights": 1})
    steps = _monks_battle(state, "hermann")

    direct, _, spillover = steps["melee_horse_defender"]
    # The first failed roll is saved by Warrior Monks. After Hermann Routs,
    # the remaining Hit on Andreas cannot give his Knights another reroll.
    assert direct["lord"] == "andreas"
    assert direct["routed"][0] == {"unit": "knights", "absorbed": True}
    assert spillover["lord"] == "andreas" and spillover["spillover"]
    assert spillover["routed"] == [{"unit": "knights", "absorbed": False}]


@pytest.mark.parametrize("besieged_lord, expected_hits", [(True, 8), (False, 3)])
def test_storm_garrison_adds_melee_hits_after_the_lords_cap(besieged_lord, expected_hits):
    state = position(seed=1, box=9)
    _place_with_vassals(state, "hermann", "hermann_helmold_von_luneburg",
                        "hermann_johannes_von_dolen")
    if besieged_lord:
        aleksandr = _place_with_vassals(state, "aleksandr", "aleksandr_pereyaslavl",
                                       "aleksandr_rostov", "aleksandr_yaroslavl")
        aleksandr.in_stronghold = True
    state.locales["pskov"].siege_markers = 1
    result = apply_action(state, {"type": "cmd_storm", "side": "teutonic", "args": {
        "lord_id": "hermann",
    }})["battle"]

    # Aleksandr contributes 6 of his 8 raw Hits and Pskov's Garrison
    # contributes 3. With seed 1, Siegeworks cancel the eighth Hit only.
    melee = next(step for step in result["log"][0]["steps"] if step["step"] == "melee_defender")
    assert melee["hits_after_walls"] == expected_hits
