"""Sally Siegeworks cancel only their own Hits and preserve their types."""

import pytest

from nevsky.actions import apply_action
from nevsky.state import GameState
from nevsky.static_data import load_lords
from tests.test_cross_game_relief_retreat import place, position
from tests.test_round7_combat_limits import _place_with_vassals


def _position(seed, active):
    state = position(seed=seed, box=9)
    state.meta.active_player = state.lords[active].side
    state.campaign_turn.active_card = state.campaign_turn.active_lord = active
    state.campaign_turn.actions_remaining = load_lords()[active]["ratings"]["command"]
    state.locales["pskov"].siege_markers = 1
    return state


def _capability(state, lid, card):
    deck = state.decks.teutonic if card.startswith("T") else state.decks.russian
    for pile in (deck.deck, deck.holds, deck.discard, deck.removed):
        if card in pile:
            pile.remove(card)
    state.lords[lid].this_lord_capabilities.append(card)


def _apply(state, action_type, side, **args):
    return apply_action(state, {"type": action_type, "side": side, "args": args})


def _resolve(state, action_type, side, **args):
    restored = GameState.model_validate_json(state.model_dump_json())
    result = _apply(state, action_type, side, **args)
    assert _apply(restored, action_type, side, **args) == result
    assert restored.model_dump_json() == state.model_dump_json()
    return result["battle"]


def _archery(result):
    return next(step for step in result["log"][0]["steps"]
                if step["step"] == "archery_attacker")


def _march_relief(state, active, join):
    _apply(state, "cmd_march", state.lords[active].side, lord_id=active,
           to="pskov", way_type="waterway", sally_join=join)


def test_ordinary_sally_cancels_the_crossbow_hit_before_protection():
    state = _position(2, "gavrilo")
    gavrilo = _place_with_vassals(state, "gavrilo", "gavrilo_pskov_1", "gavrilo_pskov_2")
    gavrilo.forces = {"men_at_arms": 2, "militia": 2}
    gavrilo.in_stronghold = True
    place(state, "hermann", {"knights": 1, "men_at_arms": 1})
    _capability(state, "gavrilo", "R1")
    _capability(state, "gavrilo", "R3")
    result = _resolve(state, "cmd_sally", "russian", lord_id="gavrilo", concede="defender")
    walls, protection = _archery(result)["distribution"]
    assert walls == {"lord": "hermann", "target": "siegeworks_vs_sally", "absorbed": 1}
    # Seed 2 rolls 1 for Crossbow Walls, 4 for ordinary Walls, 3 for
    # Protection. The ordinary Hit leaves the Man-at-Arms with Armor 1–3.
    assert protection["routed"] == [{"unit": "men_at_arms", "absorbed": True}]


@pytest.mark.parametrize("crossbow_sally", [False, True])
def test_relief_sally_walls_cancel_only_the_sallying_lords_hit(crossbow_sally):
    state = _position(2, "domash")
    domash = _place_with_vassals(state, "domash", "domash_novgorod_1")
    gavrilo = _place_with_vassals(state, "gavrilo", "gavrilo_pskov_1", "gavrilo_pskov_2")
    domash.location = "ostrov"
    gavrilo.in_stronghold = True
    crossbow, bow = (gavrilo, domash) if crossbow_sally else (domash, gavrilo)
    crossbow.forces, bow.forces = {"men_at_arms": 2}, {"militia": 2}
    _capability(state, crossbow.lord_id, "R3")
    _capability(state, bow.lord_id, "R1")
    place(state, "hermann", {"knights": 1})
    _march_relief(state, "domash", ["gavrilo"])
    result = _resolve(state, "stand_battle", "teutonic", concede="defender")
    walls, protection = _archery(result)["distribution"]
    assert walls["target"] == "siegeworks_vs_sally" and walls["absorbed"] == 1
    assert protection["hits"] == 1
    # Walls roll 1 cancels the Sally Hit. A Knight's roll of 4 saves only
    # if the surviving relief Hit is an ordinary bow Hit.
    assert protection["routed"] == [{"unit": "knights", "absorbed": crossbow_sally}]


@pytest.mark.parametrize("conceder", ["attacker", "defender"])
@pytest.mark.parametrize("seed,sally,hits", [(1, True, 2), (2, True, 1), (2, False, 1)])
def test_relief_and_sally_hits_round_separately_after_pursuit(seed, sally, hits, conceder):
    state = _position(seed, "domash")
    place(state, "domash", {"militia": 1}).location = "ostrov"
    place(state, "gavrilo", {"militia": 1}).in_stronghold = True
    place(state, "hermann", {"knights": 1, "men_at_arms": 1})
    _capability(state, "domash", "R2")
    _capability(state, "gavrilo", "R1")
    _march_relief(state, "domash", ["gavrilo"] if sally else [])
    result = _resolve(state, "stand_battle", "teutonic", concede=conceder)
    distribution = _archery(result)["distribution"]
    assert distribution[-1]["hits"] == hits
    assert sum(hit.get("absorbed", 0) for hit in distribution
               if hit.get("target") == "siegeworks_vs_sally") == int(sally and seed == 2)


def test_relief_still_rounds_separately_when_trebuchets_negate_siegeworks():
    state = _position(2, "andreas")
    andreas = _place_with_vassals(state, "andreas", "andreas_lettgallian_aux")
    andreas.location, andreas.forces = "ostrov", {"militia": 1}
    place(state, "hermann", {"militia": 1}).in_stronghold = True
    place(state, "gavrilo", {"militia": 1})
    state.locales["pskov"].teutonic_conquered = 2
    _capability(state, "andreas", "T14")
    _march_relief(state, "andreas", ["hermann"])
    result = _resolve(state, "stand_battle", "russian", concede="defender")
    step = next(step for step in result["log"][0]["steps"]
                if step["step"] == "melee_foot_attacker")
    assert [strike["raw"] for strike in step["per_striker"]] == [0.5, 0.5]
    protection, = step["distribution"]
    assert protection["hits"] == 2
