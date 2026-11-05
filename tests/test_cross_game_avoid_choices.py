"""N3-03 to N3-05 exercise the public Approach and Avoid actions."""
from __future__ import annotations

from copy import deepcopy

import pytest

from nevsky.actions import IllegalAction, apply_action
from nevsky.llm.tools import apply_action_for_side, legal_actions_for_side, safe_fallback_for_side
from nevsky.scenarios import load_scenario
from nevsky.state import GameState


def approach(*, two_attackers=True, first_loot=0, second_loot=0, ambush=False):
    state = load_scenario("crusade_on_novgorod", seed=1)
    state.meta.phase = "campaign"
    state.meta.campaign_step = "command"
    state.meta.active_player = "teutonic"
    state.campaign_turn.active_card = state.campaign_turn.active_lord = "hermann"
    state.campaign_turn.actions_remaining = 2
    for lord in state.lords.values():
        lord.state, lord.location, lord.in_stronghold = "removed", None, False
        lord.forces, lord.routed_units, lord.assets = {}, {}, {}
    state.locales["pskov"].teutonic_conquered = 0
    state.locales["pskov"].russian_conquered = 0
    state.locales["pskov"].siege_markers = 0
    state.decks.russian.holds = []
    state.decks.teutonic.holds = ["T6"] if ambush else []
    group = ["hermann", "yaroslav"] if two_attackers else ["hermann"]
    for lid in group + ["gavrilo", "domash"]:
        lord = state.lords[lid]
        lord.state = "mustered"
        lord.location = "izborsk" if lid in group else "pskov"
        lord.forces = {"knights": 2} if lid in group else {"militia": 2}
    state.lords["hermann"].assets = {"loot": first_loot} if first_loot else {}
    state.lords["yaroslav"].assets = {"loot": second_loot} if second_loot else {}
    apply_action(state, {"type": "cmd_march", "side": "teutonic",
                         "args": {"lord_id": "hermann", "to": "pskov", "group": group}})
    assert state.meta.active_player == "russian"
    return state


def avoid(state, **args):
    return apply_action_for_side(state, "russian", {
        "type": "avoid_battle", "args": {"to": "dubrovno", **args}})


def allocate(state, **args):
    return apply_action_for_side(state, "teutonic", {"type": "allocate_avoid_spoils", "args": args})


@pytest.mark.parametrize("choice,expected", [
    ({}, (2, 0)), ({"avoid_keep_order": ["domash"]}, (0, 2)),
    ({"avoid_keep": {"gavrilo": 1, "domash": 1}}, (1, 1)),
])
def test_avoid_shares_full_capacity_and_keeps_food_on_owner_mats(choice, expected):
    state = approach(two_attackers=False)
    state.lords["gavrilo"].assets = {"cart": 2, "provender": 2}
    state.lords["domash"].assets = {"provender": 2}
    result = avoid(state, **choice)
    assert tuple(state.lords[lid].assets.get("provender", 0)
                 for lid in ("gavrilo", "domash")) == expected
    assert state.lords["gavrilo"].assets["cart"] == 2
    assert result["spoils_to_attacker"] == {"loot": 0, "provender": 2}


@pytest.mark.parametrize("args,code", [
    ({"lords": ["gavrilo", "domash", "domash"]}, "bad_lords"),
    ({"lords": ["gavrilo", ["domash"]]}, "bad_lords"),
    ({"avoid_keep_order": ["domash", "domash"]}, "bad_avoid_keep_order"),
    ({"avoid_keep": {"domash": 3}}, "bad_avoid_keep"),
    ({"avoid_keep": {"domash": 1}}, "bad_avoid_keep"),
    ({"avoid_keep": {"hermann": 2}}, "bad_avoid_keep"),
    ({"avoid_keep": {"domash": 2}, "avoid_keep_order": []}, "bad_avoid_keep"),
])
def test_invalid_avoid_inputs_reject_before_ambush_with_no_mutation(args, code):
    state = approach(ambush=True)
    state.lords["gavrilo"].assets = {"cart": 2, "provender": 2}
    state.lords["domash"].assets = {"provender": 2}
    cp = state.combat_pending
    before = state.model_dump_json()
    with pytest.raises(IllegalAction, match=code):
        avoid(state, **args)
    assert state.model_dump_json() == before and state.combat_pending is cp


@pytest.mark.parametrize("first", [0, 1, 2])
def test_approaching_owner_can_allocate_any_split_after_save_load(first):
    state = approach()
    state.lords["gavrilo"].assets = {"loot": 2}
    result = avoid(state, spoils_allocation={"hermann": {"loot": 2}})
    assert result["avoid_spoils"] == {"loot": 2} and result["owed_by"] == "teutonic"
    assert not state.lords["hermann"].assets and not state.lords["yaroslav"].assets
    assert state.lords["gavrilo"].location == "dubrovno"
    assert not state.campaign_turn.in_feed_pay_disband
    actions = legal_actions_for_side(state, "teutonic")
    assert [m["type"] for m in actions] == ["allocate_avoid_spoils"]
    assert actions[0]["candidates"]["allocation"] == {"hermann": {"loot": 8},
                                                     "yaroslav": {"loot": 8}}
    assert not legal_actions_for_side(state, "russian")
    saved = GameState.model_validate_json(state.model_dump_json())
    plan = {"hermann": {"loot": first}, "yaroslav": {"loot": 2 - first}}
    original = deepcopy(plan)
    award = allocate(state, allocation=plan)
    assert allocate(saved, allocation=plan) == award
    assert state.model_dump_json() == saved.model_dump_json() and plan == original
    assert state.lords["hermann"].assets.get("loot", 0) == first
    assert state.lords["yaroslav"].assets.get("loot", 0) == 2 - first
    assert state.combat_pending is None and state.campaign_turn.in_feed_pay_disband


@pytest.mark.parametrize("side,action,code", [
    ("russian", {"type": "allocate_avoid_spoils"}, "wrong_actor"),
    ("teutonic", {"type": "end_card"}, "avoid_spoils_pending"),
    ("russian", {"type": "stand_battle"}, "avoid_spoils_pending"),
    *[("teutonic", {"type": "allocate_avoid_spoils", "args": {"allocation": plan}},
       "bad_spoils_allocation") for plan in (
        None, {"gavrilo": {"loot": 2}}, {"yaroslav": {"loot": 3}},
        {"hermann": {"loot": 2}, "yaroslav": {"loot": 1}},
        {"yaroslav": {"loot": True}}, {"yaroslav": {"coin": 1}},
    )],
])
def test_invalid_awards_preserve_pending_pool_and_allow_retry(side, action, code):
    state = approach()
    state.lords["gavrilo"].assets = {"loot": 2}
    avoid(state, lords=["gavrilo"])
    before = state.model_dump_json()
    with pytest.raises(IllegalAction, match=code):
        apply_action_for_side(state, side, action)
    assert state.model_dump_json() == before
    fallback = safe_fallback_for_side(state, "teutonic")
    assert fallback["type"] == "allocate_avoid_spoils"
    result = apply_action(state, fallback)
    assert result["spoils_distribution"] == {"hermann": {"loot": 2}}
    assert result["remaining_defenders"] == ["domash"]
    assert state.meta.active_player == "russian"
    avoid(state)
    assert state.combat_pending is None


def test_full_mats_force_allocation_and_report_cap_overflow_immediately():
    state = approach(first_loot=7, second_loot=7)
    state.lords["gavrilo"].assets = {"loot": 3}
    result = avoid(state)
    assert result["spoils_distribution"] == {"hermann": {"loot": 1}, "yaroslav": {"loot": 1}}
    assert result["spoils_lost_to_cap"] == {"loot": 1}
    assert state.combat_pending is None


@pytest.mark.parametrize("play", [False, True])
def test_ambush_precedes_avoid_spoils_and_only_decline_opens_allocation(play):
    state = approach(ambush=True)
    state.lords["gavrilo"].assets = {"loot": 2}
    assert avoid(state, _post_ambush_decline=True)["ambush_interrupt"]
    assert state.lords["gavrilo"].location == "pskov"
    assert state.lords["gavrilo"].assets == {"loot": 2}
    apply_action_for_side(state, "teutonic", {
        "type": "play_ambush_block" if play else "decline_ambush_block"})
    if play:
        assert state.lords["gavrilo"].assets == {"loot": 2}
        assert state.meta.active_player == "russian"
    else:
        assert state.combat_pending.avoid_spoils == {"loot": 2}
        assert allocate(state, allocation={"yaroslav": {"loot": 2}})["spoils_distribution"] == {
            "yaroslav": {"loot": 2}}
