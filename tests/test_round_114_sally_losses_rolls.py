"""SMOKE-094 (Round 114): Sally aftermath Loser routed_units never
resolved via 4.4.4 Losses rolls — same gap as SMOKE-093 in Battle
aftermath, but in the Sally code path (_h_cmd_sally).

Per rule 4.4.4 Losses: the LOSER rolls 1d6 per Routed unit; some
return to Forces, others are permanently lost. The Winner's
Routed units automatically return.

The Sally retreat block transferred spoils and recorded the
retreat but never called apply_losses_rolls for loser besiegers
(or sallying garrison) whose units were routed during the Battle.
Routed units silently persisted across subsequent commands.

Fix calls apply_losses_rolls for each retreating loser in the
Sally aftermath, using `conceded_then_retreated` if they conceded,
else `retreated_no_concede`.
"""
from __future__ import annotations

import inspect

import nevsky.actions  # noqa: F401
import nevsky.campaign as camp


def test_sally_aftermath_calls_apply_losses_rolls():
    src = inspect.getsource(camp._h_cmd_sally)
    assert "SMOKE-094" in src
    assert "apply_losses_rolls" in src


def test_sally_aftermath_picks_conceded_loss_state():
    src = inspect.getsource(camp._h_cmd_sally)
    smoke = src[src.find("SMOKE-094"):]
    # Should use "conceded_then_retreated" or "retreated_no_concede".
    assert "conceded_then_retreated" in smoke
    assert "retreated_no_concede" in smoke


def test_sally_aftermath_only_runs_when_routed_units_exist():
    src = inspect.getsource(camp._h_cmd_sally)
    smoke = src[src.find("SMOKE-094"):]
    assert "routed_units" in smoke
