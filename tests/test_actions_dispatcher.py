"""Tests for the action dispatcher and step-transition machinery."""

from __future__ import annotations

import pytest

from nevsky.actions import IllegalAction, apply_action
from nevsky.scenarios import load_scenario


def test_dispatcher_rejects_unknown_action() -> None:
    s = load_scenario("watland", seed=42)
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "no_such_action", "side": "teutonic", "args": {}})
    assert exc.value.code == "unknown_action"


def test_dispatcher_appends_history_with_sequence() -> None:
    """BRIEF: every action records a HistoryEntry with sequence."""
    s = load_scenario("watland", seed=42)
    pre_seq = s.meta.sequence
    apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    assert s.meta.sequence == pre_seq + 1
    assert len(s.history) == 1
    assert s.history[-1].sequence == s.meta.sequence


def test_advance_step_transitions_t_then_r_then_next_step() -> None:
    """SoP 2.2.4: T-then-R within each step. Both must complete to advance."""
    s = load_scenario("watland", seed=42)
    assert s.meta.levy_step == "arts_of_war"
    assert s.meta.active_player == "teutonic"
    apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    assert s.meta.active_player == "russian"
    assert s.meta.levy_step == "arts_of_war"
    apply_action(s, {"type": "advance_step", "side": "russian", "args": {}})
    assert s.meta.levy_step == "pay"
    assert s.meta.active_player == "teutonic"


def test_advance_step_resets_lordship_at_muster() -> None:
    s = load_scenario("watland", seed=42)
    # Skip arts_of_war, pay, disband all the way to muster.
    for _ in range(3):
        apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})
        apply_action(s, {"type": "advance_step", "side": "russian", "args": {}})
    assert s.meta.levy_step == "muster"
    for l in s.lords.values():
        assert l.lordship_used == 0


def test_advance_step_resets_call_to_arms_flags() -> None:
    s = load_scenario("watland", seed=42)
    # Pre-set flags then advance into call_to_arms.
    s.legate.acted_this_call_to_arms = True
    s.veche.acted_this_call_to_arms = True
    for _ in range(4):
        apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})
        apply_action(s, {"type": "advance_step", "side": "russian", "args": {}})
    assert s.meta.levy_step == "call_to_arms"
    assert not s.legate.acted_this_call_to_arms
    assert not s.veche.acted_this_call_to_arms


def test_action_in_wrong_step_rejected() -> None:
    s = load_scenario("watland", seed=42)
    with pytest.raises(IllegalAction) as exc:
        # Pay during arts_of_war -> should fail.
        apply_action(s, {
            "type": "pay_with_coin", "side": "teutonic",
            "args": {"from": "lord:hermann", "target_lord": "hermann", "units": 1},
        })
    assert exc.value.code == "wrong_step"


def test_action_by_wrong_actor_rejected() -> None:
    s = load_scenario("watland", seed=42)
    # Russians try to act first.
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "advance_step", "side": "russian", "args": {}})
    assert exc.value.code == "wrong_actor"


def test_system_setup_complete_clears_transport_choices() -> None:
    s = load_scenario("watland", seed=42)
    pre = sum(1 for pd in s.pending_decisions if pd.kind == "setup_transport_choice")
    assert pre > 0
    apply_action(s, {"type": "system_setup_complete", "side": "system", "args": {}})
    assert all(pd.kind != "setup_transport_choice" for pd in s.pending_decisions)
