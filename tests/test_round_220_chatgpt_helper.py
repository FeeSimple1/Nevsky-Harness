"""Round 220 — guard the ChatGPT in-sandbox play helper so it can't
bit-rot. It must start a game, auto-advance forced turns, expose a
numbered action list, apply a choice, and report findings."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load_helper():
    if "src" not in sys.path:
        sys.path.insert(0, "src")
    spec = importlib.util.spec_from_file_location(
        "chatgpt_play_helper", _SCRIPTS / "chatgpt_play_helper.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_helper_start_show_auto_apply_findings():
    nv = _load_helper()
    acts = nv.start("pleskau", seed=1)
    assert isinstance(acts, list) and len(acts) >= 1
    # play a handful of decisions via the helper API
    for _ in range(6):
        acts = nv.auto(max_steps=400)
        if not acts:  # terminal
            break
        nv.apply(0)
    findings = nv.findings_report()
    # No engine anomalies expected on this clean trajectory.
    notable = [f for f in findings
               if f["kind"] in ("illegal_concrete_action", "exception",
                                "no_legal_moves", "invariant")]
    assert notable == [], f"helper surfaced engine anomalies: {notable}"


def test_helper_apply_accepts_raw_action_dict():
    nv = _load_helper()
    nv.start("watland", seed=1)
    nv.auto(max_steps=50)
    # raw-dict apply path (the JSON escape hatch) must not crash
    nv.apply({"type": "advance_step", "side": nv._active(), "args": {}})
