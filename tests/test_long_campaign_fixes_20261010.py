"""Regressions for the October 10 full Crusade review.

Fixtures are actual saved positions, with only append-only history removed.
The two old logs retain all original actions; the corrected engine rejects
their illegal Muster interleaving. New full-replay coverage uses a legal log.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from nevsky.actions import IllegalAction, _lordship_budget, apply_action
from nevsky.held_actions import held_actions_for_side
from nevsky.legal_moves import legal_moves
from nevsky.llm.tools import legal_actions_for_side
from nevsky.scenarios import load_scenario, refresh_victory_markers
from nevsky.state import GameState

DATA = Path(__file__).parent / "data" / "crusade_20261010"
INDEX = json.loads((DATA / "index.json").read_text())
ROOT = Path(__file__).resolve().parents[1]


def position(name):
    return GameState.model_validate_json((DATA / INDEX[name]["file"]).read_text())


def envelope(move):
    return {k: move[k] for k in ("type", "side", "args")}


def offered(state, action):
    return any(envelope(m) == action for m in legal_moves(state, with_previews=False)
               if isinstance(m.get("args"), dict))


def script(name):
    spec = importlib.util.spec_from_file_location("longfix_" + name,
                                                 ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name", [n for n in INDEX if n != "T3_double_conquest"])
def test_original_missing_choices_are_now_offered_and_executable(name):
    state = position(name)
    for action in INDEX[name]["actions"]:
        before = state.model_dump_json()
        assert offered(state, action), (name, action)
        assert state.model_dump_json() == before, "Enumeration mutated the live state"
        apply_action(state, action)


def test_treachery_rejects_duplicate_conquest_without_consuming_card_or_score():
    state = position("T3_double_conquest")
    action = INDEX["T3_double_conquest"]["actions"][0]
    before = state.model_dump_json()
    assert not offered(state, action)
    with pytest.raises(IllegalAction, match="already_conquered"):
        apply_action(state, action)
    assert state.model_dump_json() == before


def test_treachery_clears_siege_and_synchronizes_calendar():
    state = position("hidden_hold_T3")
    action = INDEX["hidden_hold_T3"]["actions"][0]
    target = state.locales[action["args"]["target"]]
    assert target.teutonic_conquered == 0 and target.siege_markers == 1
    vp = state.calendar.teutonic_vp
    apply_action(state, action)
    assert target.teutonic_conquered == 1
    assert target.siege_markers == 0
    assert state.calendar.teutonic_vp == vp + 1
    assert [b.box for b in state.calendar.boxes if b.teutonic_victory_marker] == [int(vp + 1)]
    assert "T3" not in state.decks.teutonic.holds
    assert state.decks.teutonic.discard.count("T3") == 1


def test_treachery_respects_vp_cap():
    state = position("hidden_hold_T3")
    state.calendar.teutonic_vp = 17.0
    refresh_victory_markers(state)
    apply_action(state, INDEX["hidden_hold_T3"]["actions"][0])
    assert state.calendar.teutonic_vp == 17.5


@pytest.mark.parametrize("blocker", ["walls_plus_one", "teutonic_castle", "russian_castle"])
def test_treachery_still_obeys_existing_eligibility(blocker):
    state = position("hidden_hold_T3")
    action = INDEX["hidden_hold_T3"]["actions"][0]
    setattr(state.locales[action["args"]["target"]], blocker, True)
    assert not offered(state, action)
    before = state.model_dump_json()
    with pytest.raises(IllegalAction):
        apply_action(state, action)
    assert state.model_dump_json() == before


@pytest.mark.parametrize("side,name", [
    ("teutonic", "bonus_budget_hidden_teutonic"),
    ("russian", "bonus_budget_hidden_russian"),
])
def test_bonus_expenditure_stops_at_total_not_printed_rating(side, name):
    state = position(name)
    for action in INDEX[name]["actions"]:
        apply_action(state, action)
    lid = INDEX[name]["actions"][0]["args"]["lord_id"]
    assert state.lords[lid].lordship_used == _lordship_budget(state, lid)
    assert not any(m.get("args", {}).get("by_lord") == lid
                   for m in legal_moves(state, with_previews=False))
    with pytest.raises(IllegalAction, match="lordship_exhausted"):
        apply_action(state, {"type": "levy_transport", "side": side,
                             "args": {"by_lord": lid, "transport_type": "cart"}})


@pytest.mark.parametrize("new_arrival", [False, True])
@pytest.mark.parametrize("side,lid", [("russian", "gavrilo"), ("teutonic", "hermann")])
def test_extra_muster_exposes_only_its_recipient_and_can_be_spent(side, lid, new_arrival):
    state = position("extra_muster_hidden_veche_action")
    state.meta.active_player = side
    lord = state.lords[lid]
    lord.just_arrived_this_levy = new_arrival
    lord.assets["cart"] = 0
    if side == "russian":
        action = {"type": "veche_action", "side": side,
                  "args": {"option": "C", "target_lord": lid}}
    else:
        state.legate.william_of_modena_in_play = True
        state.legate.location = "locale"
        state.legate.locale_id = lord.location
        state.legate.acted_this_call_to_arms = False
        action = {"type": "legate_use", "side": side,
                  "args": {"sub_option": "2c", "target_lord": lid}}
    apply_action(state, action)
    menu = legal_moves(state, with_previews=False)
    actors = {m.get("args", m.get("args_template", {})).get("by_lord")
              for m in menu if m["type"] in {
                  "muster_lord", "muster_vassal", "levy_transport", "levy_capability",
              }}
    assert actors == {lid}
    spend = {"type": "levy_transport", "side": side,
             "args": {"by_lord": lid, "transport_type": "cart"}}
    for _ in range(_lordship_budget(state, lid)):
        assert offered(state, spend)
        apply_action(state, spend)
    assert not offered(state, spend)
    with pytest.raises(IllegalAction, match="lordship_exhausted"):
        apply_action(state, spend)


def test_new_arrival_cannot_use_ordinary_muster_or_ungranted_extra():
    state = position("extra_muster_hidden_veche_action")
    state.meta.levy_step = "muster"
    state.lords["gavrilo"].just_arrived_this_levy = True
    state.lords["gavrilo"].lordship_used = 0
    action = {"type": "levy_transport", "side": "russian",
              "args": {"by_lord": "gavrilo", "transport_type": "cart"}}
    assert not offered(state, action)
    with pytest.raises(IllegalAction, match="just_arrived"):
        apply_action(state, action)
    state.meta.levy_step = "call_to_arms"
    assert not offered(state, action)
    with pytest.raises(IllegalAction, match="wrong_step"):
        apply_action(state, action)


def test_pogost_interrupt_does_not_transfer_the_activation_or_expose_other_holds():
    state = position("hidden_hold_R3")
    state.meta.active_player = "teutonic"
    action = INDEX["hidden_hold_R3"]["actions"][0]
    before = state.model_dump_json()
    own = legal_actions_for_side(state, "russian")
    assert any(envelope(m) == action for m in own)
    assert all(m["side"] == "russian" and m["type"] == "aow_play_hold" for m in own)
    assert state.model_dump_json() == before
    assert all(m["side"] == "teutonic" for m in legal_actions_for_side(state, "teutonic"))
    turn_before = state.campaign_turn.model_dump()
    apply_action(state, action)
    assert state.meta.active_player == "teutonic"
    assert state.campaign_turn.model_dump() == turn_before
    assert state.lords[action["args"]["target"]].assets["provender"] == 4
    assert state.history[-1].actor == "russian"


@pytest.mark.parametrize("side", ["teutonic", "russian"])
def test_no_holds_are_offered_after_game_over(side):
    state = position("hidden_hold_R3")
    state.meta.game_over = True
    assert held_actions_for_side(state, side) == []
    assert legal_actions_for_side(state, side) == []
    assert legal_moves(state, with_previews=False) == []


def test_helper_logs_interrupt_as_its_actual_owner():
    helper = script("chatgpt_play_helper")
    state = position("hidden_hold_R3")
    state.meta.active_player = "teutonic"
    helper._S.update(state=state, scenario="crusade_on_novgorod", history=[], findings=[], turn=0)
    helper.apply(INDEX["hidden_hold_R3"]["actions"][0])
    assert helper._S["history"][-1]["side"] == "russian"
    assert state.meta.active_player == "teutonic"


def test_helper_does_not_label_an_empty_inactive_menu_a_stall():
    helper = script("chatgpt_play_helper")
    state = position("extra_muster_hidden_veche_action")
    state.decks.teutonic.holds = []
    helper._S.update(state=state, scenario="crusade_on_novgorod", history=[], findings=[], turn=0)
    assert helper.show("teutonic") == []
    assert not helper._S["findings"]


def test_helper_auto_stops_for_opponent_hold(monkeypatch):
    helper = script("chatgpt_play_helper")
    state = position("hidden_hold_R3")
    state.meta.active_player = "teutonic"
    helper._S.update(state=state, scenario="crusade_on_novgorod", history=[], findings=[], turn=0)
    forced = {"type": "fpd_resolve", "side": "teutonic", "args": {}}
    monkeypatch.setattr(helper, "_validated", lambda *a, **k: [forced])
    monkeypatch.setattr(helper, "show", lambda: None)
    before = state.model_dump_json()
    helper.auto(max_steps=1)
    assert state.model_dump_json() == before
    assert helper._S["turn"] == 0 and helper._S["history"] == []


@pytest.mark.parametrize("name,expected_count", [("first", 1322), ("reserve", 1685)])
def test_old_long_campaign_log_rejects_previously_allowed_muster_interleaving(name, expected_count):
    # The 20261011 audit found that action 18 returns to Hermann AFTER
    # Knud & Abel starts. Keep the original evidence, but never make an
    # invalid recorded game bypass the repaired rule. The legal, full
    # 1,742-action replacement replay is in test_seed_20261011_fixes.py.
    payload = json.loads((DATA / (name + "_replay.json")).read_text())
    assert len(payload["actions"]) == expected_count
    state = load_scenario(payload["scenario"], seed=payload["seed"])
    for action in payload["actions"][:17]:
        apply_action(state, action)
    before = state.model_dump_json()
    assert state.meta.muster_lord_order == ["hermann", "knud_and_abel"]
    with pytest.raises(IllegalAction, match="muster_finished"):
        apply_action(state, payload["actions"][17])
    assert state.model_dump_json() == before


@pytest.mark.parametrize("cid,side,lid,seat", [
    ("T7", "teutonic", "hermann", "dorpat"),
    ("T8", "teutonic", "rudolf", "wenden"),
    ("T17", "teutonic", "rudolf", "wenden"),
    ("R8", "russian", "gavrilo", "pskov"),
    ("R13", "russian", "vladislav", "neva"),
])
def test_each_lordship_hold_is_visible_at_exhausted_printed_budget(cid, side, lid, seat):
    from nevsky.actions import _place_lord_on_map

    state = load_scenario("crusade_on_novgorod", seed=20261010)
    for owner in ("teutonic", "russian"):
        apply_action(state, {"type": "confirm_all_setup_transports", "side": owner, "args": {}})
    if state.lords[lid].state != "mustered":
        _place_lord_on_map(state, lid, seat, state.meta.box)
    state.meta.active_player = side
    state.meta.levy_step = "muster"
    state.lords[lid].just_arrived_this_levy = False
    state.lords[lid].lordship_used = _lordship_budget(state, lid)
    deck = getattr(state.decks, side)
    deck.deck.remove(cid)
    deck.holds.append(cid)
    action = {"type": "aow_lordship_plus_2", "side": side,
              "args": {"card_id": cid, "lord_id": lid, "mode": "lordship"}}
    assert offered(state, action)
    apply_action(state, action)
    assert state.meta.lordship_bonus[lid] == 2
    assert state.lords[lid].lordship_used == _lordship_budget(state, lid) - 2


def test_curia_is_offered_with_two_distinct_surviving_recipients():
    from nevsky.actions import _place_lord_on_map

    state = load_scenario("crusade_on_novgorod", seed=20261010)
    _place_lord_on_map(state, "heinrich", "leal", state.meta.box)
    state.decks.teutonic.deck.remove("T13")
    state.decks.teutonic.holds.append("T13")
    action = {"type": "aow_play_hold", "side": "teutonic",
              "args": {"card_id": "T13", "recipients": ["hermann", "yaroslav"]}}
    assert offered(state, action)
    grants = {lid: state.lords[lid].assets.get("coin", 0) for lid in ("hermann", "yaroslav")}
    apply_action(state, action)
    assert state.lords["heinrich"].state == "disbanded"
    assert all(state.lords[lid].assets["coin"] == min(8, coins + 4)
               for lid, coins in grants.items())


@pytest.mark.parametrize("name", [
    "bonus_budget_hidden_teutonic", "bonus_budget_hidden_russian",
])
def test_completed_lordship_expires_with_bonus_on_campaign_entry(name):
    state = position(name)
    for action in INDEX[name]["actions"]:
        apply_action(state, action)
    lid = INDEX[name]["actions"][0]["args"]["lord_id"]
    assert state.meta.lordship_bonus[lid] == 2
    assert state.lords[lid].lordship_used == _lordship_budget(state, lid)
    # Isolate the real Call-to-Arms -> Campaign boundary after expenditure.
    state.meta.levy_step = "call_to_arms"
    state.meta.levy_step_completed_t = False
    state.meta.levy_step_completed_r = False
    state.meta.active_player = "teutonic"
    for side in ("teutonic", "russian"):
        apply_action(state, {"type": "advance_step", "side": side, "args": {}})
    assert state.meta.phase == "campaign"
    assert state.meta.lordship_bonus == {}
    assert all(lord.lordship_used == 0 for lord in state.lords.values())


@pytest.mark.parametrize("scenario,seed", [("watland", 371), ("pleskau", 163)])
def test_bonus_expiration_property_failure_seeds(scenario, seed):
    spec = importlib.util.spec_from_file_location(
        "longfix_property_helper", ROOT / "tests" / "test_property_advanced_invariants.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    state = module._run_self_play(scenario, seed=seed, max_steps=400)
    assert all(lord.lordship_used <= _lordship_budget(state, lid)
               for lid, lord in state.lords.items())
