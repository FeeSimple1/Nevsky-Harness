"""Bounded simulations must not masquerade as completed battle outcomes."""
from copy import deepcopy

import pytest

from nevsky import battle
from nevsky.previews import battle_preview
from nevsky.scenarios import load_scenario


def _battle_state():
    state = load_scenario("watland", seed=1)
    for lord_id in ("andreas", "aleksandr"):
        lord = state.lords[lord_id]
        lord.state = "mustered"
        lord.location = "pskov"
        lord.forces = {"men_at_arms": 1}
        lord.routed_units = {}
        lord.this_lord_capabilities = []
    return state


def test_bounded_preview_reports_all_unresolved_trials(monkeypatch):
    """4.4.2: surviving one Round is neither a win nor a completed Battle."""
    state = _battle_state()
    before = deepcopy(state)
    monkeypatch.setattr(battle, "roll_d6", lambda state: 1)
    preview = battle_preview(state, "teutonic", ["andreas"], ["aleksandr"],
                             trials=3, max_rounds=1)
    assert preview["successful_trials"] == preview["incomplete_trials"] == 3
    assert preview["completed_trials"] == 0
    assert preview["incomplete_rate"] == 1.0
    assert preview["attacker_winrate"] == preview["defender_winrate"] == 0.0
    assert state == before


def test_bounded_preview_winrates_use_completed_battles_only():
    """Completed winrates exclude still-undecided Rounds and expose their count."""
    preview = battle_preview(_battle_state(), "teutonic", ["andreas"], ["aleksandr"],
                             trials=32, max_rounds=1)
    assert 0 < preview["completed_trials"] < 32
    assert preview["completed_trials"] + preview["incomplete_trials"] == 32
    assert preview["successful_trials"] == 32
    assert preview["incomplete_rate"] == preview["incomplete_trials"] / 32
    assert preview["attacker_winrate"] + preview["defender_winrate"] == pytest.approx(1.0)


def test_unbounded_preview_reports_only_completed_trials():
    """Default full Battles retain completed-result aggregates and zero incompletes."""
    preview = battle_preview(_battle_state(), "teutonic", ["andreas"], ["aleksandr"], trials=8)
    assert preview["successful_trials"] == preview["completed_trials"] == 8
    assert preview["incomplete_trials"] == 0
    assert preview["incomplete_rate"] == 0.0
    assert preview["attacker_winrate"] + preview["defender_winrate"] == pytest.approx(1.0)
