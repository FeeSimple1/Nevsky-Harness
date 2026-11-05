"""IF2-1: side-bound tools cannot act as another player or the system."""

from copy import deepcopy

import pytest

from nevsky.actions import IllegalAction, apply_action
from nevsky.llm.tools import apply_action_for_side
from nevsky.scenarios import load_scenario


@pytest.mark.parametrize("caller", ["teutonic", "russian"])
@pytest.mark.parametrize("declared", ["opponent", "system", None])
def test_mismatched_side_rejects_before_setup_deck_rng_or_history_changes(caller, declared):
    state = load_scenario("pleskau", seed=1)
    opponent = "russian" if caller == "teutonic" else "teutonic"
    # An unguarded opponent action would be legal on the opponent's turn.
    state.meta.active_player = opponent
    action = {
        "type": "aow_draw",
        "side": opponent if declared == "opponent" else declared,
        "args": {},
    }
    original = deepcopy(action)
    saved = state.model_dump_json()
    deck = getattr(state.decks, opponent)
    with pytest.raises(IllegalAction) as error:
        apply_action_for_side(state, caller, action)
    assert error.value.code == "wrong_actor"
    assert state.model_dump_json() == saved
    assert getattr(state.decks, opponent) is deck and action == original


@pytest.mark.parametrize("caller", ["system", "invalid", None])
def test_invalid_caller_cannot_select_a_valid_player(caller):
    state = load_scenario("pleskau", seed=1)
    saved = state.model_dump_json()
    with pytest.raises(IllegalAction) as error:
        apply_action_for_side(state, caller, {"type": "aow_draw", "side": "teutonic"})
    assert error.value.code == "wrong_actor"
    assert state.model_dump_json() == saved


@pytest.mark.parametrize("caller", ["teutonic", "russian"])
@pytest.mark.parametrize("explicit", [False, True])
def test_owner_draw_matches_direct_engine_and_does_not_modify_input(caller, explicit):
    state = load_scenario("pleskau", seed=1)
    state.meta.active_player = caller
    control = state.model_copy(deep=True)
    action = {"type": "aow_draw", "args": {}}
    if explicit:
        action["side"] = caller
    original = deepcopy(action)
    result = apply_action_for_side(state, caller, action)
    assert result == apply_action(control, {**action, "side": caller})
    assert state.model_dump_json() == control.model_dump_json()
    assert result["drawn"] and action == original


@pytest.mark.parametrize("action", [None, [], "aow_draw"])
def test_malformed_action_is_rejected_without_mutation(action):
    state = load_scenario("pleskau", seed=1)
    saved = state.model_dump_json()
    with pytest.raises(IllegalAction) as error:
        apply_action_for_side(state, "teutonic", action)
    assert error.value.code == "bad_envelope"
    assert state.model_dump_json() == saved
