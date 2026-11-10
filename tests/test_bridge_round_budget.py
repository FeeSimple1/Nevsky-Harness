"""N6-01. Bridge limits the units that strike across a whole Battle Round."""

import pytest

from nevsky.actions import apply_action
from nevsky.state import GameState
from tests.test_cross_game_relief_retreat import place, position


def _bridge_battle(seed, knights, men_at_arms, *, concede_round=1, marsh=False):
    state = position(seed, box=9)
    hermann = place(state, "hermann", {"knights": knights, "men_at_arms": men_at_arms})
    hermann.location = "ostrov"
    place(state, "aleksandr", {"men_at_arms": 5})

    holds = {"bridge": "R1", "bridge_target_lord": "hermann"}
    cards = ["R1"]
    if marsh:
        holds["marsh"] = "R2"
        cards.append("R2")
    deck = state.decks.russian
    for pile in (deck.deck, deck.discard, deck.holds, deck.removed):
        pile[:] = [card for card in pile if card not in cards]
    deck.holds.extend(cards)

    apply_action(state, {"type": "cmd_march", "side": "teutonic", "args": {
        "lord_id": "hermann", "to": "pskov", "way_type": "waterway",
        "absorption_policy": ["knights"],
    }})
    state = GameState.model_validate_json(state.model_dump_json())
    result = apply_action(state, {"type": "stand_battle", "side": "russian", "args": {
        "holds": holds, "concede": "defender", "concede_round": concede_round,
    }})["battle"]
    assert {item["card"] for item in result["holds_consumed"]} == set(cards)
    return [{step["step"]: step for step in entry["steps"]}
            for entry in result["log"] if "steps" in entry]


def _raw(steps, step):
    if step not in steps:
        return 0
    return steps[step]["per_striker"][0]["raw"]


def test_routed_knights_do_not_release_spent_bridge_slots():
    first, second = _bridge_battle(1, 2, 2, concede_round=2)
    assert _raw(first, "melee_horse_attacker") == 4
    assert first["melee_foot_defender"]["distribution"][0]["routed"] == [
        {"unit": "knights", "absorbed": False}, {"unit": "knights", "absorbed": False},
    ]
    assert _raw(first, "melee_foot_attacker") == 0
    assert _raw(second, "melee_foot_attacker") == 1


@pytest.mark.parametrize(("knights", "marsh", "horse_hits", "foot_hits"), [
    (1, False, 2, 1),
    (2, True, 0, 2),
])
def test_foot_can_use_remaining_bridge_slots(knights, marsh, horse_hits, foot_hits):
    first, = _bridge_battle(4, knights, 3, marsh=marsh)
    assert _raw(first, "melee_horse_attacker") == horse_hits
    assert _raw(first, "melee_foot_attacker") == foot_hits
