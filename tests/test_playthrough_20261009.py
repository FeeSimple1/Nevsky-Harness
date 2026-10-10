"""Diagnostic game on an isolated playtest branch; no engine changes."""
from __future__ import annotations
import hashlib
import json
import sys
import traceback
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def test_diagnostic_pleskau_game(capsys):
    from nevsky.actions import apply_action
    from nevsky.scenarios import load_scenario, determine_scenario_winner
    from nevsky.state import GameState
    from nevsky.static_data import load_locales
    from llm_self_play import concrete_actions_validated, is_terminal
    from strategic_agent import _action_score

    seed = 20261009
    state = load_scenario("pleskau", seed=seed)
    transcript, findings = [], []
    repeated = Counter()
    visits = Counter()
    locales = load_locales()
    for side in ("teutonic", "russian"):
        action = {"type": "confirm_all_setup_transports", "side": side, "args": {}}
        try:
            apply_action(state, action)
            transcript.append({"setup": action})
        except Exception as exc:
            findings.append({"kind": "setup_rejection", "side": side, "error": str(exc)})

    def fingerprint(s):
        return hashlib.sha256(s.model_dump_json().encode()).hexdigest()

    def score(action, side):
        typ, args = action["type"], action.get("args", {})
        value = _action_score(state, action, side)
        if typ == "plan_add_card":
            value = 110 if args.get("card") != "pass" else 20
        if typ == "finalize_plan":
            value = 80
        if typ == "cmd_march":
            lid = args.get("lord_id")
            dest = args.get("to")
            value -= 18 * visits[(side, lid, dest)]
            loc = state.locales.get(dest)
            if loc and (getattr(loc, "teutonic_conquered", 0) if side == "teutonic" else getattr(loc, "russian_conquered", 0)):
                value -= 20
        # Keep the normal combat-oriented ranking, but discourage an unchanged
        # action/state pair if a non-advancing handler slips into the menu.
        key = (fingerprint(state), json.dumps(action, sort_keys=True, default=str))
        value -= 1000 * repeated[key]
        return value

    for step in range(2500):
        if is_terminal(state):
            break
        side = state.meta.active_player or "teutonic"
        before = fingerprint(state)
        menu, rejected = concrete_actions_validated(state, side)
        if fingerprint(state) != before:
            findings.append({"kind": "menu_mutates_live_state", "step": step})
            break
        for item in rejected:
            findings.append({"kind": "rejected_menu_candidate", "step": step, "box": state.meta.box, "side": side, **item})
        concrete = [{k: v for k, v in a.items() if k in ("type", "side", "args")} for a in menu if isinstance(a.get("args"), dict)]
        if not concrete:
            findings.append({"kind": "no_concrete_moves", "step": step, "menu": menu})
            break
        action = max(concrete, key=lambda a: score(a, side))
        repeated[(before, json.dumps(action, sort_keys=True, default=str))] += 1
        context = {"step": step, "box": state.meta.box, "side": side, "phase": state.meta.phase, "levy_step": state.meta.levy_step, "campaign_step": state.meta.campaign_step, "action": action}
        try:
            probe = state.model_copy(deep=True)
            expected = apply_action(probe, action)
            result = apply_action(state, action)
            if fingerprint(state) != fingerprint(probe) or result != expected:
                findings.append({"kind": "nondeterministic_apply", **context})
            if fingerprint(state) == before:
                findings.append({"kind": "action_without_state_change", **context})
            if action["type"] == "cmd_march":
                args = action.get("args", {})
                visits[(side, args.get("lord_id"), args.get("to"))] += 1
            if step % 10 == 0:
                restored = GameState.model_validate_json(state.model_dump_json())
                if fingerprint(restored) != fingerprint(state):
                    findings.append({"kind": "save_reload_mismatch", **context})
                state = restored
            transcript.append({**context, "result": result, "vp": [state.calendar.teutonic_vp, state.calendar.russian_vp]})
        except Exception as exc:
            findings.append({"kind": "exception", **context, "error": str(exc), "traceback": traceback.format_exc()})
            break
    report = {"scenario": "pleskau", "seed": seed, "policy": "combat-oriented self-play with anti-loop marching and full lord plans", "terminal": is_terminal(state), "winner": determine_scenario_winner(state) if is_terminal(state) else None, "vp": [state.calendar.teutonic_vp, state.calendar.russian_vp], "box": state.meta.box, "steps": len(transcript), "findings": findings, "transcript": transcript}
    with capsys.disabled():
        print("\nNEVSKY_PLAYTEST_REPORT_BEGIN")
        print(json.dumps(report, default=str))
        print("NEVSKY_PLAYTEST_REPORT_END\n")
    assert report["terminal"], json.dumps({k: v for k, v in report.items() if k != "transcript"}, default=str)
    severe = [f for f in findings if f["kind"] in {"exception", "nondeterministic_apply", "save_reload_mismatch", "menu_mutates_live_state", "no_concrete_moves"}]
    assert not severe, json.dumps(severe, default=str)
