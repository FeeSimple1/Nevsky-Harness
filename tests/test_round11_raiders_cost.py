"""Raiders uses the 4.7.2 cost at its target in the menu and dispatcher."""

import pytest

from nevsky.actions import IllegalAction, apply_action
from nevsky.llm.tools import legal_actions_for_side
from nevsky.state import GameState
from nevsky.static_data import load_lords
from tests.test_cross_game_relief_retreat import place, position


@pytest.mark.parametrize("card", ["T2", "R12", "R14"])
@pytest.mark.parametrize(("enemy_position", "budget", "cost"), [
    pytest.param("target", 2, 2, id="two-actions"),
    pytest.param("target", 1, 2, id="insufficient-actions"),
    pytest.param("besieged", 1, 1, id="besieged-neighbor"),
    pytest.param("origin", 1, 1, id="adjacent-only-to-origin"),
])
def test_raiders_ravage_cost(card, enemy_position, budget, cost):
    teutonic = card == "T2"
    if teutonic:
        active, origin, target = "hermann", "ugaunia", "izborsk"
        enemy, neighbor, origin_neighbor = "gavrilo", "pskov", "uzmen"
        besieger, horse = "andreas", "knights"
    else:
        active, origin, target = "domash", "izborsk", "ugaunia"
        enemy, neighbor, origin_neighbor = "hermann", "dorpat", "lettgallia"
        besieger, horse = "aleksandr", "light_horse"

    state = position(seed=1, box=9)
    raider = place(state, active, {horse: 1})
    raider.location = origin
    opponent = place(state, enemy, {"militia": 1})
    opponent.location = origin_neighbor if enemy_position == "origin" else neighbor
    if enemy_position == "besieged":
        opponent.in_stronghold = True
        state.locales[neighbor].siege_markers = 1
        place(state, besieger, {"knights": 1}).location = neighbor

    deck = state.decks.teutonic if teutonic else state.decks.russian
    deck.deck.remove(card)
    deck.capabilities_in_play.append(card)
    raider.this_lord_capabilities = [card]
    side = raider.side
    state.meta.active_player = side
    state.campaign_turn.active_lord = state.campaign_turn.active_card = active
    command = load_lords()[active]["ratings"]["command"]
    state.campaign_turn.actions_remaining = command
    for _ in range(command - budget):
        apply_action(state, {"type": "cmd_forage", "side": side, "args": {"lord_id": active}})

    action = {"type": "cmd_raiders_ravage", "side": side, "args": {"lord_id": active, "to": target}}
    moves = [move for move in legal_actions_for_side(state, side)
             if move["type"] == action["type"] and move["args"] == action["args"]]
    before = state.model_dump_json()
    if budget < cost:
        assert moves == []
        with pytest.raises(IllegalAction) as rejected:
            apply_action(state, action)
        assert rejected.value.code == "insufficient_actions"
        assert state.model_dump_json() == before
        return

    move, = moves
    assert ("(2 actions)" if cost == 2 else "(1 action)") in move["note"]
    restored = GameState.model_validate_json(before)
    provender = raider.assets.get("provender", 0)
    receipt = apply_action(state, move)
    assert receipt["actions_used"] == cost
    assert receipt == apply_action(restored, move)
    assert state.model_dump_json() == restored.model_dump_json()
    assert state.campaign_turn.actions_remaining == budget - cost
    assert getattr(state.locales[target], f"{side}_ravaged")
    assert raider.assets.get("provender", 0) == provender + 1
    assert raider.assets.get("loot", 0) == int(teutonic)
