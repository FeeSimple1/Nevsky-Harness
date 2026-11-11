"""N12-02. Resolving a split Approach response still requires Encamp."""

import pytest

from nevsky.actions import apply_action
from nevsky.legal_moves import legal_moves
from nevsky.state import GameState
from tests.test_cross_game_avoid_choices import approach as spoil_approach
from tests.test_round12_lieutenant_movement import act, approach, reject


@pytest.mark.parametrize(("withdraw_first", "save"), [
    (True, None), (True, "current"), (True, "legacy"), (False, None),
])
def test_split_approach_encamps_in_either_response_order(withdraw_first, save):
    state = approach(paired=False)
    withdraw = {"type": "withdraw", "side": "russian", "args": {"lords": ["gavrilo"]}}
    avoid = {"type": "avoid_battle", "side": "russian", "args": {
        "lords": ["vladislav"], "to": "pskov", "way_type": "trackway"}}
    first, last = (withdraw, avoid) if withdraw_first else (avoid, withdraw)
    apply_action(state, first)
    assert state.combat_pending is not None
    assert state.meta.active_player == "russian"
    assert state.campaign_turn.actions_remaining == 2
    assert not state.campaign_turn.in_feed_pay_disband
    if save is not None:
        saved = state.model_dump(mode="json")
        if save == "legacy":
            del saved["combat_pending"]["approach_started_siege"]
        state = GameState.model_validate(saved)

    apply_action(state, last)
    assert state.combat_pending is None
    assert state.locales["izborsk"].siege_markers == 1
    assert state.lords["gavrilo"].in_stronghold and state.lords["gavrilo"].location == "izborsk"
    assert state.lords["vladislav"].location == "pskov"
    assert state.campaign_turn.actions_remaining == 0
    assert state.campaign_turn.in_feed_pay_disband
    assert not any(move["type"] == "cmd_ravage" for move in legal_moves(state, with_previews=False))
    reject(state, "in_feed_pay_disband", "cmd_ravage", "teutonic")


def test_encamp_waits_for_avoid_spoils_then_ends_the_card_after_reload():
    state = spoil_approach()
    act(state, "withdraw", lords=["gavrilo"])
    state.lords["domash"].assets = {"loot": 1}
    avoided = act(state, "avoid_battle", to="dubrovno", lords=["domash"])
    assert avoided["awaiting_avoid_spoils"]
    assert not state.campaign_turn.in_feed_pay_disband
    state = GameState.model_validate_json(state.model_dump_json())

    act(state, "allocate_avoid_spoils", "teutonic", allocation={"yaroslav": {"loot": 1}})
    assert state.lords["yaroslav"].assets["loot"] == 1
    assert state.locales["pskov"].siege_markers == 1
    assert state.campaign_turn.actions_remaining == 0
    assert state.campaign_turn.in_feed_pay_disband
