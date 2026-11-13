"""4.3.4: finish the pending March before starting another Command."""

import pytest

from nevsky.actions import IllegalAction
from nevsky.llm.session import LLMSession
from nevsky.llm.tools import apply_action_for_side, legal_actions_for_side
from nevsky.state import GameState
from tests.test_round12_lieutenant_movement import act, plan, plan_position


def _hermann_card():
    state = plan_position()
    state.lords["hermann"].location = "dubrovno"
    plan(state)
    return state


@pytest.mark.parametrize("adapter", ["player", "session"])
def test_saved_approach_blocks_commands_then_accepts_stand(adapter):
    state = _hermann_card()
    act(state, "cmd_march", "teutonic", to="pskov", way_type="trackway")
    before = state.model_dump_json()
    state = GameState.model_validate_json(before)
    assert state.meta.active_player == "russian"
    assert state.campaign_turn.actions_remaining == 2
    assert not legal_actions_for_side(state, "teutonic")
    session = LLMSession(state, "teutonic", "pleskau")
    assert session.whose_turn() == "human"

    for move in [
        {"type": "cmd_forage"},
        {"type": "cmd_march", "args": {"to": "dubrovno", "way_type": "trackway"}},
        {"type": "cmd_pass"},
        {"type": "end_card"},
        {"type": "command_reveal"},
    ]:
        with pytest.raises(IllegalAction) as exc:
            if adapter == "session":
                session.apply(move)
            else:
                apply_action_for_side(state, "teutonic", move)
        assert exc.value.code == "approach_pending"
        assert state.model_dump_json() == before
        assert session.history == []

    result = session.apply({"type": "stand_battle", "args": {"concede": "defender"}}, who="human")
    assert result["winner"] == "teutonic"
    assert state.combat_pending is None
    assert state.lords["hermann"].location == "pskov"
    assert state.lords["gavrilo"].location == "izborsk"
    act(state, "fpd_resolve", "teutonic", decline_pay=True)
    assert not state.lords["hermann"].assets.get("provender")


def test_forage_before_approach_remains_a_command():
    state = _hermann_card()
    assert act(state, "cmd_forage", "teutonic")["new_count"] == 2
    result = act(state, "cmd_march", "teutonic", to="pskov", way_type="trackway")
    assert result["approach"] and result["cost"] == 2
    assert state.campaign_turn.actions_remaining == 0
    assert not state.campaign_turn.in_feed_pay_disband


@pytest.mark.parametrize("block", [False, True])
def test_saved_ambush_does_not_let_attacker_withdraw_defender(block, tmp_path):
    state = plan_position()
    state.lords["hermann"].location = "odenpah"
    state.lords["gavrilo"].location = "dorpat"
    state.locales["dorpat"].siege_markers = 1
    state.decks.teutonic.deck.remove("T6")
    state.decks.teutonic.holds.append("T6")
    plan(state)
    act(state, "cmd_march", "teutonic", to="dorpat", way_type="trackway")
    avoid = act(state, "avoid_battle", "russian", to="gdov", way_type="waterway")
    assert avoid["ambush_interrupt"]

    path = tmp_path / "ambush.json"
    LLMSession(state, "teutonic", "pleskau").save(path)
    session = LLMSession.load(path)
    state = session.state
    saved = state.model_dump_json()
    assert {move["type"] for move in session.legal_actions()} == {
        "play_ambush_block", "decline_ambush_block",
    }
    with pytest.raises(IllegalAction, match="wrong_actor"):
        apply_action_for_side(state, "teutonic", {"type": "withdraw"})
    assert state.model_dump_json() == saved
    with pytest.raises(IllegalAction, match="wrong_actor"):
        session.apply({"type": "withdraw"})
    assert state.model_dump_json() == saved
    assert not session.history

    if block:
        assert session.apply({"type": "play_ambush_block"})["ambush_blocked"]
        assert "T6" in state.decks.teutonic.discard
        assert state.combat_pending.pending_response_by == "russian"
        assert state.lords["gavrilo"].location == "dorpat"
        with pytest.raises(IllegalAction, match="not_friendly"):
            session.apply({"type": "withdraw"}, who="human")
    else:
        session.apply({"type": "decline_ambush_block"})
        assert "T6" in state.decks.teutonic.holds
        assert state.combat_pending is None
        assert state.lords["gavrilo"].location == "gdov"
        assert state.locales["dorpat"].siege_markers == 0
