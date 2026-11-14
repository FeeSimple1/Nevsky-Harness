"""Pope Gregory, contextual Holds, and snapshots of accepted actions."""

from copy import deepcopy

import pytest

from nevsky.actions import (
    IllegalAction,
    _find_cylinder_box,
    _remove_lord_permanently,
    apply_action,
)
from nevsky.llm.session import LLMSession
from nevsky.llm.tools import legal_actions_for_side
from nevsky.static_data import load_lords
from tests.test_round21_nevsky import _choose, _offered, _reject, _save_load


def _play_peipus(seed, checkpoint, *, muster=False, llm_side="teutonic"):
    session = LLMSession.start_new("peipus", llm_side=llm_side, seed=seed,
                                   confirm_transports=True)
    state = session.state
    priorities = (
        *(("muster_lord",) if muster else ()),
        "aow_draw", "aow_implement_card", "disband_resolve", "advance_step",
        "plan_add_card", "finalize_plan", "command_reveal", "fpd_resolve", "end_campaign_resolve",
    )
    for _ in range(160):
        if checkpoint(state):
            return session
        side = state.meta.active_player
        moves = legal_actions_for_side(state, side)
        action = next(move for kind in priorities for move in moves
                      if move["type"] == kind
                      and (kind != "muster_lord" or side == "teutonic")
                      and (kind != "plan_add_card" or move["args"]["card"] == "pass"))
        args = dict(action["args"])
        if action["type"] == "end_campaign_resolve":
            args["wastage"] = {lord: choices[0] for lord, choices in
                               action.get("candidates", {}).get("wastage", {}).items()}
        session.apply({"type": action["type"], "args": args},
                      who="llm" if side == llm_side else "human")
    pytest.fail("Peipus checkpoint was not reached")


def _pope_gregory_pending(state):
    return state.meta.first_levy_done and state.decks.teutonic.pending_draw[:1] == ["T11"]


def _replay_peipus(session):
    replay = LLMSession.start_new("peipus", llm_side=session.llm_side,
                                  seed=session.state.meta.seed, confirm_transports=True)
    for entry in session.history:
        replay.apply(entry["action"], who=entry["who"])
    assert replay.state.model_dump() == session.state.model_dump()
    assert replay.history == session.history


def test_pope_gregory_grants_crusade_without_a_cylinder(tmp_path):
    session = _save_load(_play_peipus(18, _pope_gregory_pending, muster=True), tmp_path)
    state = session.state
    deck = state.decks.teutonic
    assert deck.pending_draw == ["T11", "T18"]
    implement = [move for move in session.legal_actions() if move["type"] == "aow_implement_card"]
    assert [move["args"] for move in implement] == [{"card_id": "T11"}]
    assert "adds Crusade" in implement[0]["note"]
    calendar = state.calendar.model_dump()
    forces = {lid: dict(lord.forces) for lid, lord in state.lords.items()}

    result = session.apply(implement[0])

    assert result["outcome"] == "immediate_event_to_capability"
    assert result["effect"]["crusade_added"] and result["effect"]["shifted"] is None
    assert deck.capabilities_in_play.count("T11") == 1
    assert "T11" not in deck.discard
    assert deck.pending_draw == ["T18"]
    assert _offered(session, "aow_implement_card", card_id="T18")
    assert state.calendar.model_dump() == calendar
    assert all(lord.forces == forces[lid] for lid, lord in state.lords.items())
    _replay_peipus(_save_load(session, tmp_path))


def test_pope_gregory_still_requires_an_available_cylinder(tmp_path):
    session = _play_peipus(9, _pope_gregory_pending, muster=True)
    state = session.state
    before = _find_cylinder_box(state, "yaroslav")
    assert before == 16
    _reject(session, "aow_implement_card", "missing_arg", card_id="T11")
    _reject(session, "aow_implement_card", "missing_arg", card_id="T11", target="aleksandr")
    _reject(session, "aow_implement_card", "no_cylinder", card_id="T11", target="rudolf")

    result = _choose(session, "aow_implement_card", card_id="T11", target="yaroslav")

    assert result["effect"]["new_box"] == before - 1
    assert _find_cylinder_box(state, "yaroslav") == before - 1
    assert state.decks.teutonic.capabilities_in_play.count("T11") == 1
    assert "T11" not in state.decks.teutonic.discard
    _replay_peipus(_save_load(session, tmp_path))


def test_pope_gregory_crusaders_muster_and_follow_capability_limit():
    session = LLMSession.start_new("return_of_the_prince", llm_side="teutonic",
                                   seed=1, confirm_transports=True)
    state = session.state
    deck = state.decks.teutonic
    # Stage a later Summer Levy with Andreas as the only surviving Teutonic Lord.
    state.meta.first_levy_done = True
    state.meta.aow_drawn_t = state.meta.aow_drawn_r = True
    for lid, lord in state.lords.items():
        if lid != "andreas" and lord.side == "teutonic":
            _remove_lord_permanently(state, lid, load_lords()[lid])
    deck.deck.remove("T11")
    deck.pending_draw = ["T11"]
    deck.deck.remove("T12")
    deck.capabilities_in_play = ["T12"]
    andreas = state.lords["andreas"]
    knights = andreas.forces["knights"]
    crusaders = andreas.vassals["andreas_summer_crusaders_1"]

    _choose(session, "aow_implement_card", card_id="T11")
    for _ in range(6):
        _choose(session, "advance_step")
    assert state.meta.levy_step == "muster"
    assert crusaders.mustered and andreas.forces["knights"] == knights + 3
    assert andreas.lordship_used == 0

    for _ in range(4):
        _choose(session, "advance_step")
    assert state.meta.campaign_step == "capability_discard"
    _choose(session, "discard_excess_capability", card_id="T11")
    assert state.meta.campaign_step == "plan"
    assert deck.capabilities_in_play == ["T12"] and deck.discard.count("T11") == 1
    assert not crusaders.mustered and andreas.forces["knights"] == knights


def test_contextual_hold_cannot_unlock_its_capability(tmp_path):
    session = _play_peipus(1, lambda state: state.meta.box == 14
                           and state.meta.levy_step == "muster"
                           and state.meta.active_player == "russian", llm_side="russian")
    session = _save_load(session, tmp_path)
    state = session.state
    deck = state.decks.russian
    assert deck.holds == ["R8", "R5"] and state.combat_pending is None
    for card in deck.holds:
        assert not _offered(session, "aow_play_hold", card_id=card)
        _reject(session, "aow_play_hold", "wrong_hold_context", card_id=card)
    with pytest.raises(IllegalAction, match="^not_in_holds:"):
        session.apply({"type": "aow_play_hold", "args": {"card_id": "R5"}}, who="human")
    assert not _offered(session, "levy_capability", by_lord="andrey", card_id="R5")
    _reject(session, "levy_capability", "card_unavailable", by_lord="andrey", card_id="R5")

    _choose(session, "aow_lordship_plus_2", card_id="R8", lord_id="andrey", mode="lordship")
    assert state.meta.lordship_bonus["andrey"] == 2
    assert deck.holds == ["R5"] and deck.discard.count("R8") == 1
    _replay_peipus(_save_load(session, tmp_path))


@pytest.mark.parametrize("card", (
    "T4", "T5", "T6", "T7", "T8", "T9", "T10", "T17",
    "R1", "R2", "R4", "R5", "R6", "R8", "R13", "R_unknown",
))
def test_generic_hold_rejects_contextual_and_unknown_cards_atomically(card):
    side = "teutonic" if card.startswith("T") else "russian"
    session = LLMSession.start_new("watland", llm_side=side, seed=1)
    state = session.state
    deck = getattr(state.decks, side)
    if card in deck.deck:
        deck.deck.remove(card)
    deck.holds.append(card)
    args = {"card_id": card}
    action = {"type": "aow_play_hold", "side": side, "args": args}
    before = state.model_dump_json()
    for play in (session.apply, lambda move: apply_action(state, move)):
        with pytest.raises(IllegalAction, match="^wrong_hold_context:"):
            play(action)
        assert state.model_dump_json() == before
        assert session.history == []


def test_reusing_setup_transport_args_preserves_both_replay_histories(tmp_path):
    session = LLMSession.start_new("watland", llm_side="teutonic", seed=1)
    args = {"lord_id": "andreas", "slot_index": 0, "value": "cart"}
    action = {"type": "set_setup_transport", "args": args}
    expected = [deepcopy(args)]
    session.apply(action)
    args.update(slot_index=1, value="boat")
    expected.append(deepcopy(args))
    session.apply(action)
    args.clear()

    loaded = _save_load(session, tmp_path)
    engine_actions = [entry.action for entry in loaded.state.history]
    session_actions = [entry["action"] for entry in loaded.history]
    for actions in (engine_actions, session_actions):
        assert [item["args"] for item in actions] == expected
        replay = LLMSession.start_new("watland", llm_side="teutonic", seed=1)
        for item in actions:
            replay.apply(item)
        assert replay.state.model_dump() == loaded.state.model_dump()
        assert replay.history == loaded.history
