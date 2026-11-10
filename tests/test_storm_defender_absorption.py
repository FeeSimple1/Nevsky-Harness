"""N6-03-F. A Storm defender assigns Hits within the Garrison and Front Lord."""

import pytest

from nevsky.actions import IllegalAction, apply_action
from nevsky.llm.tools import apply_action_for_side, legal_actions_for_side, safe_fallback_for_side
from nevsky.state import STORM_FRONT_ACTION, GameState
from tests.test_cross_game_relief_retreat import position
from tests.test_round7_combat_limits import _place_with_vassals


def _position(*, besieged_lord=True):
    state = position(seed=1, box=9)
    state.meta.active_player = "russian"
    state.campaign_turn.active_card = state.campaign_turn.active_lord = "aleksandr"
    for lord in state.lords.values():
        lord.forces = {}
    aleksandr = _place_with_vassals(
        state, "aleksandr", "aleksandr_pereyaslavl", "aleksandr_rostov", "aleksandr_yaroslavl",
    )
    aleksandr.location = "dorpat"
    aleksandr.assets = {"provender": 2}
    aleksandr.this_lord_capabilities = ["R3"]
    state.decks.russian.deck.remove("R3")
    if besieged_lord:
        hermann = _place_with_vassals(state, "hermann")
        hermann.location = "dorpat"
        hermann.in_stronghold = True
    else:
        _place_with_vassals(state, "heinrich").location = "fellin"
    state.locales["dorpat"].siege_markers = 3
    return state


def _command(**args):
    return {"type": "cmd_storm", "side": "russian", "args": {"lord_id": "aleksandr", **args}}


def _defending_hits(battle):
    return [target for entry in battle["log"] for step in entry["steps"]
            if step["step"].endswith("_attacker") for target in step["distribution"]]


def test_defender_can_rank_garrison_and_lord_independently_after_reload():
    state = _position()
    dice = state.meta.rng_state
    result = apply_action_for_side(state, "russian", _command())
    assert result["awaiting_storm_front"] == {"owed_by": "teutonic", "locale": "dorpat"}
    assert state.meta.rng_state == dice
    assert state.campaign_turn.actions_remaining == 2
    assert not legal_actions_for_side(state, "russian")

    state = GameState.model_validate_json(state.model_dump_json())
    move, = legal_actions_for_side(state, "teutonic")
    assert move["type"] == STORM_FRONT_ACTION
    assert move["args"] == {"lord_id": "hermann"}
    assert set(move["args_template"]) == {"absorption_policy", "garrison_absorption_policy"}
    assert move["absorption_policy_options"]["garrison_absorption_policy"] == [
        "knights", "men_at_arms",
    ]
    defense = {**move, "args": {**move["args"], "absorption_policy": ["men_at_arms"],
                               "garrison_absorption_policy": ["knights"]}}
    restored = GameState.model_validate_json(state.model_dump_json())
    result = apply_action_for_side(state, "teutonic", defense)
    assert apply_action_for_side(restored, "teutonic", defense) == result
    assert restored.model_dump_json() == state.model_dump_json()

    battle = result["battle"]
    assert battle["absorption_policies"] == {
        "defender": ["men_at_arms"], "garrison": ["knights"],
    }
    hits = _defending_hits(battle)
    assert [row["target"] for row in hits[:4]] == ["garrison"] * 3 + ["lord"]
    assert [row["unit"] for row in hits[:3]] == ["knights", "men_at_arms", "men_at_arms"]
    assert all(not row["absorbed"] for row in hits[:3])
    assert hits[3]["lord"] == "hermann" and hits[3]["routed"][0]["unit"] == "men_at_arms"


def test_mixed_garrison_alone_has_defender_choice_and_safe_default():
    state = _position(besieged_lord=False)
    result = apply_action_for_side(state, "russian", _command())
    assert result["awaiting_storm_front"]["owed_by"] == "teutonic"
    move, = legal_actions_for_side(state, "teutonic")
    assert move["args"] == {"lord_id": None}
    assert set(move["args_template"]) == {"garrison_absorption_policy"}
    control = state.model_copy(deep=True)
    fallback = safe_fallback_for_side(control, "teutonic")
    assert fallback["args"] == {"lord_id": None}
    result = apply_action_for_side(control, "teutonic", fallback)
    assert _defending_hits(result["battle"])[0]["unit"] == "men_at_arms"
    result = apply_action_for_side(state, "teutonic", {
        **move, "args": {"garrison_absorption_policy": ["knights"]},
    })
    hits = _defending_hits(result["battle"])
    assert hits[0]["unit"] == "knights"
    assert all(row["target"] == "garrison" for row in hits)


@pytest.mark.parametrize("mode", ["script", "callback"])
def test_referee_can_elect_live_garrison_and_front_lord_units(mode):
    prompts = []

    def choose(decision):
        prompts.append(decision)
        if decision["type"] == "storm_garrison_absorb":
            return "knights"
        return decision["options"][0]

    args = {
        "script": {"scripted_decisions": [
            {"type": "storm_garrison_absorb", "chosen": "knights"},
            {"type": "storm_defender_absorb", "chosen": "militia"},
        ]},
        "callback": {"prompt_defender_hits": True, "decision_callback": choose},
    }[mode]
    battle = apply_action(_position(), _command(**args))["battle"]
    garrison, lord, *_ = battle["decisions"]
    assert (garrison["type"], garrison["side"], garrison["chosen"]) == (
        "storm_garrison_absorb", "defender", "knights",
    )
    assert set(garrison["options"]) == {"knights", "men_at_arms"}
    assert garrison["info"]["armor_minus_2"]
    assert (lord["type"], lord["side"], lord["chosen"]) == (
        "storm_defender_absorb", "defender", "militia",
    )
    assert {"knights", "militia"} <= set(lord["options"])
    assert lord["info"]["lord_id"] == "hermann" and not lord["info"]["armor_minus_2"]
    hits = _defending_hits(battle)
    assert hits[3]["routed"][0]["unit"] == "militia"
    if mode == "callback":
        assert [p["type"] for p in prompts[:2]] == [garrison["type"], lord["type"]]


def test_attackers_cannot_set_defender_priorities_and_bad_choices_are_atomic():
    state = _position()
    before = state.model_dump_json()
    for field in ("defender_absorption_policy", "garrison_absorption_policy"):
        with pytest.raises(IllegalAction, match="wrong_actor"):
            apply_action_for_side(state, "russian", _command(**{field: ["knights"]}))
        assert state.model_dump_json() == before
    with pytest.raises(ValueError, match="not in legal options"):
        apply_action(state, _command(prompt_defender_hits=True, decision_callback=lambda _: "militia"))
    assert state.model_dump_json() == before

    apply_action_for_side(state, "russian", _command())
    before = state.model_dump_json()
    with pytest.raises(IllegalAction, match="bad_absorption_policy"):
        apply_action_for_side(state, "teutonic", {
            "type": STORM_FRONT_ACTION, "args": {"garrison_absorption_policy": ["invalid"]},
        })
    assert state.model_dump_json() == before
