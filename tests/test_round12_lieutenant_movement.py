"""N12-01-F. Public movement and aftermath preserve a live Lieutenant pair."""

import pytest

from nevsky.actions import IllegalAction, apply_action
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import load_scenario
from nevsky.state import GameState

PAIR = ["gavrilo", "vladislav"]


def act(state, kind, side="russian", **args):
    return apply_action(state, {"type": kind, "side": side, "args": args})


def reject(state, code, kind, side="russian", **args):
    before = state.model_dump_json()
    with pytest.raises(IllegalAction) as exc:
        act(state, kind, side, **args)
    assert exc.value.code == code
    assert state.model_dump_json() == before


def plan_position():
    state = load_scenario("pleskau", seed=1)
    act(state, "system_setup_complete", "system")
    state.meta.phase = "campaign"
    state.meta.campaign_step = "plan"
    state.meta.first_levy_done = True
    return state


def plan(state, teutonic=None):
    for side, cards in [("teutonic", teutonic or ["hermann"] * 3 + ["yaroslav"] * 3),
                        ("russian", ["gavrilo"] * 3 + ["vladislav"] * 3)]:
        for card in cards:
            act(state, "plan_add_card", side, card=card)
        act(state, "finalize_plan", side)
    act(state, "command_reveal", "teutonic")


def approach(*, paired=True, city=False):
    """Native Pleskau mats, with the first Approach staged at a Fort or City."""
    state = plan_position()
    origin, destination = ("izborsk", "pskov") if city else ("lettgallia", "izborsk")
    if city:
        state.locales[origin].siege_markers = 1
    state.lords["hermann"].location = origin
    for lid in PAIR:
        state.lords[lid].location = destination
    if paired:
        act(state, "place_lieutenant", lieutenant=PAIR[0], lower_lord=PAIR[1])
    plan(state)
    act(state, "cmd_march", "teutonic", to=destination, way_type="trackway")
    return state


def next_russian_card(state):
    for side in ("teutonic", "russian"):
        act(state, "fpd_resolve", side, decline_pay=True)
    act(state, "command_reveal")


def test_pair_cannot_avoid_or_withdraw_separately_into_fort():
    state = approach()
    moves = legal_moves(state, with_previews=False)
    assert not any(move["type"] == "withdraw" for move in moves)
    assert all("lords" not in move["args"] for move in moves if move["type"] == "avoid_battle")
    reject(state, "lower_lord_required", "avoid_battle", lords=[PAIR[0]], to="pskov")
    reject(state, "lieutenant_required", "withdraw", lords=[PAIR[1]])
    reject(state, "over_capacity", "withdraw")

    # The same saved Approach still allows the whole pair to Avoid, and
    # the next Command can March both from their shared destination.
    restored = GameState.model_validate_json(state.model_dump_json())
    move = next(m for m in moves if m["type"] == "avoid_battle" and m["args"]["to"] == "pskov")
    assert apply_action(state, move) == apply_action(restored, move)
    assert state.model_dump_json() == restored.model_dump_json()
    next_russian_card(state)
    act(state, "cmd_march", to="dubrovno", group=PAIR)
    assert {state.lords[lid].location for lid in PAIR} == {"dubrovno"}


def test_withdraw_can_take_whole_pair_or_an_independent_lord():
    state = approach(city=True)
    act(state, "withdraw")
    assert all(state.lords[lid].in_stronghold for lid in PAIR)
    assert state.lords[PAIR[0]].has_lower_lord == PAIR[1]

    state = approach(paired=False)
    act(state, "avoid_battle", lords=[PAIR[0]], to="pskov")
    act(state, "withdraw", lords=[PAIR[1]])
    assert state.lords[PAIR[0]].location == "pskov"
    assert state.lords[PAIR[1]].in_stronghold


@pytest.mark.parametrize("command", ["march", "sail"])
def test_marshal_cannot_take_only_one_member_of_another_pair(command):
    state = plan_position()
    leader, upper, lower = "hermann", "yaroslav", "knud_and_abel"
    for lid in (leader, upper, lower):
        state.lords[lid].location = "lettgallia" if command == "march" else "reval"
    act(state, "place_lieutenant", "teutonic", lieutenant=upper, lower_lord=lower)
    plan(state)
    if command == "march":
        dest = "adsel"
        route = {"to": dest, "discard_excess_provender": True}
    else:
        dest = "narwia"
        # Stage four additional Ships from earlier Levy for the native mats.
        state.lords[leader].assets["ship"] = 4
        route = {"destination": dest, "discard_excess_provender": True}
    reject(state, "lieutenant_required", f"cmd_{command}", "teutonic", group=[leader, lower], **route)
    reject(state, "lower_lord_required", f"cmd_{command}", "teutonic", group=[leader, upper], **route)
    act(state, f"cmd_{command}", "teutonic", group=[leader, upper, lower], **route)
    assert {state.lords[lid].location for lid in (leader, upper, lower)} == {dest}


def test_battle_retreat_rejects_split_and_uses_either_partners_destination():
    state = approach()
    reject(state, "split_stack", "stand_battle", concede="defender",
           retreat_to={PAIR[0]: "pskov", PAIR[1]: "ugaunia"})
    reject(state, "lower_lord_required", "stand_battle", concede="defender",
           withdraw_losers=[PAIR[0]])
    restored = GameState.model_validate_json(state.model_dump_json())
    result = act(state, "stand_battle", concede="defender", retreat_to={PAIR[1]: "ugaunia"})
    assert result == act(restored, "stand_battle", concede="defender", retreat_to={PAIR[1]: "ugaunia"})
    assert state.model_dump_json() == restored.model_dump_json()
    assert not result["removed"]
    assert {state.lords[lid].location for lid in PAIR} == {"ugaunia"}
    assert state.lords[PAIR[0]].has_lower_lord == PAIR[1]


def test_battle_removal_leaves_single_lord_free_to_withdraw():
    state = approach()
    result = act(state, "stand_battle", concede="defender",
                 remove_losers=[PAIR[1]], withdraw_losers=True)
    assert result["removed"] == [PAIR[1]]
    assert result["withdrew"] == [PAIR[0]]
    assert state.lords[PAIR[0]].has_lower_lord is None
    assert state.lords[PAIR[0]].in_stronghold


def test_saved_sally_retreat_uses_pair_destination():
    state = plan_position()
    upper, lower = "yaroslav", "knud_and_abel"
    for lid in (upper, lower):
        state.lords[lid].location = "pskov"
    state.locales["pskov"].siege_markers = 1
    state.lords["gavrilo"].in_stronghold = True
    act(state, "place_lieutenant", "teutonic", lieutenant=upper, lower_lord=lower)
    plan(state, teutonic=["pass"] + ["hermann"] * 3 + ["yaroslav"] * 2)
    next_russian_card(state)
    act(state, "cmd_sally", concede="defender", choose_loser_fate=True)
    state = GameState.model_validate_json(state.model_dump_json())
    [move] = legal_moves(state, with_previews=False)
    assert move["retreat_pairs"] == [[upper, lower]]
    first, second, *_ = move["retreat_destinations"]
    reject(state, "split_stack", move["type"], "teutonic", retreat_to={upper: first, lower: second})
    result = act(state, move["type"], "teutonic", retreat_to={lower: second})
    assert result["siege_lifted"]
    assert {state.lords[lid].location for lid in (upper, lower)} == {second}


@pytest.mark.parametrize("old_split", ["locale", "inside"])
def test_loading_an_old_split_releases_links_without_moving_either_lord(old_split):
    state = approach()
    # Simulate a save left by the earlier split-response bug.
    if old_split == "locale":
        state.lords[PAIR[1]].location = "pskov"
        state.lords[PAIR[1]].moved_fought = True
    else:
        state.lords[PAIR[1]].in_stronghold = True
        state.locales["izborsk"].siege_markers = 1
        state.combat_pending.withdrawn_lords = [PAIR[1]]
    state.combat_pending.defender_lords = [PAIR[0]]
    restored = GameState.model_validate_json(state.model_dump_json())
    state.lords[PAIR[0]].has_lower_lord = None
    state.lords[PAIR[1]].lieutenant_of = None
    assert restored.model_dump_json() == state.model_dump_json()
