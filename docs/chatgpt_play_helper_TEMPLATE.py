"""ChatGPT-in-sandbox play helper — GENERIC TEMPLATE for L&C rules engines.

Goal: let ChatGPT (GPT-5.x, etc.) play YOUR harness in its own Python
sandbox and surface bugs — no API key, no network. ChatGPT IS the player;
this file just exposes start/show/apply/auto/findings and bakes in the
bug instrumentation (validated action palette + invariants + anomaly log).

HOW TO USE
  1. Copy this file into your repo (e.g. scripts/chatgpt_play_helper.py).
  2. Fill in the ADAPTER block below (~6 small functions) for your engine.
  3. Zip the repo, upload to a ChatGPT Project, paste the project
     instructions from CHATGPT_PLAY_PORTING_GUIDE.md, and play.

Everything OUTSIDE the ADAPTER block is engine-agnostic — leave it alone.
See CHATGPT_PLAY_PORTING_GUIDE.md for the full contract and rationale.
"""
from __future__ import annotations

import json
import sys
import traceback
from collections import defaultdict

# ===================== ADAPTER — edit for your engine =====================
sys.path.insert(0, "src")  # adjust if your package is not under src/

from yourengine.scenarios import load_scenario, SCENARIO_IDS          # noqa: E402,F401
from yourengine.actions import apply_action                          # noqa: E402  mutates state IN PLACE
from yourengine.errors import IllegalAction                          # noqa: E402  raised on an illegal action
from yourengine.briefing import briefing_for_side                    # noqa: E402  (state, side) -> str
from yourengine.legal import legal_actions_for_side                  # noqa: E402  (state, side) -> list[dict]

# Exception type(s) that mean "this action was illegal" (NOT a crash).
ILLEGAL_EXCEPTIONS = (IllegalAction,)

# Each legal action is a dict shaped like {"type": str, "args": dict, ...}.
# legal_actions_for_side MUST return CONCRETE, hidden-info-filtered actions
# for `side` (expand any templated/parameterized moves inside your adapter).
# apply_action(state, {"type":..., "side":..., "args":...}) applies in place.

def active_side(state):
    """Whose turn is it?"""
    return state.meta.active_player

def is_terminal(state):
    """Is the game over?"""
    raise NotImplementedError("return a bool: game finished?")

def determine_winner(state):
    """Optional: return a winner/result object, or None."""
    return None

def deep_copy(state):
    """Return an INDEPENDENT copy whose mutation cannot affect `state`.
    CRITICAL: this must fully isolate the RNG (see guide §RNG). If your RNG
    lives in the state (seed + counter), a structural deep copy works:
        return state.model_copy(deep=True)        # pydantic v2
        # or: import copy; return copy.deepcopy(state)
    If your RNG is a MODULE GLOBAL, deep copy will NOT isolate it — set
    VALIDATE = False below and rely on apply-time catching instead."""
    return state.model_copy(deep=True)

def setup_actions(state):
    """Actions to auto-apply right after load (e.g. confirming setup
    choices). Return [] if your engine needs none."""
    return []

def invariants(state):
    """Return a list of human-readable violation strings ([] = OK). These
    run after EVERY applied action. Customize for your edition. The
    canonical L&C one is the co-location check; a reference implementation
    is in CHATGPT_PLAY_PORTING_GUIDE.md §Invariants — paste & adapt it."""
    return []

VALIDATE = True  # validated palette on (requires deep_copy to isolate RNG)
# =========================== END ADAPTER ===========================


_S = {"state": None, "scenario": None, "history": [], "findings": [], "turn": 0}


def _concrete(side):
    acts = legal_actions_for_side(_S["state"], side)
    return [a for a in acts if isinstance(a, dict)]


def _validated(side, log_rejects=True):
    """Validated, LLM-safe menu: probe each candidate on a deep copy and
    keep only those the handler accepts; log filtered ones as
    over-enumeration diagnostics (the root enumerator bug to fix)."""
    cands = _concrete(side)
    if not VALIDATE:
        return cands
    out = []
    for a in cands:
        if not isinstance(a.get("args"), dict):
            out.append({**a, "_unvalidated": True})
            continue
        minimal = {k: v for k, v in a.items() if k in ("type", "side", "args")}
        minimal.setdefault("side", side)
        probe = deep_copy(_S["state"])
        try:
            apply_action(probe, minimal)
            out.append(a)
        except ILLEGAL_EXCEPTIONS as e:
            if log_rejects:
                _S["findings"].append({"kind": "over_enum_filtered", "turn": _S["turn"],
                                       "side": side, "action": minimal, "code": str(e)[:160]})
        except Exception as e:
            if log_rejects:
                _S["findings"].append({"kind": "exception_in_probe", "turn": _S["turn"],
                                       "side": side, "action": minimal,
                                       "etype": type(e).__name__, "msg": str(e)[:200]})
    return out


def _check_invariants():
    bad = []
    try:
        bad = invariants(_S["state"]) or []
    except Exception as e:
        _S["findings"].append({"kind": "invariant_crash", "turn": _S["turn"],
                               "error": f"{type(e).__name__}: {e}"[:200]})
    for v in bad:
        _S["findings"].append({"kind": "invariant", "turn": _S["turn"], "violation": v})
    return bad


def start(scenario, seed=1):
    if scenario not in SCENARIO_IDS:
        raise ValueError(f"unknown scenario {scenario!r}; choose from {sorted(SCENARIO_IDS)}")
    s = load_scenario(scenario, seed=seed)
    for a in setup_actions(s):
        try:
            apply_action(s, a)
        except Exception:
            pass
    _S.update(state=s, scenario=scenario, history=[], findings=[], turn=0)
    print(f"started {scenario} (seed={seed}). Call nv.show().")
    return show()


def show():
    s = _S["state"]
    if is_terminal(s):
        print("GAME OVER:", determine_winner(s))
        return []
    side = active_side(s)
    acts = _validated(side)
    print(f"\n===== turn {_S['turn']} | active: {side} =====")
    print(briefing_for_side(s, side))
    print(f"\nLEGAL ACTIONS ({len(acts)}):")
    for i, a in enumerate(acts):
        print(f"  [{i}] {a.get('type','?')}  {json.dumps(a.get('args') or {}, default=str)}"
              + (f"   // {a['note']}" if a.get("note") else ""))
    if not acts:
        _S["findings"].append({"kind": "no_legal_moves", "turn": _S["turn"], "side": side})
        print("!! no legal moves (stall) — recorded")
    return acts


def apply(choice):
    s = _S["state"]
    side = active_side(s)
    acts = _validated(side, log_rejects=False)
    if isinstance(choice, int):
        if not (0 <= choice < len(acts)):
            print(f"index {choice} out of range; pass a valid index or an action dict")
            return show()
        a = acts[choice]
        action = {k: v for k, v in a.items() if k in ("type", "side", "args")}
    elif isinstance(choice, dict):
        action = {k: v for k, v in choice.items() if k in ("type", "side", "args")}
    else:
        raise TypeError("choice must be an int index or an action dict")
    action.setdefault("side", side)
    try:
        result = apply_action(s, action)
    except ILLEGAL_EXCEPTIONS as e:
        _S["findings"].append({"kind": "illegal_action", "turn": _S["turn"],
                               "side": side, "action": action, "code": str(e)[:160]})
        print(f"!! ILLEGAL (recorded): {str(e)[:160]}")
        return show()
    except Exception as e:
        _S["findings"].append({"kind": "exception", "turn": _S["turn"], "side": side,
                               "action": action, "etype": type(e).__name__,
                               "msg": str(e)[:200], "tb": traceback.format_exc()[-700:]})
        print(f"!! EXCEPTION (recorded): {type(e).__name__}: {e}")
        return
    _S["history"].append({"turn": _S["turn"], "side": side, "action": action})
    _S["turn"] += 1
    if _check_invariants():
        print("!! INVARIANT VIOLATION (recorded)")
    print(f"applied: {action['type']} ({side})")
    return show()


def auto(max_steps=300):
    """Auto-apply purely-forced turns (exactly one legal action) so you
    skip boilerplate; stop at the next real choice or game end."""
    s = _S["state"]
    n = 0
    while n < max_steps and not is_terminal(s):
        side = active_side(s)
        acts = _validated(side)
        if len(acts) != 1:
            break
        a = acts[0]
        action = {k: v for k, v in a.items() if k in ("type", "side", "args")}
        action.setdefault("side", side)
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
        _check_invariants()
    print(f"auto-advanced {n} forced turn(s).")
    return show()


def findings_report():
    notable = [f for f in _S["findings"] if f["kind"] in (
        "illegal_action", "over_enum_filtered", "exception", "exception_in_probe",
        "no_legal_moves", "invariant", "invariant_crash")]
    print(f"\n===== FINDINGS: {len(_S['findings'])} total, {len(notable)} notable =====")
    for f in notable:
        print("  ", json.dumps(f, default=str)[:240])
    if not notable:
        print("  (none — no engine anomalies on this trajectory)")
    return _S["findings"]


def save(path="chatgpt_game.json"):
    import pathlib
    s = _S["state"]
    blob = getattr(s, "model_dump_json", None)
    data = {"scenario": _S["scenario"], "history": _S["history"], "findings": _S["findings"]}
    data["state_json"] = blob() if blob else None
    pathlib.Path(path).write_text(json.dumps(data, indent=2, default=str))
    print("saved ->", path)
