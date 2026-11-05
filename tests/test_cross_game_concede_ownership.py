"""IF3-01. Battle and Sally Concede declarations belong to their owner."""

from copy import deepcopy

import pytest

from nevsky.actions import IllegalAction, apply_action
from nevsky.llm.session import LLMSession
from nevsky.llm.tools import apply_action_for_side
from nevsky.scenarios import load_scenario


def position():
    state = load_scenario("crusade_on_novgorod", seed=1)
    state.meta.box = 1
    state.meta.phase = "campaign"
    state.meta.campaign_step = "command"
    state.meta.active_player = "teutonic"
    state.campaign_turn.active_card = state.campaign_turn.active_lord = "hermann"
    state.campaign_turn.actions_remaining = 2
    for lord in state.lords.values():
        lord.state = "removed"
        lord.location = None
        lord.in_stronghold = False
        lord.routed_units = {}
        lord.forces = {}
        lord.assets = {}
    state.locales["pskov"].siege_markers = 0
    state.locales["pskov"].teutonic_conquered = 0
    state.locales["pskov"].russian_conquered = 0
    attacker = state.lords["hermann"]
    attacker.state, attacker.location = "mustered", "ostrov"
    attacker.forces = {"knights": 2, "sergeants": 2, "men_at_arms": 3}
    attacker.assets = {"boat": 4}
    defender = state.lords["gavrilo"]
    defender.state, defender.location = "mustered", "pskov"
    defender.forces = {"militia": 2}
    return state


def march(**args):
    return {"type": "cmd_march", "args": {
        "lord_id": "hermann", "to": "pskov", "way_type": "waterway", **args,
    }}


def approach():
    state = position()
    result = apply_action_for_side(state, "teutonic", march())
    assert result["approach"]
    assert state.combat_pending.attacker_concede_round is None
    return state


def besieged_position():
    state = position()
    state.meta.active_player = "russian"
    state.campaign_turn.active_card = state.campaign_turn.active_lord = "gavrilo"
    state.lords["hermann"].location = "pskov"
    state.lords["gavrilo"].in_stronghold = True
    state.locales["pskov"].siege_markers = 1
    return state


@pytest.mark.parametrize("adapter", ["tool", "llm", "human"])
@pytest.mark.parametrize("args", [
    {"concede": "attacker"},
    {"concede_decisions": {"1": "attacker"}},
    {"concede": "defender", "concede_decisions": {"1": "attacker", "2": "defender"}},
])
def test_battle_defender_cannot_concede_the_attacker(adapter, args):
    state = approach()
    action = {"type": "stand_battle", "args": deepcopy(args)}
    original = deepcopy(action)
    saved = state.model_dump_json()
    pending = state.combat_pending
    session = LLMSession(state, "teutonic" if adapter == "human" else "russian",
                         "crusade_on_novgorod")

    with pytest.raises(IllegalAction) as error:
        if adapter == "tool":
            apply_action_for_side(state, "russian", action)
        else:
            session.apply(action, who=adapter)

    assert error.value.code == "wrong_actor"
    assert state.model_dump_json() == saved
    assert state.combat_pending is pending
    assert action == original and not session.history
    result = session.apply({"type": "stand_battle"}, who="human" if adapter == "human" else "llm")
    assert result["winner"] == "teutonic"
    assert result["battle"].get("conceded") is None


@pytest.mark.parametrize("args", [
    {"concede": "defender"},
    {"concede_decisions": {"1": "defender"}},
    {"concede": "attacker", "concede_decisions": {"1": "defender"}},
])
def test_sallying_player_cannot_concede_the_besiegers(args):
    state = besieged_position()
    saved = state.model_dump_json()
    with pytest.raises(IllegalAction) as error:
        apply_action_for_side(state, "russian", {"type": "cmd_sally", "args": args})
    assert error.value.code == "wrong_actor"
    assert state.model_dump_json() == saved


@pytest.mark.parametrize("args", [
    {"concede": "defender"},
    {"concede_decisions": {"1": "defender"}},
])
def test_defender_can_concede_own_side(args):
    state = approach()
    session = LLMSession(state, "russian", "crusade_on_novgorod")
    action = {"type": "stand_battle", "args": args}
    result = session.apply(action)
    assert result["winner"] == "teutonic"
    assert result["battle"]["conceded"] == "defender"
    assert session.history[0]["action"] == {**action, "side": "russian"}
    assert "side" not in action


def test_attacker_cannot_stand_for_the_defender_during_ambush():
    state = approach()
    state.decks.teutonic.holds.append("T6")
    result = apply_action_for_side(state, "russian", {
        "type": "avoid_battle", "args": {"to": "dubrovno"},
    })
    assert result["ambush_interrupt"] and result["owed_by"] == "teutonic"
    saved = state.model_dump_json()
    action = {"type": "stand_battle", "args": {"concede": "defender"}}

    with pytest.raises(IllegalAction) as error:
        apply_action_for_side(state, "teutonic", action)

    assert error.value.code == "wrong_actor"
    assert state.model_dump_json() == saved
    assert apply_action_for_side(state, "teutonic", {"type": "play_ambush_block"})["ambush_blocked"]
    result = apply_action_for_side(state, "russian", action)
    assert result["battle"]["conceded"] == "defender"


def test_marching_player_declaration_survives_save_and_outranks_defender(tmp_path):
    session = LLMSession(position(), "teutonic", "crusade_on_novgorod")
    session.apply(march(concede=1))
    save = tmp_path / "before_response.json"
    session.save(save)

    loaded = LLMSession.load(save)
    assert loaded.state.combat_pending.attacker_concede_round == 1
    result = loaded.apply(
        {"type": "stand_battle", "args": {"concede": "defender"}}, who="human",
    )
    assert result["winner"] == "russian"
    assert result["battle"]["conceded"] == "attacker"


def test_sallying_player_can_concede_own_side():
    state = besieged_position()
    result = apply_action_for_side(state, "russian", {
        "type": "cmd_sally", "args": {"concede": "attacker"},
    })
    assert result["battle"]["conceded"] == "attacker"
    assert result["sally_outcome"] == "withdrew"


@pytest.mark.parametrize("kind", ["stand_battle", "cmd_sally"])
def test_referee_can_submit_opponent_concede_for_scripted_combat(kind):
    state = approach() if kind == "stand_battle" else besieged_position()
    concede = "attacker" if kind == "stand_battle" else "defender"
    result = apply_action(state, {
        "type": kind, "side": "russian", "args": {"concede_decisions": {"1": concede}},
    })
    assert result["battle"]["conceded"] == concede
