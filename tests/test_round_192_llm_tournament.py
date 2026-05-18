"""R192 tournament harness smoke test.

Doesn't validate strategic strength — just confirms the harness
loads, runs one game per pairing across one scenario, and produces
a coherent leaderboard. Catches regressions to the agent personas,
the play loop, or the leaderboard renderer.
"""
from __future__ import annotations
import importlib.util
from pathlib import Path

import pytest

import nevsky.actions  # noqa: F401

_TOURN = (Path(__file__).resolve().parent.parent
          / "scripts" / "llm_tournament.py")


@pytest.fixture(scope="module")
def tourn():
    spec = importlib.util.spec_from_file_location("tourn", _TOURN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_agents_dict_has_four_entries(tourn):
    assert set(tourn.AGENTS.keys()) == {
        "greedy", "strategic", "aggressive", "conservative"}


def test_play_one_game_terminates(tourn):
    """Single game on watland (cheaper than pleskau, deterministic)."""
    r = tourn.play_game("watland", "greedy", "strategic",
                        seed=1, max_steps=3000)
    assert r["terminal"] is True, (
        f"tournament play_game did not terminate: {r}"
    )
    assert r["winner"] in {"teutonic", "russian", "draw"}
    assert r["steps"] > 10  # at least sanity


def test_leaderboard_renders(tourn):
    games = [
        {"scenario": "watland", "teu_agent": "greedy",
         "rus_agent": "strategic", "winner": "teutonic",
         "vp_teutonic": 3.5, "vp_russian": 1.0,
         "steps": 100, "terminal": True, "seed": 1},
        {"scenario": "watland", "teu_agent": "strategic",
         "rus_agent": "greedy", "winner": "draw",
         "vp_teutonic": 1.0, "vp_russian": 1.0,
         "steps": 100, "terminal": True, "seed": 1},
    ]
    out = tourn.render_leaderboard(games)
    assert "Tournament Leaderboard" in out
    assert "greedy" in out and "strategic" in out


def test_short_tournament_runs(tourn):
    """Two agents × one scenario × both sides = 2 games. Smoke."""
    games = tourn.run_tournament(
        ["watland"], ["greedy", "strategic"],
        seed=1, max_steps=3000)
    assert len(games) == 2
    for g in games:
        assert g["terminal"] is True
        assert g["winner"] in {"teutonic", "russian", "draw"}
