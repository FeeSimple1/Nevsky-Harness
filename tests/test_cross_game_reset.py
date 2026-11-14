"""Cross-game N4/N5: empty-Lord Disband and voluntary Reset Capabilities."""
from __future__ import annotations

import pytest

from nevsky.actions import IllegalAction, apply_action
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import load_scenario
from nevsky.state import GameState, move_vassal_marker
from nevsky.static_data import load_lords


def end_campaign(box=3, side="teutonic"):
    state = load_scenario("crusade_on_novgorod", seed=42)
    state.meta.phase = "campaign"
    state.meta.campaign_step = "end_campaign"
    state.meta.active_player = side
    state.meta.box = box
    state.meta.end_campaign_completed_t = False
    state.meta.end_campaign_completed_r = False
    for cb in state.calendar.boxes:
        cb.has_levy_campaign_marker = cb.box == box
        cb.levy_campaign_face = "campaign" if cb.box == box else None
    return state


def resolve(state, side="teutonic", **args):
    return apply_action(state, {"type": "end_campaign_resolve", "side": side, "args": args})


def card_in(state, cid, zone, lord=None):
    deck = state.decks.teutonic if cid.startswith("T") else state.decks.russian
    for name in ("deck", "discard", "holds", "pending_draw", "capabilities_in_play"):
        pile = getattr(deck, name)
        while cid in pile:
            pile.remove(cid)
    for mat in state.lords.values():
        if cid in mat.this_lord_capabilities:
            mat.this_lord_capabilities.remove(cid)
    if lord is None:
        getattr(deck, zone).append(cid)
    else:
        state.lords[lord].this_lord_capabilities.append(cid)


def place(state, lid, forces):
    lord = state.lords[lid]
    lord.state = "mustered"
    lord.location = "pskov" if lord.side == "russian" else "dorpat"
    lord.forces = dict(forces)
    for cb in state.calendar.boxes:
        if lid in cb.cylinders:
            cb.cylinders.remove(lid)
        if lid in cb.service_markers:
            cb.service_markers.remove(lid)
    state.calendar.boxes[10].service_markers.append(lid)
    return lord


@pytest.mark.parametrize("box,besieged", [(2, False), (6, True), (15, False)])
def test_last_serf_returns_lord_to_calendar_and_cleans_mat(box, besieged):
    state = end_campaign(box)
    lord = place(state, "gavrilo", {"serfs": 1})
    lord.in_stronghold = besieged
    lord.assets = {"coin": 1}
    card_in(state, "R2", "this_lord_capabilities", lord.lord_id)
    vid, vassal = next(iter(lord.vassals.items()))
    vassal.mustered = True
    move_vassal_marker(state.calendar, vid, vassal, 12)
    resolve(state)
    result = resolve(state, "russian")
    target = box + 1 + load_lords()[lord.lord_id]["ratings"]["service"]
    assert lord.state == "disbanded" and lord.location is None
    assert lord.assets == lord.forces == {} and not lord.this_lord_capabilities
    assert "R2" in state.decks.russian.deck
    assert not any(lord.lord_id in cb.service_markers for cb in state.calendar.boxes)
    assert not vassal.mustered and not vassal.on_calendar
    assert not any(vid in cb.vassal_service_markers for cb in state.calendar.boxes)
    assert ((lord.lord_id in state.calendar.off_right) if target > 16
            else (lord.lord_id in state.calendar.boxes[target - 1].cylinders))
    assert result["serfs_returned"] == [{"lord_id": lord.lord_id, "count": 1,
                                         "lord_disbanded": True}]
    assert GameState.model_validate_json(state.model_dump_json()) == state


def test_serf_return_preserves_a_lord_with_other_forces():
    state = end_campaign()
    lord = place(state, "gavrilo", {"serfs": 1, "militia": 1})
    resolve(state)
    resolve(state, "russian")
    assert lord.state == "mustered" and lord.forces == {"militia": 1}


def test_last_serf_of_last_russian_lord_ends_campaign_without_advancing():
    state = end_campaign()
    for lord in state.lords.values():
        if lord.side == "russian" and lord.lord_id != "gavrilo":
            lord.state = "ready"
            lord.location = None
    place(state, "gavrilo", {"serfs": 1})
    resolve(state)
    result = resolve(state, "russian")
    assert state.meta.game_over and state.meta.winner == "teutonic"
    assert state.meta.campaign_step == "done" and state.meta.box == 3
    assert result["game_over"] and not result["advanced_to_next_levy"]
    assert legal_moves(state) == []


def test_reset_menu_and_action_cover_holds_side_and_this_lord_capabilities():
    state = end_campaign()
    card_in(state, "T6", "holds")
    card_in(state, "T13", "capabilities_in_play")
    card_in(state, "T2", "this_lord_capabilities", "hermann")
    state.legate.william_of_modena_in_play = True
    state.legate.location = "locale"
    state.legate.locale_id = "dorpat"
    move = next(m for m in legal_moves(state, with_previews=False)
                if m["type"] == "end_campaign_resolve")
    assert move["candidates"]["reset_discard"] == ["T13", "T2", "T6"]
    result = resolve(state, reset_discard=["T6", "T13", "T2"])
    assert result["reset_discard"] == ["T6", "T13", "T2"]
    assert not state.legate.william_of_modena_in_play
    assert state.legate.location == "card" and state.legate.locale_id is None
    for cid in result["reset_discard"]:
        assert state.decks.teutonic.deck.count(cid) == 1
        assert cid not in state.decks.teutonic.discard
        assert cid not in state.decks.teutonic.holds
        assert cid not in state.decks.teutonic.capabilities_in_play
        assert cid not in state.lords["hermann"].this_lord_capabilities


@pytest.mark.parametrize("side,lid,cid,unit,count", [
    ("teutonic", "andreas", "T11", "knights", 3),
    ("russian", "aleksandr", "R10", "asiatic_horse", 2),
])
def test_reset_capability_cascades_special_vassals_and_empty_lord(side, lid, cid, unit, count):
    state = end_campaign(side=side)
    lord = place(state, lid, {unit: count})
    lord.assets = {"coin": 1}
    card_in(state, cid, "capabilities_in_play")
    vid, vs = next((vid, vs) for vid, vs in lord.vassals.items()
                   if any(v["vassal_id"] == vid and v.get("special")
                          for v in load_lords()[lid]["vassals"]))
    vs.mustered = True
    move_vassal_marker(state.calendar, vid, vs, 10)
    result = resolve(state, side, reset_discard=[cid])
    assert lord.state == "disbanded" and lord.location is None
    assert not lord.forces and not lord.assets
    assert not vs.mustered and not vs.ready and not vs.on_calendar
    removals = result["reset_cleanup"][0]["disbanded_vassals"]
    assert any(v.get("lord_disbanded") for v in removals)
    deck = getattr(state.decks, side)
    assert deck.deck.count(cid) == 1 and cid not in deck.discard
    target_box = 3 + 1 + load_lords()[lid]["ratings"]["service"]
    assert lid in state.calendar.boxes[target_box - 1].cylinders


def test_automatic_summer_vassal_disband_counts_from_new_levy_and_does_not_end_game():
    state = end_campaign(box=4)
    for lord in state.lords.values():
        if lord.side == "teutonic" and lord.lord_id != "andreas":
            lord.state = "ready"
            lord.location = None
    lord = place(state, "andreas", {"knights": 3})
    lord.vassals["andreas_summer_crusaders_1"].mustered = True
    card_in(state, "T11", "capabilities_in_play")
    resolve(state)
    result = resolve(state, "russian")
    assert lord.state == "disbanded" and lord.location is None
    assert lord.lord_id in state.calendar.boxes[5 + 4 - 1].cylinders
    assert state.meta.phase == "levy" and state.meta.box == 5
    assert not state.meta.game_over and not result["game_over"]


def test_wastage_precedes_voluntary_capability_discard():
    state = end_campaign()
    lord = state.lords["hermann"]
    lord.assets = {"provender": 1}
    card_in(state, "T2", "this_lord_capabilities", lord.lord_id)
    card_in(state, "T5", "this_lord_capabilities", lord.lord_id)
    result = resolve(state, wastage={lord.lord_id: "provender"}, reset_discard=["T2"])
    assert {"lord_id": lord.lord_id, "discarded": "provender"} in result["wastage"]
    assert not lord.assets and lord.this_lord_capabilities == ["T5"]


def test_card_already_returned_by_wastage_is_not_duplicated_by_reset():
    state = end_campaign()
    lord = state.lords["hermann"]
    lord.assets = {}
    card_in(state, "T2", "this_lord_capabilities", lord.lord_id)
    card_in(state, "T5", "this_lord_capabilities", lord.lord_id)
    resolve(state, wastage={lord.lord_id: "capability:T2"}, reset_discard=["T2"])
    assert state.decks.teutonic.deck.count("T2") == 1
    assert lord.this_lord_capabilities == ["T5"]


@pytest.mark.parametrize("selected", [["T13", "R4"], ["T13", "T13"], ["T13", {}], "T13"])
def test_invalid_or_foreign_reset_selection_rolls_back(selected):
    state = end_campaign()
    card_in(state, "T13", "capabilities_in_play")
    card_in(state, "R4", "capabilities_in_play")
    before = state.model_dump_json()
    with pytest.raises(IllegalAction, match="bad_reset_discard"):
        resolve(state, reset_discard=selected)
    assert state.model_dump_json() == before


def test_final_box_skips_reset_and_its_capability_menu():
    state = end_campaign()
    state.meta.span_end_box = state.meta.box
    card_in(state, "T13", "capabilities_in_play")
    move = next(m for m in legal_moves(state, with_previews=False)
                if m["type"] == "end_campaign_resolve")
    assert "reset_discard" not in move.get("candidates", {})
    result = resolve(state, reset_discard=["T13"])
    assert not result["reset_discard"]
    assert "T13" in state.decks.teutonic.capabilities_in_play


def test_selected_mat_card_already_returned_by_serf_disband_is_not_duplicated():
    state = end_campaign()
    place(state, "gavrilo", {"serfs": 1})
    card_in(state, "R2", "this_lord_capabilities", "gavrilo")
    resolve(state)
    resolve(state, "russian", reset_discard=["R2"])
    assert state.decks.russian.deck.count("R2") == 1
    assert state.lords["gavrilo"].state == "disbanded"


def test_special_vassal_cleanup_preserves_lord_with_other_forces():
    state = end_campaign()
    lord = place(state, "andreas", {"knights": 3, "militia": 1})
    lord.vassals["andreas_summer_crusaders_1"].mustered = True
    card_in(state, "T11", "capabilities_in_play")
    resolve(state, reset_discard=["T11"])
    assert lord.state == "mustered" and lord.forces == {"militia": 1}


def test_capability_cascade_cannot_duplicate_a_later_selected_legate_card():
    state = end_campaign()
    lord = place(state, "andreas", {"knights": 3})
    lord.vassals["andreas_summer_crusaders_1"].mustered = True
    place(state, "gavrilo", {"militia": 1}).location = lord.location
    state.legate.william_of_modena_in_play = True
    state.legate.location = "locale"
    state.legate.locale_id = lord.location
    card_in(state, "T11", "capabilities_in_play")
    card_in(state, "T13", "capabilities_in_play")
    resolve(state, reset_discard=["T11", "T13"])
    assert state.decks.teutonic.deck.count("T13") == 1
    assert "T13" not in state.decks.teutonic.discard
    assert not state.legate.william_of_modena_in_play


@pytest.mark.parametrize("named", [False, True])
def test_capability_limit_recounts_lords_after_special_vassal_disband(named):
    state = end_campaign()
    for lord in state.lords.values():
        if lord.side == "teutonic":
            lord.state = "ready"
            lord.location = None
    lord = place(state, "andreas", {"knights": 3})
    lord.vassals["andreas_summer_crusaders_1"].mustered = True
    for cid in ["T1", "T12", "T11"]:
        card_in(state, cid, "capabilities_in_play")
    state.meta.phase = "levy"
    state.meta.levy_step = "call_to_arms"
    apply_action(state, {"type": "advance_step", "side": "teutonic", "args": {}})
    args = {"rule_4_0_discards": {"teutonic": ["T11", "T1", "T12"]}} if named else {}
    apply_action(state, {"type": "advance_step", "side": "russian", "args": args})
    if not named:
        apply_action(state, {"type": "discard_excess_capability", "side": "teutonic",
                             "args": {"card_id": "T11"}})
    assert lord.state == "disbanded"
    assert state.decks.teutonic.capabilities_in_play == []
    assert state.meta.game_over and state.meta.winner == "russian"


def test_crusade_discard_can_leave_another_choice_after_losing_a_lord():
    state = end_campaign()
    for lord in state.lords.values():
        if lord.side == "teutonic":
            lord.state = "ready"
            lord.location = None
    andreas = place(state, "andreas", {"knights": 3})
    andreas.vassals["andreas_summer_crusaders_1"].mustered = True
    place(state, "hermann", {"knights": 1})
    for cid in ("T1", "T12", "T11"):
        card_in(state, cid, "capabilities_in_play")
    state.meta.phase = "levy"
    state.meta.levy_step = "call_to_arms"
    for side in ("teutonic", "russian"):
        apply_action(state, {"type": "advance_step", "side": side, "args": {}})
    for card, expected_step in (("T11", "capability_discard"), ("T1", "plan")):
        apply_action(state, {"type": "discard_excess_capability", "side": "teutonic",
                             "args": {"card_id": card}})
        assert state.meta.campaign_step == expected_step
    assert andreas.state == "disbanded"
    assert state.decks.teutonic.capabilities_in_play == ["T12"]
