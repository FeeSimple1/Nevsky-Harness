"""March-menu regressions from multi-policy Crusade seed 20261012.

The captured state is from play. Other positions deliberately isolate the
same rules (Converts, shared Transport and voluntary discard to move Unladen).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nevsky.actions import apply_action
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import load_scenario
from nevsky.state import GameState

DATA = Path(__file__).parent / "data" / "convergence_20261010"


def minimal(move):
    return {key: move[key] for key in ("type", "side", "args")}


def command(*, provender=2, carts=1, converts=False, horse=True, remaining=1):
    state = load_scenario("crusade_on_novgorod", seed=20261012)
    for side in ("teutonic", "russian"):
        apply_action(state, {"type": "confirm_all_setup_transports", "side": side, "args": {}})
    state.meta.phase = "campaign"
    state.meta.campaign_step = "command"
    state.meta.active_player = "teutonic"
    state.meta.box = 1
    turn = state.campaign_turn
    turn.active_card = turn.active_lord = "yaroslav"
    turn.actions_remaining = remaining
    turn.actions_used_this_card = 1
    lord = state.lords["yaroslav"]
    lord.location = "odenpah"
    lord.assets = {"provender": provender, "cart": carts}
    lord.this_lord_capabilities = ["T3"] if converts else []
    lord.first_march_used_this_card = False
    if not horse:
        lord.forces.pop("light_horse", None)
    return state


def moves(state, group=None):
    before = state.model_dump_json()
    result = [
        m
        for m in legal_moves(state, with_previews=False)
        if m["type"] == "cmd_march"
        and m["args"].get("to") == "dorpat"
        and m["args"].get("way_type") == "trackway"
        and not m["args"].get("concede")
    ]
    assert state.model_dump_json() == before
    if group is not None:
        result = [
            m for m in result if set(m["args"].get("group", [m["args"]["lord_id"]])) == set(group)
        ]
    return result


def test_captured_zero_cost_converts_march_is_visible():
    state = GameState.model_validate_json((DATA / "converts_march.json").read_text())
    palette = moves(state)
    assert palette, "Yaroslav can make the first Converts March with one action remaining"
    result = apply_action(state, minimal(palette[0]))
    assert result["cost"] == 0
    assert state.lords["yaroslav"].location == "dorpat"
    assert state.campaign_turn.actions_remaining == 1


@pytest.mark.parametrize("converts", [False, True])
@pytest.mark.parametrize("provender,carts", [(0, 0), (1, 0), (2, 1), (5, 1), (1, 2)])
@pytest.mark.parametrize("remaining", [1, 2])
def test_menu_contains_an_affordable_march_and_all_variants_apply(
    converts, provender, carts, remaining
):
    state = command(provender=provender, carts=carts, converts=converts, remaining=remaining)
    palette = moves(state)
    assert palette, "A legal March, optionally discarding to Unladen, must not be hidden"
    for option in palette:
        probe = state.model_copy(deep=True)
        result = apply_action(probe, minimal(option))
        assert result["cost"] <= remaining
        assert probe.lords["yaroslav"].location == "dorpat"
    if converts:
        assert any(not m["args"].get("discard_to_unladen") for m in palette)
        probe = state.model_copy(deep=True)
        normal = next(m for m in palette if not m["args"].get("discard_to_unladen"))
        assert apply_action(probe, minimal(normal))["cost"] == 0


def test_discard_to_unladen_is_an_optional_choice_not_automatic_when_laden_fits():
    state = command(remaining=2)
    palette = moves(state)
    normal = next(m for m in palette if not m["args"].get("discard_to_unladen"))
    discard = next(m for m in palette if m["args"].get("discard_to_unladen"))
    keep_state, drop_state = state.model_copy(deep=True), state.model_copy(deep=True)
    assert apply_action(keep_state, minimal(normal))["cost"] == 2
    assert keep_state.lords["yaroslav"].assets["provender"] == 2
    assert apply_action(drop_state, minimal(discard))["cost"] == 1
    assert drop_state.lords["yaroslav"].assets["provender"] == 1


@pytest.mark.parametrize("horse,used", [(False, False), (True, True)])
def test_converts_does_not_make_ineligible_march_free(horse, used):
    state = command(converts=True, horse=horse, remaining=2)
    state.lords["yaroslav"].first_march_used_this_card = used
    normal = next(m for m in moves(state) if not m["args"].get("discard_to_unladen"))
    assert apply_action(state, minimal(normal))["cost"] == 2


def test_shared_transport_group_is_offered_when_solo_lord_cannot_keep_cargo():
    state = command()
    state.campaign_turn.active_lord = state.campaign_turn.active_card = "hermann"
    hermann = state.lords["hermann"]
    hermann.location = "odenpah"
    hermann.assets = {"provender": 2, "cart": 1}
    state.lords["yaroslav"].assets = {"cart": 2}
    group = ["hermann", "yaroslav"]
    option = next(m for m in moves(state, group) if not m["args"].get("discard_to_unladen"))
    assert apply_action(state, minimal(option))["cost"] == 1
    assert hermann.assets["provender"] == 2
    assert all(state.lords[lid].location == "dorpat" for lid in group)


def test_group_member_converts_and_another_members_light_horse_enable_free_march():
    state = command(provender=0, carts=0, converts=True)
    state.campaign_turn.active_lord = state.campaign_turn.active_card = "hermann"
    state.lords["hermann"].location = "odenpah"
    state.lords["hermann"].assets = {"provender": 2, "cart": 1}
    state.lords["hermann"].forces["light_horse"] = 1
    state.lords["yaroslav"].forces.pop("light_horse", None)
    option = next(
        m for m in moves(state, ["hermann", "yaroslav"]) if not m["args"].get("discard_to_unladen")
    )
    assert apply_action(state, minimal(option))["cost"] == 0
    assert state.campaign_turn.actions_remaining == 1


def test_lieutenant_keeps_lower_lord_in_discard_variant():
    state = command(provender=0, carts=1)
    lower = state.lords["knud_and_abel"]
    lower.location = "odenpah"
    lower.assets = {"provender": 2, "loot": 1}
    lower.lieutenant_of = "yaroslav"
    state.lords["yaroslav"].has_lower_lord = "knud_and_abel"
    option = next(
        m
        for m in moves(state, ["yaroslav", "knud_and_abel"])
        if m["args"].get("discard_to_unladen")
    )
    assert apply_action(state, minimal(option))["cost"] == 1
    assert lower.location == state.lords["yaroslav"].location == "dorpat"
    assert lower.assets.get("loot", 0) == 0
