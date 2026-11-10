"""N6-03. The Storm attacker chooses within the mandatory Armored tier."""

import pytest

from nevsky.actions import IllegalAction, apply_action
from nevsky.llm.tools import apply_action_for_side, legal_actions_for_side
from nevsky.state import STORM_FRONT_ACTION, GameState
from tests.test_cross_game_relief_retreat import place, position


def _storm_state(seed=2):
    state = position(seed=seed, box=9)
    place(state, "hermann", {"knights": 2, "men_at_arms": 3, "militia": 1})
    place(state, "gavrilo", {"knights": 1, "militia": 1}).in_stronghold = True
    state.locales["pskov"].siege_markers = 1
    return state


def _command(**args):
    return {"type": "cmd_storm", "side": "teutonic", "args": {"lord_id": "hermann", **args}}


def _attacker_hits(result):
    return [hit for entry in result["battle"]["log"] for step in entry["steps"]
            if step["step"].endswith("_defender")
            for target in step["distribution"] for hit in target.get("routed", [])]


def test_player_can_rank_men_at_arms_first_within_the_armored_tier():
    state = _storm_state()
    default = apply_action_for_side(state.model_copy(deep=True), "teutonic", _command())
    priority = ["militia", "men_at_arms", "knights"]
    elected = apply_action_for_side(state, "teutonic", _command(absorption_policy=priority))
    assert _attacker_hits(default)[0]["unit"] == "knights"
    assert _attacker_hits(elected)[0]["unit"] == "men_at_arms"
    assert elected["battle"]["absorption_policies"] == {"attacker": priority}


def test_storm_priority_survives_defender_front_handoff_and_reload():
    state = _storm_state()
    place(state, "aleksandr", {"men_at_arms": 2}).in_stronghold = True
    move = next(m for m in legal_actions_for_side(state, "teutonic") if m["type"] == "cmd_storm")
    assert "absorption_policy" in move["absorption_policy_template"]
    priority = ["men_at_arms", "knights"]
    result = apply_action_for_side(state, "teutonic", _command(absorption_policy=priority))
    assert result["awaiting_storm_front"]["owed_by"] == "russian"
    state = GameState.model_validate_json(state.model_dump_json())
    result = apply_action_for_side(state, "russian", {
        "type": STORM_FRONT_ACTION, "args": {"lord_id": "gavrilo"},
    })
    assert result["battle"]["defender_storm_positions"]["gavrilo"] == "storm_front"
    assert result["battle"]["absorption_policies"]["attacker"] == priority
    assert _attacker_hits(result)[0]["unit"] == "men_at_arms"


def test_referee_hit_prompts_follow_live_armor_until_it_routs():
    state = _storm_state(seed=1)
    state.lords["hermann"].forces = {
        "knights": 1, "men_at_arms": 1, "militia": 1, "light_horse": 1,
    }
    state.lords["gavrilo"].forces = {"knights": 2, "men_at_arms": 2}
    offered = []

    def choose(decision):
        assert (decision["type"], decision["side"]) == ("storm_attacker_absorb", "attacker")
        offered.append(set(decision["options"]))
        return "men_at_arms" if len(offered) == 1 else "militia"

    result = apply_action(state, _command(prompt_attacker_hits=True, decision_callback=choose))
    assert offered == [{"knights", "men_at_arms"}, {"militia", "light_horse"}]
    assert _attacker_hits(result)[0] == {"unit": "men_at_arms", "absorbed": False}
    assert [d["chosen"] for d in result["battle"]["decisions"]] == ["men_at_arms", "militia"]


def test_referee_can_script_a_storm_hit_choice():
    result = apply_action(_storm_state(), _command(scripted_decisions=[
        {"type": "storm_attacker_absorb", "chosen": "men_at_arms"},
    ]))
    assert _attacker_hits(result)[0]["unit"] == "men_at_arms"


def test_illegal_referee_pick_rolls_back_the_storm():
    state = _storm_state()
    before = state.model_dump_json()
    with pytest.raises(ValueError, match="not in legal options"):
        apply_action(state, _command(
            prompt_attacker_hits=True, decision_callback=lambda _: "militia",
        ))
    assert state.model_dump_json() == before


@pytest.mark.parametrize("priority", [["unknown"], [["knights"]]])
def test_bad_priority_is_rejected_before_the_front_handoff(priority):
    state = _storm_state()
    place(state, "aleksandr", {"men_at_arms": 2}).in_stronghold = True
    before = state.model_dump_json()
    with pytest.raises(IllegalAction, match="bad_absorption_policy"):
        apply_action_for_side(state, "teutonic", _command(absorption_policy=priority))
    assert state.model_dump_json() == before
