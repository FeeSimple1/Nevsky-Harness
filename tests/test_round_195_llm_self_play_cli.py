"""R195 — smoke test for scripts/llm_self_play.py CLI driver.

The script is the primary tool for LLM-vs-LLM self-play in Cowork
mode. Smoke-test: start, status, briefing, actions, apply (by
index and JSON), history, terminal — confirm they all produce
coherent output and don't regress with state-file corruption.
"""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = (Path(__file__).resolve().parent.parent
           / "scripts" / "llm_self_play.py")


def _run(state_path: Path, *args, expect_exit: int = 0) -> str:
    env = {"PYTHONPATH": "src"}
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), "--state", str(state_path), *args],
        capture_output=True, text=True,
        cwd=str(_SCRIPT.parent.parent),
        env={**__import__("os").environ, **env},
    )
    assert proc.returncode == expect_exit, (
        f"command {args} returned {proc.returncode}; "
        f"stderr:\n{proc.stderr}\nstdout:\n{proc.stdout}"
    )
    return proc.stdout


def test_start_and_status(tmp_path):
    sf = tmp_path / "g.json"
    out = _run(sf, "start", "pleskau", "--seed", "1")
    assert "started pleskau" in out
    assert "scenario:" in out
    assert sf.exists()
    payload = json.loads(sf.read_text())
    assert payload["scenario_id"] == "pleskau"
    assert payload["history"] == []


def test_briefing_actions_apply_by_index(tmp_path):
    sf = tmp_path / "g.json"
    _run(sf, "start", "watland", "--seed", "1")
    briefing = _run(sf, "briefing")
    assert "TEUTONIC" in briefing or "RUSSIAN" in briefing
    assert "Phase" in briefing
    actions_out = _run(sf, "actions")
    assert "legal action" in actions_out
    # advance_step is always present in Arts-of-War. Pick it.
    # Just pick index 0 — any legal move advances state.
    out = _run(sf, "apply", "0")
    assert "applied:" in out
    history_out = _run(sf, "history", "-n", "5")
    assert "1" in history_out


def test_apply_json_action(tmp_path):
    sf = tmp_path / "g.json"
    _run(sf, "start", "pleskau", "--seed", "1")
    out = _run(sf, "apply", '{"type":"advance_step","args":{}}')
    assert "applied:" in out and "advance_step" in out


def test_terminal_command_returns_json(tmp_path):
    sf = tmp_path / "g.json"
    _run(sf, "start", "pleskau", "--seed", "1")
    out = _run(sf, "terminal").strip()
    data = json.loads(out)
    assert data["terminal"] is False
    assert data["active_side"] in ("teutonic", "russian")


def test_state_persists_across_invocations(tmp_path):
    sf = tmp_path / "g.json"
    _run(sf, "start", "watland", "--seed", "1")
    _run(sf, "apply", "0")
    _run(sf, "apply", "0")
    history_out = _run(sf, "history", "-n", "10")
    # Two moves recorded.
    assert "[  1]" in history_out
    assert "[  2]" in history_out


def test_bad_action_index_errors_cleanly(tmp_path):
    sf = tmp_path / "g.json"
    _run(sf, "start", "pleskau", "--seed", "1")
    # Index 999 should not exist.
    out = subprocess.run(
        [sys.executable, str(_SCRIPT), "--state", str(sf), "apply", "999"],
        capture_output=True, text=True,
        cwd=str(_SCRIPT.parent.parent),
        env={**__import__("os").environ, "PYTHONPATH": "src"},
    )
    assert out.returncode != 0
    assert "out of range" in out.stderr or "out of range" in out.stdout
