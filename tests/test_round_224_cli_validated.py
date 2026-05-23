"""Round 224 — CLI `actions`/`apply` use the validated palette by default.

Eric's reliability note: chatgpt_play_helper validates the menu, but the
raw `llm_self_play.py` CLI printed `_concrete_actions` unfiltered, so an
index-driven caller could be offered a handler-rejected move. R224 routes
both `actions` and `apply` through `concrete_actions_validated()` by
default (index-consistent), with `--raw` to opt out.
"""
from __future__ import annotations
import importlib.util
import io
import json
import os
import subprocess
import sys
import types
from contextlib import redirect_stdout
from pathlib import Path

import pytest

import nevsky.actions  # noqa: F401
from nevsky.scenarios import load_scenario

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "llm_self_play.py"


def _load():
    spec = importlib.util.spec_from_file_location("llm_sp_224", _SCRIPT)
    m = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(_SCRIPT.parent))
    spec.loader.exec_module(m)
    return m


def test_cli_palette_validated_filters_illegal(monkeypatch):
    llm = _load()
    s = load_scenario("watland", seed=1)
    side = llm.active_side(s)
    legal = {"type": "advance_step", "side": side, "args": {}}
    illegal = {"type": "cmd_march", "side": side,
               "args": {"lord_id": "nobody", "to": "nowhere"}}
    monkeypatch.setattr(llm, "_concrete_actions", lambda st, sd: [legal, illegal])
    raw_pal, raw_rej = llm._cli_palette(s, side, raw=True)
    val_pal, val_rej = llm._cli_palette(s, side, raw=False)
    assert len(raw_pal) == 2 and raw_rej == []
    assert legal in val_pal
    assert all(a["type"] != "cmd_march" for a in val_pal), "illegal march must be filtered"
    assert len(val_rej) == 1 and val_rej[0]["action"]["type"] == "cmd_march"


def test_cmd_actions_prints_validated_tag_and_footer(monkeypatch):
    llm = _load()
    s = load_scenario("watland", seed=1)
    side = llm.active_side(s)
    legal = {"type": "advance_step", "side": side, "args": {}}
    illegal = {"type": "cmd_march", "side": side,
               "args": {"lord_id": "nobody", "to": "nowhere"}}
    monkeypatch.setattr(llm, "_concrete_actions", lambda st, sd: [legal, illegal])
    monkeypatch.setattr(llm, "load_state", lambda p: (s, "watland", []))
    args = types.SimpleNamespace(state="ignored", raw=False)
    buf = io.StringIO()
    with redirect_stdout(buf):
        llm.cmd_actions(args)
    out = buf.getvalue()
    assert "[validated]" in out
    assert "1 legal action" in out  # only advance_step survives
    assert "filtered 1 over-enumerated" in out
    assert "cmd_march" in out  # named in the REJECT diagnostic


def _run(state_path, *a, expect_exit=0):
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), "--state", str(state_path), *a],
        capture_output=True, text=True, cwd=str(_SCRIPT.parent.parent),
        env={**os.environ, "PYTHONPATH": "src"})
    assert proc.returncode == expect_exit, proc.stderr + proc.stdout
    return proc.stdout


def test_cli_default_validated_raw_flag_and_index_apply(tmp_path):
    sf = tmp_path / "g.json"
    _run(sf, "start", "watland", "--seed", "1")
    assert "[validated]" in _run(sf, "actions")
    assert "[raw]" in _run(sf, "actions", "--raw")
    # index apply still works against the validated default palette
    out = _run(sf, "apply", "0")
    assert "applied:" in out
