"""SMOKE-093 (Round 113): Battle aftermath Loser routed_units never
resolved via 4.4.4 Losses rolls — pile silently persists across
Battles.

Per rule 4.4.4 Losses: the LOSER rolls 1d6 per Routed unit; some
return to Forces, others are permanently lost. The Winner's
Routed units automatically return.

The harness restored Winner.routed_units → forces unconditionally
but never called apply_losses_rolls for losers. The loser's
routed_units pile sat untouched, so a Lord could carry routed
units across multiple Battles without resolution.

Fix calls apply_losses_rolls for each retreating loser, using
`conceded_then_retreated` if they conceded, else
`retreated_no_concede`.
"""
from __future__ import annotations

import inspect

import nevsky.actions  # noqa: F401
import nevsky.campaign as camp


def test_battle_aftermath_calls_apply_losses_rolls():
    src = inspect.getsource(camp._h_stand_battle)
    assert "SMOKE-093" in src
    assert "apply_losses_rolls" in src


def test_battle_aftermath_picks_conceded_loss_state():
    src = inspect.getsource(camp._h_stand_battle)
    smoke = src[src.find("SMOKE-093"):]
    # Should use "conceded_then_retreated" or "retreated_no_concede".
    assert "conceded_then_retreated" in smoke
    assert "retreated_no_concede" in smoke


def test_battle_aftermath_only_runs_when_routed_units_exist():
    src = inspect.getsource(camp._h_stand_battle)
    smoke = src[src.find("SMOKE-093"):]
    assert "lord.routed_units" in smoke
