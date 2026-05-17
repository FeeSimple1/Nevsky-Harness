"""SMOKE-096 (Round 116): failed-Storm attackers' routed_units
never resolved via 4.4.4 Losses rolls.

`apply_losses_rolls` in battle.py defines an explicit
"storm_attacker" loss_state (keep on roll==1) but `_h_cmd_storm`
never called it. After a failed Storm the siege continues — but
attackers carrying routed units from the Storm rounds left them
unresolved, contradicting 4.4.4 Losses and matching the pattern
of SMOKE-093 (Battle) and SMOKE-094 (Sally).

Fix: in the storm_failed branch, call apply_losses_rolls(state,
alid, "storm_attacker") for each attacker with routed_units.
"""
from __future__ import annotations

import inspect

import nevsky.actions  # noqa: F401
import nevsky.campaign as camp


def test_storm_failed_calls_apply_losses_rolls():
    src = inspect.getsource(camp._h_cmd_storm)
    assert "SMOKE-096" in src
    assert "apply_losses_rolls" in src


def test_storm_failed_uses_storm_attacker_loss_state():
    src = inspect.getsource(camp._h_cmd_storm)
    smoke = src[src.find("SMOKE-096"):]
    assert "storm_attacker" in smoke


def test_storm_failed_only_runs_when_routed_units_exist():
    src = inspect.getsource(camp._h_cmd_storm)
    smoke = src[src.find("SMOKE-096"):]
    assert "routed_units" in smoke
