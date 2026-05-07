"""CLI integration tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from nevsky.cli import app
from nevsky.state import GameState


runner = CliRunner()


def test_version_subcommand_runs() -> None:
    """version: smoke test (carried from Phase 0)."""
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "nevsky-harness" in result.output


def test_new_writes_valid_state(tmp_path: Path) -> None:
    """new <scenario> -o <path>: writes a JSON state file that parses
    back to a GameState."""
    out = tmp_path / "pleskau.json"
    result = runner.invoke(app, ["new", "pleskau", "-o", str(out), "--seed", "9"])
    assert result.exit_code == 0
    text = out.read_text(encoding="utf-8")
    s = GameState.model_validate_json(text)
    assert s.meta.scenario_id == "pleskau"
    assert s.meta.seed == 9


def test_new_quickstart_exits_two(tmp_path: Path) -> None:
    """new quickstart: rejected with exit code 2, no file written."""
    out = tmp_path / "qs.json"
    result = runner.invoke(app, ["new", "quickstart", "-o", str(out)])
    assert result.exit_code == 2
    assert not out.exists()


def test_state_summary(tmp_path: Path) -> None:
    """state <file> --mode summary prints scenario header."""
    p = tmp_path / "watland.json"
    runner.invoke(app, ["new", "watland", "-o", str(p)])
    result = runner.invoke(app, ["state", str(p), "--mode", "summary"])
    assert result.exit_code == 0
    assert "Watland" in result.output


def test_state_focus_lord(tmp_path: Path) -> None:
    """state --mode focus --focus lord:<id> prints the Lord mat."""
    p = tmp_path / "rotp.json"
    runner.invoke(app, ["new", "return_of_the_prince", "-o", str(p)])
    result = runner.invoke(app, ["state", str(p), "--mode", "focus", "--focus", "lord:aleksandr"])
    assert result.exit_code == 0
    assert "Aleksandr" in result.output


def test_state_focus_requires_focus_arg(tmp_path: Path) -> None:
    """state --mode focus without --focus exits 2."""
    p = tmp_path / "p.json"
    runner.invoke(app, ["new", "pleskau", "-o", str(p)])
    result = runner.invoke(app, ["state", str(p), "--mode", "focus"])
    assert result.exit_code == 2


def test_state_invalid_mode(tmp_path: Path) -> None:
    """state --mode foo exits 2."""
    p = tmp_path / "p.json"
    runner.invoke(app, ["new", "pleskau", "-o", str(p)])
    result = runner.invoke(app, ["state", str(p), "--mode", "foo"])
    assert result.exit_code == 2


def test_save_round_trip_bit_identical(tmp_path: Path) -> None:
    """save preserves bytes (BRIEF determinism)."""
    p = tmp_path / "p.json"
    p2 = tmp_path / "p-copy.json"
    runner.invoke(app, ["new", "peipus", "-o", str(p), "--seed", "5"])
    result = runner.invoke(app, ["save", str(p), "-o", str(p2)])
    assert result.exit_code == 0
    assert p.read_bytes() == p2.read_bytes()


def test_load_validates(tmp_path: Path) -> None:
    """load echoes a one-line summary on a valid state."""
    p = tmp_path / "p.json"
    runner.invoke(app, ["new", "pleskau", "-o", str(p)])
    result = runner.invoke(app, ["load", str(p)])
    assert result.exit_code == 0
    assert "scenario=pleskau" in result.output


def test_pending_lists_decisions(tmp_path: Path) -> None:
    """pending lists the setup_transport_choice items left over from
    scenario load."""
    p = tmp_path / "p.json"
    runner.invoke(app, ["new", "crusade_on_novgorod", "-o", str(p)])
    result = runner.invoke(app, ["pending", str(p)])
    assert result.exit_code == 0
    assert "setup_transport_choice" in result.output


def test_history_empty_at_setup(tmp_path: Path) -> None:
    """history on a fresh scenario state is empty."""
    p = tmp_path / "p.json"
    runner.invoke(app, ["new", "pleskau", "-o", str(p)])
    result = runner.invoke(app, ["history", str(p)])
    assert result.exit_code == 0
    assert "no history" in result.output


def test_legal_moves_returns_json(tmp_path: Path) -> None:
    """legal-moves emits a JSON list (Phase 2)."""
    p = tmp_path / "p.json"
    runner.invoke(app, ["new", "pleskau", "-o", str(p)])
    result = runner.invoke(app, ["legal-moves", str(p)])
    assert result.exit_code == 0
    import json
    moves = json.loads(result.stdout)
    assert isinstance(moves, list)
    # advance_step is always available
    assert any(m["type"] == "advance_step" for m in moves)


def test_do_rejects_invalid_action(tmp_path: Path) -> None:
    """do exits 2 on a malformed action (Phase 2)."""
    p = tmp_path / "p.json"
    af = tmp_path / "act.json"
    af.write_text("{}", encoding="utf-8")
    runner.invoke(app, ["new", "pleskau", "-o", str(p)])
    result = runner.invoke(app, ["do", str(p), str(af)])
    assert result.exit_code == 2
