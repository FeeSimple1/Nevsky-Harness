"""Rejected actions preserve the authoritative board, RNG, and history."""

from __future__ import annotations

import pytest

from nevsky.actions import IllegalAction, apply_action
from nevsky.rng import roll_d6
from nevsky.scenarios import load_scenario
from nevsky.state import GameState


def _campaign_state() -> GameState:
    state = load_scenario("crusade_on_novgorod", seed=17)
    for side in ("teutonic", "russian"):
        apply_action(state, {
            "type": "confirm_all_setup_transports", "side": side, "args": {},
        })
    state.meta.phase = "campaign"
    state.meta.campaign_step = "command"
    state.meta.box = 1
    state.meta.active_player = "teutonic"
    lord = state.lords["andreas"]
    lord.state = "mustered"
    lord.location = "reval"
    lord.in_stronghold = False
    state.campaign_turn.active_lord = "andreas"
    state.campaign_turn.actions_remaining = 1
    state.campaign_turn.in_feed_pay_disband = False
    return state


def test_rejected_laden_march_restores_discarded_provender() -> None:
    """4.3.2: an unaffordable Laden March cannot discard its excess load."""
    state = _campaign_state()
    lord = state.lords["andreas"]
    lord.assets = {"cart": 1, "provender": 5}
    assets = lord.assets
    history = state.history
    first_entry = history[0]
    before = state.model_dump_json()
    action = {
        "type": "cmd_march", "side": "teutonic",
        "args": {"lord_id": "andreas", "to": "revala",
                 "way_type": "trackway", "discard_excess_provender": True},
    }

    with pytest.raises(IllegalAction) as error:
        apply_action(state, action)

    assert error.value.code == "insufficient_actions"
    assert state.model_dump_json() == before  # Includes RNG, sequence, and history.
    assert state.lords["andreas"] is lord
    assert lord.assets is assets
    assert assets == {"cart": 1, "provender": 5}
    assert state.history is history
    assert history[0] is first_entry

    # A corrected retry commits the discard and movement exactly once.
    state.campaign_turn.actions_remaining = 2
    result = apply_action(state, action)
    assert result["cost"] == 2
    assert state.lords["andreas"] is lord
    assert lord.location == "revala"
    assert lord.assets is assets
    assert assets == {"cart": 1, "provender": 2}
    assert len(history) == 3


def test_bad_wastage_restores_earlier_plow_and_reap() -> None:
    """4.9.3–4.9.4: invalid Wastage cannot leave transport flipped/halved."""
    state = _campaign_state()
    state.meta.campaign_step = "end_campaign"
    state.meta.box = 2
    lord = state.lords["andreas"]
    lord.assets = {"cart": 5, "provender": 2}
    assets = lord.assets
    before = state.model_dump_json()

    with pytest.raises(IllegalAction) as error:
        apply_action(state, {
            "type": "end_campaign_resolve", "side": "teutonic",
            "args": {"wastage": {"andreas": "ship"}},
        })

    assert error.value.code == "bad_wastage"
    assert state.model_dump_json() == before
    assert state.lords["andreas"] is lord
    assert lord.assets is assets
    assert assets == {"cart": 5, "provender": 2}

    apply_action(state, {
        "type": "end_campaign_resolve", "side": "teutonic",
        "args": {"wastage": {"andreas": "sled"}},
    })
    assert lord.assets == {"sled": 2, "provender": 2}


def test_rejection_restores_automatically_confirmed_setup_choices() -> None:
    """BRIEF atomicity includes setup changes made before handler validation."""
    state = load_scenario("watland", seed=17)
    pending = state.pending_decisions
    assert any(decision.kind == "setup_transport_choice" for decision in pending)
    before = state.model_dump_json()

    with pytest.raises(IllegalAction) as error:
        apply_action(state, {
            "type": "pay_with_coin", "side": "teutonic",
            "args": {"from": "lord:andreas", "target_lord": "andreas", "units": 1},
        })

    assert error.value.code == "wrong_step"
    assert state.model_dump_json() == before
    assert state.pending_decisions is pending


@pytest.mark.parametrize("unexpected", [False, True])
def test_late_failure_restores_rng_replaced_fields_and_history(monkeypatch, unexpected) -> None:
    """BRIEF: late rejection or engine failure cannot consume dice or a turn."""
    from nevsky.actions import _HANDLERS

    state = _campaign_state()
    meta = state.meta
    lords = state.lords
    lord = lords["andreas"]
    assets = lord.assets
    history = state.history
    first_entry = history[0]
    before = state.model_dump_json()
    fields_before = meta.model_fields_set.copy()
    next_roll = roll_d6(state.model_copy(deep=True))
    def callback(current):
        return roll_d6(current)

    observed_rolls = []

    def fail_after_mutation(current, side, args):
        observed_rolls.append(args["callback"](current))
        assets["provender"] = 0
        lord.assets = {"loot": 8}
        current.lords = {}
        meta.sequence += 1
        meta.winner = side
        current.meta = meta.model_copy()
        history.append(first_entry)
        current.history = []
        if unexpected:
            raise RuntimeError("injected late engine failure")
        raise IllegalAction("late_rejection", "injected late validation failure")

    monkeypatch.setitem(_HANDLERS, "test_late_failure", fail_after_mutation)
    action = {"type": "test_late_failure", "side": "teutonic",
              "args": {"callback": callback}}
    for _ in range(2):
        with pytest.raises(RuntimeError if unexpected else IllegalAction):
            apply_action(state, action)
        assert state.model_dump_json() == before
        assert state.meta is meta
        assert meta.model_fields_set == fields_before
        assert state.lords is lords
        assert state.lords["andreas"] is lord
        assert lord.assets is assets
        assert state.history is history
        assert history[0] is first_entry
        assert action["args"]["callback"] is callback
    assert observed_rolls == [next_roll, next_roll]
