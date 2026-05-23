"""In-process play helper for GPT-5.5 (or any ChatGPT) running this repo in
its own Python sandbox -- NO API key, NO network. ChatGPT IS the player:
it runs the harness here and decides each move itself.

Setup (paste once in ChatGPT's python tool after uploading/unzipping the repo):
    import sys
    sys.path.insert(0, "src"); sys.path.insert(0, "scripts")
    import chatgpt_play_helper as nv
    nv.start("crusade_on_novgorod", seed=1)

Then loop:
    nv.show()        # prints active side, briefing, and NUMBERED legal actions
    nv.apply(3)      # apply action #3 (or nv.apply({"type":...,"args":{...}}))
    nv.auto()        # auto-advance forced/boilerplate turns; stops at next real choice
    ...
    nv.findings_report()   # the bug triage queue (illegal/exception/stall/invariant)

Only dependency is pydantic (already in the sandbox). Goal: a different
model walks different trajectories and surfaces different engine bugs;
every anomaly is captured automatically.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import traceback
from collections import Counter, defaultdict
from pathlib import Path

if "src" not in sys.path:
    sys.path.insert(0, "src")

import nevsky.actions  # noqa: F401
from nevsky.actions import IllegalAction, apply_action
from nevsky.scenarios import SCENARIO_IDS, determine_scenario_winner, load_scenario
from nevsky.llm.briefing import briefing_for_side
from nevsky.llm.tools import safe_fallback_for_side

_spec = importlib.util.spec_from_file_location(
    "llm_sp", Path(__file__).resolve().parent / "llm_self_play.py")
_llm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_llm)
_concrete_actions = _llm._concrete_actions

_S = {"state": None, "scenario": None, "history": [], "findings": [], "turn": 0}


def _terminal() -> bool:
    s = _S["state"]
    return s.meta.phase == "campaign" and s.meta.campaign_step == "done"


def _coloc(s):
    by = defaultdict(set)
    for l in s.lords.values():
        if l.state == "mustered" and l.location is not None and not l.in_stronghold:
            by[l.location].add(l.side)
    bad = [loc for loc, sides in by.items() if len(sides) > 1]
    cp = s.combat_pending
    if cp is not None:
        bad = [loc for loc in bad if loc != cp.to_locale]
    return bad


def _check_invariants():
    s = _S["state"]
    out = []
    co = _coloc(s)
    if co:
        out.append(f"co_located_enemies:{co}")
    if s.calendar.teutonic_vp > 17.5 or s.calendar.russian_vp > 17.5:
        out.append("vp_over_cap")
    if s.calendar.teutonic_vp < 0 or s.calendar.russian_vp < 0:
        out.append("vp_negative")
    for v in out:
        _S["findings"].append({"kind": "invariant", "turn": _S["turn"], "violation": v,
                               "box": s.meta.box})
    return out


def start(scenario: str, seed: int = 1):
    if scenario not in SCENARIO_IDS:
        raise ValueError(f"unknown scenario {scenario!r}; choose from {sorted(SCENARIO_IDS)}")
    s = load_scenario(scenario, seed=seed)
    for sd in ("teutonic", "russian"):
        try:
            apply_action(s, {"type": "confirm_all_setup_transports", "side": sd, "args": {}})
        except Exception:
            pass
    _S.update(state=s, scenario=scenario, history=[], findings=[], turn=0)
    print(f"started {scenario} (seed={seed}). Call nv.show() to see the first decision.")
    return show()


def _active():
    return _S["state"].meta.active_player or "teutonic"


def show():
    """Print the active side's briefing + numbered legal actions. Returns
    the list of concrete actions (so you can also inspect programmatically)."""
    s = _S["state"]
    if _terminal():
        print("GAME OVER:", determine_scenario_winner(s))
        return []
    side = _active()
    acts = _concrete_actions(s, side)
    step = s.meta.campaign_step if s.meta.phase == "campaign" else s.meta.levy_step
    print(f"\n===== turn {_S['turn']} | {side.upper()} | {s.meta.phase}/{step} | box {s.meta.box} "
          f"| VP T{s.calendar.teutonic_vp:.1f}/R{s.calendar.russian_vp:.1f} =====")
    print(briefing_for_side(s, side))
    print(f"\nLEGAL ACTIONS ({len(acts)}):")
    for i, a in enumerate(acts):
        argp = json.dumps(a.get("args") or a.get("args_template") or {}, default=str)
        note = a.get("note", "")
        print(f"  [{i}] {a.get('type','?'):<22} {argp}" + (f"   // {note}" if note else ""))
    if not acts:
        _S["findings"].append({"kind": "no_legal_moves", "turn": _S["turn"],
                               "phase": s.meta.phase, "step": step, "side": side})
        print("!! no legal moves (stall) — recorded as a finding")
    return acts


def apply(choice):
    """Apply a move: an int index from the last show(), or a raw action dict.
    Runs invariant checks + captures any anomaly, then shows the next state."""
    s = _S["state"]
    side = _active()
    acts = _concrete_actions(s, side)
    if isinstance(choice, int):
        if not (0 <= choice < len(acts)):
            print(f"index {choice} out of range 0..{len(acts)-1}; applying safe fallback")
            action = safe_fallback_for_side(s, side)
        else:
            a = acts[choice]
            action = {k: v for k, v in a.items() if k in ("type", "side", "args")}
            if "args" not in action:
                action = safe_fallback_for_side(s, side)
    elif isinstance(choice, dict):
        action = {k: v for k, v in choice.items() if k in ("type", "side", "args")}
        action.setdefault("side", side)
    else:
        raise TypeError("choice must be an int index or an action dict")
    try:
        result = apply_action(s, action)
    except IllegalAction as e:
        _S["findings"].append({"kind": "illegal_concrete_action", "turn": _S["turn"],
                               "side": side, "action": action, "code": str(e.args[0])[:160]})
        print(f"!! ILLEGAL (recorded): {str(e.args[0])[:160]} — applying safe fallback")
        action = safe_fallback_for_side(s, side)
        result = apply_action(s, action)
    except Exception as e:
        _S["findings"].append({"kind": "exception", "turn": _S["turn"], "side": side,
                               "action": action, "etype": type(e).__name__,
                               "msg": str(e)[:200], "tb": traceback.format_exc()[-700:]})
        print(f"!! EXCEPTION (recorded): {type(e).__name__}: {e}")
        return
    _S["history"].append({"turn": _S["turn"], "side": side, "action": action})
    _S["turn"] += 1
    bad = _check_invariants()
    if bad:
        print("!! INVARIANT VIOLATION (recorded):", bad)
    print(f"applied: {action['type']} ({side})"
          + (f" -> {result.get('outcome')}" if isinstance(result, dict) and result.get('outcome') else ""))
    return show()


def auto(max_steps: int = 300):
    """Auto-apply purely forced turns (exactly one legal action) so you skip
    boilerplate (Pass cards, single-option steps, FPD/reveal). Stops and
    show()s at the first turn with a real choice (>=2 actions), or game end.
    Instrumentation runs throughout."""
    s = _S["state"]
    n = 0
    while n < max_steps and not _terminal():
        side = _active()
        acts = _concrete_actions(s, side)
        if len(acts) != 1:
            break
        a = acts[0]
        action = {k: v for k, v in a.items() if k in ("type", "side", "args")}
        if "args" not in action:
            action = safe_fallback_for_side(s, side)
        try:
            apply_action(s, action)
        except Exception as e:
            _S["findings"].append({"kind": "exception", "turn": _S["turn"], "side": side,
                                   "action": action, "etype": type(e).__name__,
                                   "msg": str(e)[:200], "tb": traceback.format_exc()[-700:]})
            print(f"!! EXCEPTION during auto (recorded): {type(e).__name__}: {e}")
            return
        _S["turn"] += 1
        n += 1
        if _check_invariants():
            print("!! INVARIANT VIOLATION during auto (recorded) at turn", _S["turn"])
    print(f"auto-advanced {n} forced turn(s).")
    return show()


def findings_report():
    notable = [f for f in _S["findings"]
               if f["kind"] in ("illegal_concrete_action", "exception",
                                "no_legal_moves", "invariant")]
    print(f"\n===== FINDINGS: {len(_S['findings'])} total, {len(notable)} notable =====")
    for f in notable:
        print("  ", json.dumps(f, default=str)[:240])
    if not notable:
        print("  (none — no engine anomalies on this trajectory)")
    return _S["findings"]


def save(path: str = "chatgpt_game.json"):
    s = _S["state"]
    Path(path).write_text(json.dumps({"scenario_id": _S["scenario"],
                                      "state_json": s.model_dump_json(),
                                      "history": _S["history"],
                                      "findings": _S["findings"]}, indent=2))
    print("saved ->", path)
