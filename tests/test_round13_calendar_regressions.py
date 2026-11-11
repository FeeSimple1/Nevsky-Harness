"""Round 13: Disband return timing and Dietrich's mandatory Calendar shift."""

import pytest

from nevsky.actions import (
    IllegalAction,
    _find_cylinder_box,
    _find_service_marker_box,
    _place_lord_on_map,
    apply_action,
)
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import load_scenario
from nevsky.state import GameState, move_vassal_marker
from nevsky.static_data import load_lords


def _act(state, kind, side="teutonic", **args):
    return apply_action(state, {"type": kind, "side": side, "args": args})


def _scenario(name):
    state = load_scenario(name, seed=13)
    for side in ("teutonic", "russian"):
        _act(state, "confirm_all_setup_transports", side)
    return state


def _set_calendar(state, box, phase="levy"):
    state.meta.box = box
    state.meta.phase = phase
    state.meta.first_levy_done = True
    for entry in state.calendar.boxes:
        entry.has_levy_campaign_marker = entry.box == box
        entry.levy_campaign_face = phase if entry.box == box else None


def _set_service(state, lord_id, box):
    for entry in state.calendar.boxes:
        if lord_id in entry.service_markers:
            entry.service_markers.remove(lord_id)
    state.calendar.boxes[box - 1].service_markers.append(lord_id)


def _disband_position(phase):
    state = _scenario("crusade_on_novgorod")
    _set_calendar(state, 4, phase)
    _place_lord_on_map(state, "andreas", "fellin", 4)
    for lid, lord in state.lords.items():
        if lord.state == "mustered":
            _set_service(state, lid, 4 + int(load_lords()[lid]["ratings"]["service"]))
    state.meta.active_player = "teutonic"
    state.meta.levy_step = "muster" if phase == "levy" else "done"
    state.meta.campaign_step = "command"
    if phase == "campaign":
        state.campaign_turn.active_lord = "andreas"
        state.campaign_turn.active_card = "andreas"
        state.campaign_turn.actions_remaining = 3
    return state


@pytest.mark.parametrize("phase,return_box", [("levy", 8), ("campaign", 9)])
@pytest.mark.parametrize("service_box", [8, 9])
def test_heinrich_curia_returns_cylinder_based_on_current_turn(phase, return_box, service_box):
    state = _disband_position(phase)
    _place_lord_on_map(state, "heinrich", "leal", 4)
    _set_service(state, "heinrich", service_box)
    deck = state.decks.teutonic
    deck.deck.remove("T13")
    deck.holds.append("T13")
    state = GameState.model_validate_json(state.model_dump_json())
    recipients = ["andreas", "yaroslav"]
    starting_coin = {lid: state.lords[lid].assets.get("coin", 0) for lid in recipients}

    _act(state, "aow_play_hold", card_id="T13", recipients=recipients)

    assert state.lords["heinrich"].state == "disbanded"
    assert _find_service_marker_box(state, "heinrich") is None
    assert _find_cylinder_box(state, "heinrich") == return_box
    for lid, coin in starting_coin.items():
        assert state.lords[lid].assets["coin"] == min(8, coin + 4)


@pytest.mark.parametrize("phase,return_box", [("levy", 8), ("campaign", 9)])
@pytest.mark.parametrize("expiry_box", [3, 4])
def test_final_forces_expire_with_advanced_vassal_service(phase, return_box, expiry_box):
    state = _disband_position(phase)
    state.meta.optional_rules["advanced_vassal_service"] = True
    lid, vid = "hermann", "hermann_ugaunian_aux"
    _place_lord_on_map(state, lid, "dorpat", 4)
    _set_service(state, lid, 6)
    lord = state.lords[lid]
    # Only the Ugaunian Auxiliaries' native Forces remain after combat.
    lord.forces = dict(next(v["forces"] for v in load_lords()[lid]["vassals"]
                            if v["vassal_id"] == vid))
    vassal = lord.vassals[vid]
    vassal.mustered, vassal.ready = True, False
    move_vassal_marker(state.calendar, vid, vassal, expiry_box)
    state = GameState.model_validate_json(state.model_dump_json())

    if phase == "levy":
        state.meta.levy_step = "disband"
        _act(state, "disband_resolve")
    else:
        state.campaign_turn.actions_remaining = 0
        state.campaign_turn.in_feed_pay_disband = True
        _act(state, "fpd_resolve", decline_pay=True)

    assert state.lords[lid].state == "disbanded"
    assert _find_cylinder_box(state, lid) == return_box
    assert not state.lords[lid].vassals[vid].on_calendar


@pytest.mark.parametrize("on_map", [True, False], ids=["services", "cylinders"])
def test_dietrich_requires_an_available_marker_and_offers_both_directions(on_map):
    state = _scenario("watland" if on_map else "crusade_on_novgorod")
    if on_map:
        _place_lord_on_map(state, "rudolf", "wenden", 4)
    _set_calendar(state, 5 if on_map else 2)
    state.meta.levy_step = "arts_of_war"
    state.meta.active_player = "russian"
    deck = state.decks.russian
    deck.deck.remove("R17")
    deck.pending_draw.append("R17")
    target, invalid = ("service:andreas", "andreas") if on_map else ("andreas", "service:andreas")
    find_box = _find_service_marker_box if on_map else _find_cylinder_box
    initial = find_box(state, "andreas")

    before = state.model_dump_json()
    with pytest.raises(IllegalAction) as exc:
        _act(state, "aow_implement_card", "russian", target=invalid)
    assert exc.value.code == "ineligible_target"
    assert state.model_dump_json() == before

    moves = [m["args"] for m in legal_moves(state)
             if m["type"] == "aow_implement_card"]
    assert {(m["target"], m["direction"]) for m in moves} == {
        (choice, direction)
        for choice in (target, target.replace("andreas", "rudolf"))
        for direction in ("left", "right")
    }

    right = GameState.model_validate_json(before)
    _act(right, "aow_implement_card", "russian", target=target, direction="right")
    assert find_box(right, "andreas") == initial + 1
    _act(state, "aow_implement_card", "russian")
    assert find_box(state, "andreas") == initial - 1
    assert set(state.meta.block_lords_this_levy_t) == {"andreas", "rudolf"}
    assert not state.decks.russian.pending_draw
