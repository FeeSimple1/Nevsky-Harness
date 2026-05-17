"""SMOKE-097 (Round 117): simple Sally where sallying side loses
and withdraws back into the Stronghold (4.5.3 RAID) — sallying
Lords with routed_units never got 4.4.4 Losses resolution.

`apply_losses_rolls` defines a `"withdrew"` loss_state (unmodified
Protection range — the most generous threshold) but had no caller
for this Sally path. Same dead-code-surfaces family as
SMOKE-093/094/095/096.

Fix: in the simple-Sally lost-side branch (right after siege ->
RAID 1), iterate attackers and call apply_losses_rolls(state,
alid, "withdrew") for any with non-empty routed_units, BEFORE the
SMOKE-007 zero-force removal sweep so successful rolls can save
the Lord.
"""
from __future__ import annotations

import inspect

import nevsky.actions  # noqa: F401
import nevsky.campaign as camp


def test_sally_withdrew_calls_apply_losses_rolls():
    src = inspect.getsource(camp)
    # Find the simple-Sally sally_outcome="withdrew" block specifically
    idx = src.find('aftermath["sally_outcome"] = "withdrew"')
    assert idx > 0
    block = src[idx:idx + 2000]
    assert "SMOKE-097" in block
    assert "apply_losses_rolls" in block


def test_sally_withdrew_uses_withdrew_loss_state():
    src = inspect.getsource(camp)
    idx = src.find("SMOKE-097")
    assert idx > 0
    block = src[idx:idx + 1000]
    assert '"withdrew"' in block


def test_sally_withdrew_runs_before_zero_force_sweep():
    """Order matters: rolls should run BEFORE the SMOKE-007 removal
    sweep, so a successful roll can restore forces and save the Lord
    from permanent removal."""
    src = inspect.getsource(camp)
    smoke097 = src.find("SMOKE-097")
    smoke007 = src.find("SMOKE-007", smoke097)
    assert smoke097 > 0 and smoke007 > smoke097
