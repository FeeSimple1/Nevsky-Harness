"""SMOKE-100 (Round 120): Sail doesn't honor 1.7.2 voluntary asset
discard. Per rule 1.7.2 Greed, Lords MAY discard Loot and Provender
when Sailing (4.7.3 listed alongside March/Avoid/Retreat). Before
this fix the Sail handler had no discard arg, so a Lord with extra
assets and a Ship budget too tight could not voluntarily drop
assets to fit; Sail failed with insufficient_ships.

Boolean flags elect only necessary discards. Integer counts and per-Lord
choices must make the Sail possible and need every discarded Asset.
"""
from __future__ import annotations

import inspect

import pytest

import nevsky.actions  # noqa: F401
import nevsky.campaign as camp
from nevsky.actions import IllegalAction, _find_service_marker_box, apply_action
from nevsky.legal_moves import legal_moves
from nevsky.llm.session import LLMSession
from nevsky.scenarios import load_scenario
from tests.test_round12_lieutenant_movement import act, plan, plan_position
from tests.test_token_efficient_helper import attach, helper


def _setup_sail_state(prov, loot, ships):
    s = load_scenario("watland", seed=11)
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    teu = next(lid for lid, lord in s.lords.items()
               if lord.side == "teutonic" and lord.state == "mustered")
    s.lords[teu].location = "riga"
    s.lords[teu].forces.clear()
    s.lords[teu].forces["men_at_arms"] = 1  # foot only — no horse cost
    s.lords[teu].assets = {"provender": prov, "loot": loot, "ship": ships}
    s.meta.box = 1  # Summer
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "teutonic"
    s.campaign_turn.active_lord = teu
    # Sail is an entire-card Command (R203): requires a pristine full
    # Command card, so set the budget to the Lord's full command rating.
    s.campaign_turn.actions_remaining = camp._effective_command_rating(s, teu)
    s.campaign_turn.next_to_reveal = "teutonic"
    s.campaign_turn.in_feed_pay_disband = False
    return s, teu


def test_sail_discard_provender_lets_sail_succeed():
    # Prov=5, Loot=0, Ships=3 — need 5 ships for prov, have 3.
    # Discard 2 Provender → need 3, have 3 → SUCCEED.
    s, teu = _setup_sail_state(prov=5, loot=0, ships=3)
    apply_action(s, {
        "type": "cmd_sail", "side": "teutonic",
        "args": {"lord_id": teu, "destination": "reval", "group": [teu],
                 "discard_excess_provender": True},
    })
    assert s.lords[teu].location == "reval"
    assert s.lords[teu].assets["provender"] == 3


def test_sail_discard_loot_lets_sail_succeed():
    # Loot=2, Ships=3 — need 4 ships for loot, have 3.
    # Discard 1 Loot → need 2, have 3 → SUCCEED.
    s, teu = _setup_sail_state(prov=0, loot=2, ships=3)
    apply_action(s, {
        "type": "cmd_sail", "side": "teutonic",
        "args": {"lord_id": teu, "destination": "reval", "group": [teu],
                 "discard_excess_loot": True},
    })
    assert s.lords[teu].location == "reval"
    assert s.lords[teu].assets["loot"] == 1


def test_sail_without_discard_still_fails_when_insufficient():
    """Without discard arg, Sail still fails when ships are short."""
    s, teu = _setup_sail_state(prov=5, loot=0, ships=2)
    with pytest.raises(IllegalAction, match="insufficient_ships"):
        apply_action(s, {
            "type": "cmd_sail", "side": "teutonic",
            "args": {"lord_id": teu, "destination": "reval", "group": [teu]},
        })


def test_sail_handler_documents_smoke100():
    src = inspect.getsource(camp._h_cmd_sail)
    assert "SMOKE-100" in src
    assert "discard_excess_provender" in src
    assert "discard_excess_loot" in src


@pytest.mark.parametrize("ships", [3, 4])
def test_native_sail_retains_food_for_feed_after_session_load(ships, tmp_path):
    state = load_scenario("pleskau", seed=1)
    lid = "knud_and_abel"
    act(state, "system_setup_complete", "system")
    for _ in range(60):
        if state.meta.phase == "campaign":
            break
        moves = legal_moves(state, with_previews=False)
        if state.meta.levy_step == "arts_of_war":
            apply_action(state, moves[0])
        elif (state.meta.levy_step == "muster" and state.meta.active_player == "teutonic"
              and state.lords[lid].assets["ship"] < ships):
            act(state, "levy_transport", "teutonic", by_lord=lid, transport_type="ship")
        else:
            apply_action(state, next(m for m in moves if m["type"] == "advance_step"))
    assert state.meta.campaign_step == "plan"
    plan(state, teutonic=[lid] * 3 + ["hermann"] * 3)
    assert state.lords[lid].assets == {"coin": 1, "provender": 2, "ship": ships}
    service = _find_service_marker_box(state, lid)
    assert service == 3

    session = LLMSession(state, "teutonic", "pleskau")
    [move] = [m for m in session.legal_actions()
              if m["type"] == "cmd_sail" and m["args"]["destination"] == "riga"]
    assert move in legal_moves(state, with_previews=False)
    if ships == 3:
        assert type(move["args"]["discard_excess_provender"]) is int
        assert move["args"]["discard_excess_provender"] == 1
    else:
        assert "discard_excess_provender" not in move["args"]

    path = tmp_path / "sail.json"
    session.save(path)
    restored = LLMSession.load(path)
    assert restored.apply(move) == session.apply(move)
    assert restored.state.lords[lid].assets["provender"] == ships - 2
    feed = {"type": "fpd_resolve", "args": {"decline_pay": True}}
    assert restored.apply(feed) == session.apply(feed)
    assert _find_service_marker_box(restored.state, lid) == service
    assert restored.state.model_dump_json() == state.model_dump_json()


@pytest.mark.parametrize(("ships", "totals"), [
    (3, {(0, 1), (2, 0)}),
    (2, {(1, 1), (3, 0)}),
    (4, {(0, 1), (1, 0)}),
])
def test_sail_menu_offers_all_necessary_mixed_cargo_choices(ships, totals):
    state, lid = _setup_sail_state(prov=3, loot=1, ships=ships)
    choices = [m for m in legal_moves(state, with_previews=False)
               if m["type"] == "cmd_sail" and m["args"]["destination"] == "reval"]
    observed = set()
    for move in choices:
        args = move["args"]
        prov = args.get("discard_excess_provender", 0)
        loot = args.get("discard_excess_loot", 0)
        observed.add((prov, loot))
        restored = state.model_copy(deep=True)
        apply_action(restored, move)
        assert restored.lords[lid].assets.get("provender", 0) == 3 - prov
        assert restored.lords[lid].assets.get("loot", 0) == 1 - loot
    assert observed == totals


@pytest.mark.parametrize(("ships", "selection", "error"), [
    (5, {"discard_excess_provender": 1}, "unnecessary_discard"),
    (5, {"discard_excess_loot": 1}, "unnecessary_discard"),
    (4, {"discard_excess_loot": 1, "discard_excess_provender": 1}, "unnecessary_discard"),
    (3, {"discard_excess_provender": 1}, "insufficient_ships"),
    (3, {"discard_excess_provender": -1}, "bad_sail_discard"),
    (3, {"discard_excess_provender": 4}, "bad_sail_discard"),
    (3, {"discard_excess_loot": "1"}, "bad_sail_discard"),
])
def test_sail_rejects_unnecessary_or_invalid_discards_atomically(ships, selection, error):
    state, lid = _setup_sail_state(prov=3, loot=1, ships=ships)
    before = state.model_dump_json()
    with pytest.raises(IllegalAction, match=error):
        act(state, "cmd_sail", "teutonic", lord_id=lid, destination="reval", **selection)
    assert state.model_dump_json() == before


def test_legacy_flags_keep_all_cargo_when_it_fits():
    state, lid = _setup_sail_state(prov=3, loot=1, ships=5)
    act(state, "cmd_sail", "teutonic", lord_id=lid, destination="reval",
        discard_excess_provender=True, discard_excess_loot=True)
    assert state.lords[lid].assets == {"provender": 3, "loot": 1, "ship": 5}


def test_sail_action_id_allows_linked_lords_to_choose_discarding_mat(capsys):
    state = plan_position()
    leader, lower = "yaroslav", "knud_and_abel"
    state.lords[leader].location = "reval"
    state.lords[lower].assets["ship"] = 6
    act(state, "place_lieutenant", "teutonic", lieutenant=leader, lower_lord=lower)
    plan(state, teutonic=[leader] * 3 + ["hermann"] * 3)

    nv = helper()
    attach(nv, state)
    rows = nv.actions("cmd_sail", params={"destination": "riga"})["items"]
    [row] = rows
    assert row["action"]["args"]["group"] == [leader, lower]
    assert row["action"]["args"]["discard_excess_provender"] == 1
    assert "discard_by_lord" in capsys.readouterr().out

    before = state.model_dump_json()
    with pytest.raises(IllegalAction, match="bad_sail_discard"):
        nv.apply(row["id"], args={"discard_by_lord": {"hermann": {"provender": 1}}})
    assert state.model_dump_json() == before
    nv.apply(row["id"], args={"discard_by_lord": {lower: {"provender": 1}}})
    assert state.lords[leader].assets["provender"] == state.lords[lower].assets["provender"] == 1
    assert state.lords[leader].location == state.lords[lower].location == "riga"
