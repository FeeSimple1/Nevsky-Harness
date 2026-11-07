"""Fourth cross-game audit regressions through public actions and player tools."""

import pytest

from nevsky.actions import IllegalAction, apply_action
from nevsky.legal_moves import legal_moves
from nevsky.llm.session import LLMSession
from nevsky.llm.tools import apply_action_for_side, legal_actions_for_side
from nevsky.rewards import REWARD_ACTION
from nevsky.state import GameState
from tests.test_cross_game_combat_spoils import place, position
from tests.test_cross_game_concede_ownership import march
from tests.test_cross_game_concede_ownership import position as approach_position


def capability(state, card):
    deck = state.decks.russian if card.startswith("R") else state.decks.teutonic
    deck.deck.remove(card)
    deck.capabilities_in_play.append(card)


def sally(state, **args):
    return apply_action_for_side(
        state, "russian", {"type": "cmd_sally", "args": {"lord_id": "gavrilo", **args}},
    )


def test_winning_battle_lord_lost_in_losses_pays_ransom_to_withdrawer():
    state = position(1)
    place(state, "hermann", {"militia": 1}, "izborsk")
    place(state, "yaroslav", {"knights": 2, "men_at_arms": 3}, "izborsk")
    place(state, "gavrilo", {"knights": 2, "men_at_arms": 2})
    place(state, "aleksandr", {"knights": 1}, "novgorod")
    capability(state, "R7")
    apply_action_for_side(state, "teutonic", march(
        group=["hermann", "yaroslav"], way_type="trackway",
    ))
    result = apply_action_for_side(state, "russian", {
        "type": "stand_battle", "args": {
            "concede": "defender", "concede_round": 2, "withdraw_losers": ["gavrilo"],
        },
    })
    assert result["winner_removed_by_losses"] == ["hermann"]
    assert state.lords["gavrilo"].in_stronghold
    assert state.lords["gavrilo"].assets["coin"] == 4
    assert result["ransom"] == [{
        "ransom": True, "removed": "hermann", "recipient": "gavrilo", "coin": 4,
    }]


@pytest.mark.parametrize("besieged,service_box", [(True, 3), (True, 2), (False, 3)])
def test_levy_disband_ransom_requires_siege(besieged, service_box):
    state = position(1, "gavrilo", "russian")
    state.meta.phase, state.meta.levy_step, state.meta.box = "levy", "disband", 3
    state.meta.disband_resolved_t = state.meta.disband_resolved_r = False
    place(state, "gavrilo", {"knights": 1}, "pskov" if besieged else "ostrov", inside=besieged)
    place(state, "hermann", {"knights": 1})
    place(state, "aleksandr", {"knights": 1}, "novgorod")
    state.locales["pskov"].siege_markers = int(besieged)
    for box in state.calendar.boxes:
        box.has_levy_campaign_marker = box.box == 3
        box.levy_campaign_face = "levy" if box.box == 3 else None
        if "gavrilo" in box.service_markers:
            box.service_markers.remove("gavrilo")
    state.calendar.boxes[service_box - 1].service_markers.append("gavrilo")
    capability(state, "T16")
    result = apply_action_for_side(state, "russian", {"type": "disband_resolve"})
    assert state.lords["gavrilo"].state == ("disbanded" if service_box == 3 else "removed")
    assert state.lords["hermann"].assets.get("coin", 0) == (4 if besieged else 0)
    assert ("ransom" in result) == besieged


def failed_sally_position():
    state = position(1, "gavrilo", "russian")
    state.locales["pskov"].siege_markers = 2
    place(state, "gavrilo", {"militia": 1}, inside=True, loot=2)
    place(state, "hermann", {"knights": 2, "men_at_arms": 3}, coin=8)
    place(state, "yaroslav", {"knights": 2, "men_at_arms": 3})
    place(state, "aleksandr", {"knights": 1}, "novgorod")
    return state


def test_ransom_choice_then_failed_sally_spoils_survive_save_and_reload():
    state = failed_sally_position()
    capability(state, "T16")
    result = sally(state)
    assert result["removed_after_sally"] == ["gavrilo"]
    assert result["awaiting_aftermath_reward"] == {"reward": "ransom", "owed_by": "teutonic"}
    assert not legal_actions_for_side(state, "russian")
    assert state.lords["yaroslav"].assets == {}
    state = GameState.model_validate_json(state.model_dump_json())
    moves = legal_moves(state, with_previews=False)
    assert {m["args"]["recipient"] for m in moves} == {"hermann", "yaroslav"}
    saved = state.model_dump_json()
    for side, action in (
        ("russian", {"type": REWARD_ACTION, "args": {"recipient": "yaroslav"}}),
        ("teutonic", {"type": REWARD_ACTION, "args": {"recipient": "aleksandr"}}),
        ("teutonic", {"type": "fpd_resolve"}),
    ):
        with pytest.raises(IllegalAction):
            apply_action_for_side(state, side, action)
        assert state.model_dump_json() == saved
    result = apply_action_for_side(state, "teutonic", next(
        m for m in moves if m["args"]["recipient"] == "yaroslav"))
    assert result["ransom"][0]["coin"] == 4
    assert result["awaiting_aftermath_reward"] == {
        "reward": "sally_spoils", "owed_by": "teutonic",
    }
    saved = state.model_dump_json()
    with pytest.raises(IllegalAction, match="allocation exceeds"):
        apply_action_for_side(state, "teutonic", {
            "type": REWARD_ACTION, "args": {"allocation": {"yaroslav": {"loot": 3}}},
        })
    assert state.model_dump_json() == saved
    result = apply_action_for_side(state, "teutonic", {
        "type": REWARD_ACTION, "args": {"allocation": {"yaroslav": {"loot": 2}}},
    })
    assert result["spoils"][0]["distributed"] == {"yaroslav": {"loot": 2}}
    assert state.lords["hermann"].assets == {"coin": 8}
    assert state.lords["yaroslav"].assets == {"coin": 4, "loot": 2}
    assert [m["type"] for m in legal_moves(state, with_previews=False)] == ["fpd_resolve"]


def test_ransom_cap_receipt_records_actual_payment():
    state = failed_sally_position()
    capability(state, "T16")
    sally(state)
    result = apply_action_for_side(state, "teutonic", {
        "type": REWARD_ACTION, "args": {"recipient": "hermann"},
    })
    assert result["ransom"][0]["coin"] == 0
    assert result["ransom"][0]["coin_lost_to_cap"] == 4
    assert state.lords["hermann"].assets["coin"] == 8


@pytest.mark.parametrize("preselect", [False, True])
def test_successful_sally_winner_allocates_spoils(preselect):
    state = position(4, "gavrilo", "russian")
    state.locales["pskov"].siege_markers = 1
    place(state, "gavrilo", {"knights": 2, "men_at_arms": 3}, inside=True)
    place(state, "domash", {"knights": 2, "men_at_arms": 3}, inside=True)
    place(state, "hermann", {"knights": 1}, loot=2)
    place(state, "yaroslav", {"knights": 1}, "izborsk")
    plan = {"gavrilo": {"loot": 2}}
    result = sally(state, **({"spoils_allocation": plan} if preselect else {}))
    assert result["battle"]["winner"] == "russian"
    assert result["awaiting_sally_loser_fate"] == {"owed_by": "teutonic"}
    result = apply_action_for_side(state, "teutonic", {
        "type": "resolve_sally_loser_fate", "args": {},
    })
    if not preselect:
        assert state.meta.active_player == "russian"
        assert legal_actions_for_side(state, "russian")[0]["reward"]["pool"] == {"loot": 2}
        result = apply_action_for_side(state, "russian", {
            "type": REWARD_ACTION, "args": {"allocation": plan},
        })
    assert result["spoils"][0]["distributed"] == plan
    assert state.lords["gavrilo"].assets["loot"] == 2
    assert state.meta.active_player == "teutonic"


@pytest.mark.parametrize("adapter", ["tool", "llm", "human"])
@pytest.mark.parametrize("args", [
    {"remove_losers": ["hermann"]},
    {"holds": {"field_organ": "T10", "field_organ_lord": "hermann"}},
    {"retreat_to": {"hermann": "ostrov"}},
    {"spoils_allocation": {"hermann": {"loot": 1}}},
    {"scripted_decisions": [{"type": "initial_placement_attacker", "chosen": "hermann"}]},
])
def test_stand_rejects_opponent_elections_before_combat(adapter, args):
    state = approach_position()
    state.decks.teutonic.holds.append("T10")
    apply_action_for_side(state, "teutonic", march(concede=1))
    action = {"type": "stand_battle", "args": args}
    session = LLMSession(state, "teutonic" if adapter == "human" else "russian",
                         "crusade_on_novgorod")
    saved = state.model_dump_json()
    with pytest.raises(IllegalAction, match="wrong_actor"):
        if adapter == "tool":
            apply_action_for_side(state, "russian", action)
        else:
            session.apply(action, who=adapter)
    assert state.model_dump_json() == saved
    assert not session.history


def test_hold_menu_and_stand_allow_own_held_event():
    state = approach_position()
    state.decks.teutonic.holds.append("T10")
    state.decks.russian.holds.append("R5")
    apply_action_for_side(state, "teutonic", march())
    stand = next(m for m in legal_actions_for_side(state, "russian")
                 if m["type"] == "stand_battle")
    assert [h["card"] for h in stand["holds_available"]] == ["R5"]
    result = apply_action_for_side(state, "russian", {
        "type": "stand_battle", "args": {"holds": {"hill": "R5"}},
    })
    assert result["battle"]["holds_consumed"] == [{"card": "R5", "key": "hill"}]
    assert "T10" in state.decks.teutonic.holds


def test_referee_can_resolve_prearranged_two_sided_combat_choices():
    state = approach_position()
    state.decks.teutonic.holds.append("T10")
    apply_action_for_side(state, "teutonic", march(concede=1))
    result = apply_action(state, {
        "type": "stand_battle", "side": "russian",
        "args": {"remove_losers": ["hermann"],
                 "holds": {"field_organ": "T10", "field_organ_lord": "hermann"}},
    })
    assert result["removed"] == ["hermann"]
    assert result["battle"]["holds_consumed"] == [{"card": "T10", "key": "field_organ"}]


def test_battle_awards_ransom_before_distributing_captured_coin():
    state = position(4)
    place(state, "hermann", {"knights": 2, "men_at_arms": 3}, "izborsk", coin=3)
    place(state, "yaroslav", {"knights": 2, "men_at_arms": 3}, "izborsk", coin=7)
    place(state, "gavrilo", {"militia": 1}, coin=2)
    place(state, "aleksandr", {"knights": 1}, "novgorod")
    capability(state, "T16")
    apply_action_for_side(state, "teutonic", march(
        group=["hermann", "yaroslav"], way_type="trackway",
    ))
    result = apply_action_for_side(state, "russian", {
        "type": "stand_battle", "args": {"remove_losers": ["gavrilo"]},
    })
    assert result["winner"] == "teutonic"
    assert result["awaiting_aftermath_reward"]["reward"] == "ransom"
    assert "spoils" not in result
    assert state.lords["hermann"].assets["coin"] == 3
    result = apply_action_for_side(state, "teutonic", {
        "type": REWARD_ACTION, "args": {"recipient": "hermann"},
    })
    assert result["ransom"][0]["coin"] == 4
    assert result["spoils"][0]["distributed"] == {
        "hermann": {"coin": 1}, "yaroslav": {"coin": 1},
    }
