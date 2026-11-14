"""Acquisition, Service expiry, and owner-routed Capability discard."""

import pytest

from nevsky.actions import IllegalAction, _t11_summer_auto_muster
from nevsky.campaign import _discard_side_capability
from nevsky.llm.session import LLMSession
from nevsky.llm.tools import legal_actions_for_side
from nevsky.state import GameState, move_vassal_marker


def _apply(session, kind, *, side=None, **args):
    side = side or session.state.meta.active_player
    who = "llm" if side == session.llm_side else "human"
    return session.apply({"type": kind, "args": args}, who=who)


def _offered(session, kind, **args):
    state = session.state
    return any(
        move["type"] == kind and all(move.get("args", {}).get(k) == v for k, v in args.items())
        for move in legal_actions_for_side(state, state.meta.active_player)
    )


def _choose(session, kind, **args):
    assert _offered(session, kind, **args)
    return _apply(session, kind, **args)


def _reject(session, code, kind, **args):
    before = session.state.model_dump_json(), list(session.history)
    with pytest.raises(IllegalAction) as rejected:
        _apply(session, kind, **args)
    assert rejected.value.code == code
    assert (session.state.model_dump_json(), session.history) == before


def _roundtrip(session, tmp_path):
    path = tmp_path / "checkpoint.json"
    session.save(path)
    loaded = LLMSession.load(path)
    assert loaded.state.model_dump_json() == session.state.model_dump_json()
    assert loaded.history == session.history
    return loaded


def _reach_muster(session):
    state = session.state
    for _ in range(32):
        if state.meta.levy_step == "muster":
            assert state.meta.active_player == "teutonic"
            return
        menu = legal_actions_for_side(state, state.meta.active_player)
        move = next(move for kind in ("aow_draw", "aow_implement_card",
                                      "disband_resolve", "advance_step")
                    for move in menu if move["type"] == kind)
        _apply(session, move["type"], **move["args"])
    pytest.fail("Muster did not start")


def _first_muster(scenario="return_of_the_prince", *, seed=1):
    session = LLMSession.start_new(scenario, llm_side="teutonic", seed=seed,
                                   confirm_transports=True)
    _reach_muster(session)
    return session


def _at_call_to_arms(session):
    _choose(session, "advance_step")
    _choose(session, "advance_step")
    assert session.state.meta.levy_step == "call_to_arms"


@pytest.mark.parametrize("seed", [1, 25])
def test_steppe_warriors_native_initial_or_ordinary_acquisition(seed, tmp_path):
    session = _first_muster(seed=seed)
    _choose(session, "advance_step")
    state = session.state
    if seed == 1:
        _reject(session, "vassal_gated", "muster_vassal", by_lord="aleksandr",
                vassal_id="aleksandr_mongols_1")
        _choose(session, "levy_capability", by_lord="aleksandr", card_id="R10")
    assert "R10" in state.decks.russian.capabilities_in_play
    saved = _roundtrip(session, tmp_path)
    for vid in ("aleksandr_mongols_1", "aleksandr_mongols_2"):
        assert _offered(session, "muster_vassal", by_lord="aleksandr", vassal_id=vid)
    result = _choose(session, "muster_vassal", by_lord="aleksandr", vassal_id="aleksandr_mongols_1")
    assert result == _choose(saved, "muster_vassal", by_lord="aleksandr",
                             vassal_id="aleksandr_mongols_1")
    assert state.lords["aleksandr"].forces["asiatic_horse"] == 2
    assert saved.state.model_dump() == state.model_dump()


@pytest.mark.parametrize("extra_muster", [False, True])
def test_steppe_warriors_through_veche(extra_muster):
    session = _first_muster()
    state = session.state
    if extra_muster:
        _at_call_to_arms(session)
        _choose(session, "advance_step")
        _choose(session, "veche_action", option="C", target_lord="aleksandr")
        _choose(session, "levy_capability", by_lord="aleksandr", card_id="R10")
        _choose(session, "muster_vassal", by_lord="aleksandr", vassal_id="aleksandr_mongols_1")
        assert state.lords["aleksandr"].forces["asiatic_horse"] == 2
    else:
        _choose(session, "advance_step")
        _choose(session, "levy_capability", by_lord="aleksandr", card_id="R10")
        _choose(session, "advance_step")
        _choose(session, "advance_step")
        _choose(session, "veche_action", option="B", target_lord="andrey", seat="novgorod")
        andrey = state.lords["andrey"]
        assert andrey.state == "mustered"
        assert andrey.vassals["andrey_kipchaqs_1"].ready
        assert not andrey.vassals["andrey_kipchaqs_1"].mustered


@pytest.mark.parametrize("seed", [1, 7])
def test_crusade_native_initial_or_ordinary_acquisition(seed, tmp_path):
    session = _first_muster(seed=seed)
    state = session.state
    andreas = state.lords["andreas"]
    if seed == 1:
        state.meta.optional_rules["advanced_vassal_service"] = True
        result = _choose(session, "levy_capability", by_lord="andreas", card_id="T11")
        assert result["crusade"][0]["added_forces"] == {"knights": 3}
        assert andreas.vassals["andreas_summer_crusaders_1"].calendar_box == 11
    assert andreas.forces["knights"] == 4
    assert andreas.lordship_used == (1 if seed == 1 else 0)
    assert andreas.vassals["andreas_summer_crusaders_1"].mustered
    _roundtrip(session, tmp_path)


def test_crusade_extra_muster_includes_lord_in_enemy_territory():
    session = _first_muster()
    state = session.state
    _choose(session, "levy_capability", by_lord="andreas", card_id="T13")
    state.lords["andreas"].location = "riga"
    rudolf = state.lords["rudolf"]
    # Stage Rudolf's army with a later Service marker in unoccupied enemy territory.
    state.calendar.boxes[8].cylinders.remove("rudolf")
    rudolf.state = "mustered"
    rudolf.location = "luga"
    rudolf.forces = {"knights": 1}
    state.calendar.boxes[10].service_markers.append("rudolf")
    _at_call_to_arms(session)
    _choose(session, "legate_arrives", bishopric="riga")
    _choose(session, "legate_use", sub_option="2c", target_lord="andreas")
    result = _choose(session, "levy_capability", by_lord="andreas", card_id="T11")
    assert {event["lord_id"] for event in result["crusade"]} == {"andreas", "rudolf"}
    assert state.lords["andreas"].lordship_used == 1
    assert rudolf.forces["knights"] == 3 and rudolf.lordship_used == 0


def test_crusade_automatically_musters_with_a_lord_who_arrives_later():
    session = _first_muster(seed=7)
    state = session.state
    andreas = state.lords["andreas"]
    for _ in range(3):
        result = _choose(session, "muster_lord", by_lord="andreas",
                         target_lord="rudolf", seat="wenden")
        if result["outcome"] == "mustered":
            break
    rudolf = state.lords["rudolf"]
    assert rudolf.state == "mustered"
    assert rudolf.forces["knights"] == 3 and rudolf.lordship_used == 0
    assert andreas.forces["knights"] == 4


def test_crusade_reacquisition_cannot_replace_knights_twice_in_one_levy():
    session = _first_muster()
    state = session.state
    _choose(session, "levy_capability", by_lord="andreas", card_id="T11")
    andreas = state.lords["andreas"]
    andreas.forces["knights"] = 2
    assert _t11_summer_auto_muster(state) == []
    _discard_side_capability(state, "teutonic", "T11")
    _choose(session, "levy_capability", by_lord="andreas", card_id="T11")
    assert andreas.forces.get("knights", 0) == 0
    assert not _offered(session, "muster_vassal", by_lord="andreas",
                        vassal_id="andreas_summer_crusaders_1")


def _expiry_checkpoint(side, position):
    session = LLMSession.start_new("watland", llm_side=side, seed=22, confirm_transports=True)
    state = session.state
    state.meta.levy_step = "disband"
    state.meta.active_player = side
    state.meta.levy_step_completed_t = side == "russian"
    state.meta.optional_rules["advanced_vassal_service"] = True
    if side == "teutonic":
        lord_id, vid = "knud_and_abel", "knud_and_abel_estonian_aux"
        lord = state.lords[lord_id]
        lord.location = "reval"
        lord.forces["light_horse"] = 1
        lord.forces["militia"] += 1
        state.decks.teutonic.deck.remove("T13")
        state.decks.teutonic.capabilities_in_play.append("T13")
        state.legate.reset_pawn(in_play=True)
    else:
        lord_id, vid = "domash", "domash_novgorod_1"
        state.lords[lord_id].forces["militia"] += 2
    vassal = state.lords[lord_id].vassals[vid]
    vassal.mustered = True
    move_vassal_marker(state.calendar, vid, vassal, position)
    return session, lord_id, vid


@pytest.mark.parametrize(("side", "position"), [
    ("teutonic", 0), ("russian", 3), ("teutonic", 4), ("russian", 4), ("russian", 5),
])
def test_vassal_only_expiry_through_ordinary_and_extra_muster(side, position, tmp_path):
    session, lid, vid = _expiry_checkpoint(side, position)
    if position <= 4:
        _reject(session, "must_disband", "advance_step")
        receipt = _choose(session, "disband_resolve")["vassal_advanced"]
        records = receipt["removed" if position < 4 else "to_mat_unready"]
        assert records[0]["vassal_id"] == vid and records[0]["from_box"] == position
    else:
        assert not _offered(session, "disband_resolve")
    session = _roundtrip(session, tmp_path)
    vassal = session.state.lords[lid].vassals[vid]
    _choose(session, "advance_step")
    _choose(session, "advance_step")
    assert session.state.meta.levy_step == "muster"
    expected = "vassal_unready" if position <= 4 else "already_mustered"
    _reject(session, expected, "muster_vassal", by_lord=lid, vassal_id=vid, side=side)
    _choose(session, "advance_step")
    if side == "teutonic":
        _choose(session, "advance_step")
        _choose(session, "legate_arrives", bishopric="reval")
        _choose(session, "legate_use", sub_option="2c", target_lord=lid)
    else:
        _choose(session, "advance_step")
        _choose(session, "veche_action", option="C", target_lord=lid)
    assert not _offered(session, "muster_vassal", by_lord=lid, vassal_id=vid)
    _reject(session, expected, "muster_vassal", by_lord=lid, vassal_id=vid)
    _choose(session, "advance_step")
    assert vassal.ready == (position >= 4)
    assert vassal.removed == (position < 4)
    assert vassal.mustered == (position > 4)
    assert vassal.unready_through_levy is None


@pytest.mark.parametrize("position", [3, 4])
def test_service_status_survives_lord_disband_and_later_remuster(position, tmp_path):
    session, lid, vid = _expiry_checkpoint("russian", position)
    state = session.state
    state.calendar.boxes[6].service_markers.remove(lid)
    state.calendar.boxes[3].service_markers.append(lid)
    result = _choose(session, "disband_resolve")
    assert result["disbanded"] == [{"lord_id": lid, "new_box": 8}]
    _choose(session, "advance_step")
    _at_call_to_arms(session)
    _choose(session, "advance_step")
    _choose(session, "advance_step")
    session = _roundtrip(session, tmp_path)
    state = session.state
    # Stage a subsequent Levy when the cylinder reaches the current box.
    state.meta.phase = "levy"
    state.meta.levy_step = "call_to_arms"
    state.meta.active_player = "russian"
    state.meta.levy_step_completed_t = True
    state.meta.box = 8
    state.calendar.boxes[3].has_levy_campaign_marker = False
    state.calendar.boxes[7].has_levy_campaign_marker = True
    state.veche.vp_markers = 2
    _choose(session, "veche_action", option="B", target_lord=lid, seat="novgorod")
    vassal = state.lords[lid].vassals[vid]
    assert vassal.ready == (position == 4)
    assert vassal.removed == (position == 3)


def test_campaign_expiry_blocks_the_ensuing_levy(tmp_path):
    session, lid, vid = _expiry_checkpoint("russian", 4)
    state = session.state
    state.meta.phase = "campaign"
    state.meta.campaign_step = "command"
    state.meta.levy_step = "done"
    state.campaign_turn.in_feed_pay_disband = True
    state.campaign_turn.fpd_completed_t = True
    receipt = _apply(session, "fpd_resolve", decline_pay=True)["vassal_advanced"]
    assert receipt["to_mat_unready"][0]["vassal_id"] == vid
    assert state.lords[lid].vassals[vid].unready_through_levy == 5
    assert state.meta.campaign_step == "end_campaign"
    _apply(session, "end_campaign_resolve")
    _apply(session, "end_campaign_resolve")
    assert state.meta.phase == "levy" and state.meta.box == 5
    session = _roundtrip(session, tmp_path)
    vassal = session.state.lords[lid].vassals[vid]
    _reach_muster(session)
    _at_call_to_arms(session)
    _choose(session, "advance_step")
    _choose(session, "veche_action", option="C", target_lord=lid)
    assert not vassal.ready
    _reject(session, "vassal_unready", "muster_vassal", by_lord=lid, vassal_id=vid)
    _choose(session, "advance_step")
    assert vassal.ready


def test_old_save_recovers_permanent_expiry_even_after_erroneous_remuster():
    session, lid, vid = _expiry_checkpoint("russian", 3)
    _choose(session, "disband_resolve")
    raw = session.state.model_dump()
    lord = raw["lords"][lid]
    vassal = lord["vassals"][vid]
    for field in ("removed", "unready_through_levy", "last_crusade_levy"):
        del vassal[field]
    vassal.update(ready=True, mustered=True, on_calendar=True, calendar_box=6)
    raw["calendar"]["boxes"][5]["vassal_service_markers"].append(vid)
    lord["forces"]["militia"] += 2
    restored = GameState.model_validate(raw)
    assert restored.lords[lid].vassals[vid].removed
    assert not restored.lords[lid].vassals[vid].ready
    assert restored.lords[lid].forces["militia"] == 1
    assert vid not in restored.calendar.boxes[5].vassal_service_markers


def test_hidden_mats_preserves_public_expiry_but_screens_returned_forces():
    session, lid, vid = _expiry_checkpoint("russian", 3)
    session.state.meta.optional_rules["hidden_mats"] = True
    _choose(session, "disband_resolve")
    own_expiry = session.full_state()["history"][-1]["result"]["vassal_advanced"]["removed"][0]
    assert own_expiry["returned_forces"] == {"militia": 2}
    opposing = LLMSession(state=session.state, llm_side="teutonic", scenario_id="watland")
    assert not opposing.full_state()["lords"][lid]["vassals"]
    opposing_result = opposing.full_state()["history"][-1]["result"]
    assert opposing_result["vassal_advanced"]["removed"] == [
        {"lord_id": lid, "vassal_id": vid, "from_box": 3},
    ]


def test_hidden_mats_screens_free_muster_from_opponents_advance_receipt():
    session = LLMSession.start_new("return_of_the_prince", llm_side="teutonic", seed=7,
                                   confirm_transports=True)
    session.state.meta.optional_rules["hidden_mats"] = True
    for _ in range(16):
        if session.state.meta.levy_step == "disband":
            break
        state = session.state
        menu = legal_actions_for_side(state, state.meta.active_player)
        move = next(m for kind in ("aow_draw", "aow_implement_card", "advance_step")
                    for m in menu if m["type"] == kind)
        _apply(session, move["type"], **move["args"])
    assert session.state.meta.levy_step == "disband"
    _choose(session, "advance_step")
    russian_receipt = _choose(session, "advance_step")
    assert not russian_receipt["crusade"]
    assert session.state.lords["andreas"].forces["knights"] == 4
    assert session.full_state()["history"][-1]["result"]["crusade"][0]["lord_id"] == "andreas"


@pytest.mark.parametrize("choice", [None, "T12", "T16"])
def test_peipus_public_discard_choices_roundtrip(choice, tmp_path):
    session = _first_muster("peipus")
    if choice is not None:
        _choose(session, "levy_capability", by_lord="hermann", card_id="T16")
        _choose(session, "levy_capability", by_lord="hermann", card_id="T8")
    _at_call_to_arms(session)
    _reject(session, "wrong_actor", "advance_step", rule_4_0_discards={"teutonic": ["T12"]})
    _choose(session, "advance_step")
    _reject(session, "wrong_actor", "advance_step", rule_4_0_discards={"teutonic": ["T16"]})
    _choose(session, "advance_step")
    state = session.state
    if choice is None:
        assert state.meta.campaign_step == "plan"
        assert state.decks.teutonic.capabilities_in_play == ["T12"]
    else:
        assert (state.meta.campaign_step, state.meta.active_player) == (
            "capability_discard", "teutonic",
        )
        assert state.decks.teutonic.capabilities_in_play == ["T12", "T16", "T8"]
        assert [m["args"]["card_id"] for m in session.legal_actions()] == ["T12", "T16", "T8"]
        assert session.legal_actions_for_human() == []
        _reject(session, "wrong_actor", "discard_excess_capability", side="russian", card_id=choice)
        _reject(session, "bad_capability_discard", "discard_excess_capability", card_id="T4")
        _reject(session, "bad_capability_discard", "discard_excess_capability", card_id=["T12"])
        _reject(session, "capability_discard_pending", "plan_add_card", card="pass")
        saved = _roundtrip(session, tmp_path)
        assert _choose(saved, "discard_excess_capability", card_id=choice) == _choose(
            session, "discard_excess_capability", card_id=choice)
        assert state.meta.campaign_step == "plan"
        assert state.decks.teutonic.discard.count(choice) == 1
        remaining = [card for card in ("T12", "T16", "T8") if card != choice]
        assert state.decks.teutonic.capabilities_in_play == remaining
        assert saved.state.model_dump() == state.model_dump()
    assert state.lords["hermann"].this_lord_capabilities == ["T4"]
