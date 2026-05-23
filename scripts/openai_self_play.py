"""R219 — Autonomous self-play driver for an OpenAI (ChatGPT) model.

A different LLM walks different trajectories and surfaces different bugs
(the LLM-playthrough lesson). This driver reuses the harness's
model-agnostic LLM interface (briefing + concrete legal actions + apply)
and lets an OpenAI chat model choose moves for BOTH sides, turn by turn,
with the same bug instrumentation as our smoke batches.

Usage (run on a machine with network + OPENAI_API_KEY set):
    PYTHONPATH=src python3 scripts/openai_self_play.py crusade_on_novgorod \
        --seed 1 --model gpt-4o --max-turns 6000 \
        --state docs/chatgpt_crusade_seed1.json \
        --findings docs/chatgpt_crusade_seed1.findings.json

In-sandbox / no-key smoke of the DRIVER itself (picks a deterministic
action instead of calling the API):
    PYTHONPATH=src python3 scripts/openai_self_play.py watland --seed 1 --mock --max-turns 4000

The model never sees the other side's hidden info: each turn the briefing
and legal actions are computed for state.meta.active_player only.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import traceback
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, "src")

import nevsky.actions  # noqa: F401
from nevsky.actions import IllegalAction, apply_action
from nevsky.scenarios import SCENARIO_IDS, determine_scenario_winner, load_scenario
from nevsky.state import GameState
from nevsky.llm.briefing import briefing_for_side
from nevsky.llm.tools import legal_actions_for_side, safe_fallback_for_side

# Reuse the exact concrete-action expansion the Cowork CLI uses, so the
# numbered list the model chooses from is identical and index-applicable.
_LLM_SP = importlib.util.spec_from_file_location(
    "llm_sp", Path(__file__).resolve().parent / "llm_self_play.py")
_llm = importlib.util.module_from_spec(_LLM_SP)
_LLM_SP.loader.exec_module(_llm)
_concrete_actions = _llm._concrete_actions
_cav = _llm.concrete_actions_validated


def is_terminal(state: GameState) -> bool:
    return state.meta.phase == "campaign" and state.meta.campaign_step == "done"


# ----------------------------- invariants --------------------------------

def colocation_violations(state: GameState):
    """R217/R218 invariant: no two opposing MUSTERED Lords both outside a
    Stronghold share a Locale, excluding the active combat Locale while a
    battle is pending."""
    by_loc = defaultdict(set)
    for l in state.lords.values():
        if l.state == "mustered" and l.location is not None and not l.in_stronghold:
            by_loc[l.location].add(l.side)
    bad = [loc for loc, sides in by_loc.items() if len(sides) > 1]
    cp = state.combat_pending
    if cp is not None:
        bad = [loc for loc in bad if loc != cp.to_locale]
    return bad


def invariant_violations(state: GameState) -> list[str]:
    out = []
    co = colocation_violations(state)
    if co:
        out.append(f"co_located_enemies:{co}")
    if state.calendar.teutonic_vp > 17.5 or state.calendar.russian_vp > 17.5:
        out.append(f"vp_over_cap:T={state.calendar.teutonic_vp},R={state.calendar.russian_vp}")
    if state.calendar.teutonic_vp < 0 or state.calendar.russian_vp < 0:
        out.append("vp_negative")
    return out


# ----------------------------- deciders ----------------------------------

SYSTEM_PROMPT = """You are playing the board wargame "Nevsky: Teutons and \
Rus in Collision, 1240-1242" (a GMT Levy & Command game) through a rules \
engine. You control BOTH sides, switching perspective each turn; play each \
turn to win for whichever side is currently active. You only ever see the \
active side's information.

Each turn you are given: a natural-language BRIEFING of the current state \
for the active side, and a NUMBERED list of every legal action. Choose ONE \
action by its index. Reply with ONLY a single JSON object, no prose:
  {"choice": <integer index from the list>, "reason": "<one short clause>"}
Pick a legal, sensible move toward winning the active side. Prefer concrete \
progress (March toward objectives, Siege/Storm enemy Strongholds, Tax/Forage \
to stay supplied, use Capabilities) over passing, but Pass/end-card when \
that is genuinely best."""


def openai_decider(model: str):
    from openai import OpenAI  # lazy import; only needed for real play
    client = OpenAI()

    def decide(side: str, briefing: str, actions: list[dict]) -> tuple[int, str]:
        lines = []
        for i, a in enumerate(actions):
            argp = json.dumps(a.get("args") or a.get("args_template") or {}, default=str)
            note = a.get("note", "")
            lines.append(f"[{i}] {a.get('type','?')} args={argp}" + (f"  // {note}" if note else ""))
        user = (f"ACTIVE SIDE: {side.upper()}\n\nBRIEFING:\n{briefing}\n\n"
                f"LEGAL ACTIONS ({len(actions)}):\n" + "\n".join(lines) +
                "\n\nRespond with ONLY the JSON object.")
        resp = client.chat.completions.create(
            model=model, temperature=0.7,
            messages=[{"role": "system", "content": SYSTEM_PROMPT},
                      {"role": "user", "content": user}],
        )
        text = resp.choices[0].message.content or ""
        return _parse_choice(text, len(actions))

    return decide


def mock_decider():
    """Deterministic stand-in for the API: prefer the first non-pass,
    non-end action; rotate slightly to avoid trivial loops."""
    counter = Counter()

    def decide(side: str, briefing: str, actions: list[dict]) -> tuple[int, str]:
        order = sorted(range(len(actions)),
                       key=lambda i: (actions[i].get("type") in
                                      ("cmd_pass", "end_card", "legate_skip",
                                       "aow_discard_this_levy"),
                                      counter[(actions[i].get("type"),)]))
        idx = order[0]
        counter[(actions[idx].get("type"),)] += 1
        return idx, "mock"

    return decide


def _parse_choice(text: str, n: int) -> tuple[int, str]:
    """Extract {"choice": int} from the model text; fall back to first int."""
    reason = ""
    try:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            obj = json.loads(m.group(0))
            ch = int(obj.get("choice"))
            reason = str(obj.get("reason", ""))[:120]
            if 0 <= ch < n:
                return ch, reason
    except Exception:
        pass
    m = re.search(r"-?\d+", text)
    if m:
        ch = int(m.group(0))
        if 0 <= ch < n:
            return ch, reason or "bare-int"
    return -1, "unparseable"  # signal: use fallback


# ----------------------------- driver ------------------------------------

def play(scenario: str, seed: int, model: str, max_turns: int, mock: bool,
         state_path: Path | None, findings_path: Path | None) -> dict:
    state = load_scenario(scenario, seed=seed)
    for sd in ("teutonic", "russian"):
        try:
            apply_action(state, {"type": "confirm_all_setup_transports", "side": sd, "args": {}})
        except Exception:
            pass
    decide = mock_decider() if mock else openai_decider(model)

    history: list[dict] = []
    findings: list[dict] = []
    action_types: Counter = Counter()
    turn = 0
    while turn < max_turns and not is_terminal(state):
        side = state.meta.active_player or "teutonic"
        actions, _rejected = _cav(state, side)  # validated, LLM-safe menu (P0)
        for _r in _rejected:
            findings.append({"kind": "over_enum_filtered", "turn": turn, "side": side, **_r})
        if not actions:
            findings.append({"kind": "no_legal_moves", "turn": turn,
                             "phase": state.meta.phase,
                             "step": state.meta.campaign_step if state.meta.phase == "campaign" else state.meta.levy_step,
                             "side": side, "box": state.meta.box})
            break
        briefing = briefing_for_side(state, side)
        try:
            idx, reason = decide(side, briefing, actions)
        except Exception as e:
            findings.append({"kind": "decider_error", "turn": turn,
                             "error": f"{type(e).__name__}: {e}"[:200]})
            break
        used_fallback = False
        if idx < 0 or idx >= len(actions):
            chosen = safe_fallback_for_side(state, side)
            used_fallback = True
        else:
            a = actions[idx]
            chosen = {k: v for k, v in a.items() if k in ("type", "side", "args")}
            if "args" not in chosen:  # leftover templated move w/o concrete args
                chosen = safe_fallback_for_side(state, side)
                used_fallback = True
        try:
            apply_action(state, chosen)
            action_types[chosen.get("type")] += 1
        except IllegalAction as e:
            # A model-chosen index maps to a concrete enumerated action;
            # a rejection here is an enumerator/handler mismatch (real).
            findings.append({"kind": "illegal_concrete_action", "turn": turn,
                             "side": side, "action": chosen,
                             "code": str(e.args[0])[:120]})
            try:
                apply_action(state, safe_fallback_for_side(state, side))
                used_fallback = True
            except Exception as e2:
                findings.append({"kind": "fallback_failed", "turn": turn,
                                 "error": f"{type(e2).__name__}: {e2}"[:200]})
                break
        except Exception as e:
            findings.append({"kind": "exception", "turn": turn, "side": side,
                             "action": chosen, "etype": type(e).__name__,
                             "msg": str(e)[:200], "tb": traceback.format_exc()[-800:]})
            break
        # Invariant check after every applied action.
        for v in invariant_violations(state):
            findings.append({"kind": "invariant", "turn": turn, "violation": v,
                             "after_action": chosen.get("type"), "box": state.meta.box})
        history.append({"turn": turn, "side": side, "action": chosen,
                        "reason": reason if not used_fallback else "fallback",
                        "box": state.meta.box})
        turn += 1
        if state_path and turn % 25 == 0:
            _save(state, scenario, history, state_path)

    result = {
        "scenario": scenario, "seed": seed, "model": ("mock" if mock else model),
        "turns": turn, "terminal": is_terminal(state), "box": state.meta.box,
        "teutonic_vp": state.calendar.teutonic_vp, "russian_vp": state.calendar.russian_vp,
        "action_types": dict(action_types.most_common(20)),
        "findings": findings,
        "winner": determine_scenario_winner(state) if is_terminal(state) else None,
    }
    if state_path:
        _save(state, scenario, history, state_path)
    if findings_path:
        findings_path.write_text(json.dumps(result, indent=2, default=str))
    return result


def _save(state: GameState, scenario: str, history: list, path: Path):
    path.write_text(json.dumps({"scenario_id": scenario,
                                "state_json": state.model_dump_json(),
                                "history": history}, indent=2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario", choices=sorted(SCENARIO_IDS))
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--model", default="gpt-4o")
    ap.add_argument("--max-turns", type=int, default=6000)
    ap.add_argument("--mock", action="store_true",
                    help="use a deterministic decider (no API) to smoke-test the driver")
    ap.add_argument("--state", default=None)
    ap.add_argument("--findings", default=None)
    args = ap.parse_args()
    r = play(args.scenario, args.seed, args.model, args.max_turns, args.mock,
             Path(args.state) if args.state else None,
             Path(args.findings) if args.findings else None)
    real = [f for f in r["findings"]
            if f["kind"] in ("exception", "illegal_concrete_action", "invariant",
                             "no_legal_moves", "fallback_failed", "over_enum_filtered")]
    print(json.dumps({k: v for k, v in r.items() if k != "findings"}, indent=2, default=str))
    print(f"\nfindings: {len(r['findings'])} total, {len(real)} notable")
    for f in real[:20]:
        print("  ", json.dumps(f, default=str)[:200])
    return 0 if not real and r["terminal"] else (0 if args.mock else 1)


if __name__ == "__main__":
    sys.exit(main())
