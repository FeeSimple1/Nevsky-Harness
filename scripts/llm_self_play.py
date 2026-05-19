"""R195 — turn-by-turn LLM self-play CLI driver.

Designed for use in Cowork mode where a single Claude instance
plays both sides. The script persists state to disk between
invocations so Cowork-Claude can run one command per turn:

  python scripts/llm_self_play.py start pleskau         # create new game
  python scripts/llm_self_play.py status                # whose turn, VP, phase
  python scripts/llm_self_play.py briefing              # natural-language briefing for active side
  python scripts/llm_self_play.py actions               # numbered list of legal actions
  python scripts/llm_self_play.py apply 3               # apply action by index
  python scripts/llm_self_play.py apply '{"type":"...","args":{...}}'
  python scripts/llm_self_play.py history               # last 20 moves
  python scripts/llm_self_play.py terminal              # 0 = ongoing, 1 = terminal+winner

Hidden-info filter respected per side. Each turn the briefing and
legal-actions are computed for state.meta.active_player.

Default state path: ./nevsky_self_play.json
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, "src")

import nevsky.actions  # noqa: F401
from nevsky.actions import IllegalAction, apply_action
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import (
    SCENARIO_IDS, determine_scenario_winner, load_scenario,
)
from nevsky.state import GameState
from nevsky.llm.briefing import briefing_for_side
from nevsky.llm.tools import legal_actions_for_side, safe_fallback_for_side


DEFAULT_PATH = Path("nevsky_self_play.json")


# ---------- persistence ---------------------------------------------------


def save_state(state: GameState, scenario_id: str, history: list,
               path: Path) -> None:
    payload = {
        "scenario_id": scenario_id,
        "state_json": state.model_dump_json(),
        "history": history,
    }
    path.write_text(json.dumps(payload, indent=2))


def load_state(path: Path) -> tuple[GameState, str, list]:
    if not path.exists():
        raise SystemExit(
            f"no saved game at {path}. Run 'start <scenario>' first."
        )
    payload = json.loads(path.read_text())
    state = GameState.model_validate_json(payload["state_json"])
    return state, payload["scenario_id"], payload.get("history", [])


# ---------- helpers -------------------------------------------------------


def active_side(state: GameState) -> str:
    return state.meta.active_player or "teutonic"


def is_terminal(state: GameState) -> bool:
    return (state.meta.phase == "campaign"
            and state.meta.campaign_step == "done")


def _concrete_actions(state: GameState, side: str) -> list[dict]:
    """All legal_actions for the side with concrete args, templated
    moves expanded. Mirrors the round-trip sweep's expansion so the
    LLM sees the same palette."""
    out = []
    raw = legal_actions_for_side(state, side)
    # legal_actions_for_side already filters by side; expand templates.
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "sp_mod", Path(__file__).resolve().parent / "self_play.py")
    sp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sp)
    for m in raw:
        if "args" in m and isinstance(m["args"], dict):
            out.append(m)
        else:
            try:
                out.extend(sp._instantiate_templated_move(state, m))
            except Exception:
                # Leave the templated form as-is for the LLM to fill in.
                out.append(m)
    return out


# ---------- subcommands ---------------------------------------------------


def cmd_start(args):
    if args.scenario not in SCENARIO_IDS:
        raise SystemExit(
            f"unknown scenario {args.scenario!r}; loadable: "
            f"{[s for s in SCENARIO_IDS if s != 'quickstart']}"
        )
    state = load_scenario(args.scenario, seed=args.seed)
    # Auto-confirm setup transports.
    for side in ("teutonic", "russian"):
        try:
            apply_action(state, {"type": "confirm_all_setup_transports",
                                  "side": side, "args": {}})
        except Exception:
            pass
    save_state(state, args.scenario, [], Path(args.state))
    print(f"started {args.scenario} (seed={args.seed}) → {args.state}")
    cmd_status(args)


def cmd_status(args):
    state, scenario_id, history = load_state(Path(args.state))
    side = active_side(state)
    terminal = is_terminal(state)
    print(f"scenario:        {scenario_id}")
    print(f"phase:           {state.meta.phase}")
    print(f"step:            {state.meta.levy_step or state.meta.campaign_step}")
    print(f"box:             {state.meta.box}")
    print(f"active side:     {side}")
    print(f"VP (teu/rus):    {state.calendar.teutonic_vp:.1f} / {state.calendar.russian_vp:.1f}")
    print(f"turn count:      {len(history)}")
    print(f"terminal:        {terminal}")
    if terminal:
        try:
            w = determine_scenario_winner(state)
            print(f"winner:          {w}")
        except Exception as e:
            print(f"winner:          (error: {e})")


def cmd_briefing(args):
    state, _, _ = load_state(Path(args.state))
    side = active_side(state)
    print(f"=== briefing for {side.upper()} ===")
    print(briefing_for_side(state, side))


def cmd_actions(args):
    state, _, _ = load_state(Path(args.state))
    side = active_side(state)
    actions = _concrete_actions(state, side)
    print(f"=== {len(actions)} legal action(s) for {side.upper()} ===")
    for i, a in enumerate(actions):
        note = a.get("note", "")
        atype = a.get("type", "?")
        argspart = json.dumps(a.get("args") or a.get("args_template") or {},
                              default=str)
        print(f"  [{i}] {atype:<25} args={argspart}")
        if note:
            print(f"       note: {note}")


def cmd_apply(args):
    state, scenario_id, history = load_state(Path(args.state))
    side = active_side(state)
    actions = _concrete_actions(state, side)

    target = args.action
    # Parse: either a numeric index into the legal-actions list, or
    # a JSON action dict.
    chosen: dict | None = None
    try:
        idx = int(target)
        if 0 <= idx < len(actions):
            chosen = actions[idx]
        else:
            raise SystemExit(f"index {idx} out of range (0..{len(actions)-1})")
    except ValueError:
        try:
            parsed = json.loads(target)
        except json.JSONDecodeError as e:
            raise SystemExit(f"action must be index or JSON: {e}")
        if not isinstance(parsed, dict):
            raise SystemExit("JSON action must be an object")
        chosen = parsed
        chosen.setdefault("side", side)

    action = {k: v for k, v in chosen.items()
              if k in ("type", "side", "args")}
    try:
        result = apply_action(state, action)
    except IllegalAction as e:
        raise SystemExit(f"illegal action ({e.code}): {e}")

    history.append({
        "turn": len(history) + 1,
        "side": side,
        "action": action,
        "reasoning": args.reasoning,
        "phase": state.meta.phase,
        "step": state.meta.levy_step or state.meta.campaign_step,
        "result": result if isinstance(result, dict) else str(result),
    })
    save_state(state, scenario_id, history, Path(args.state))
    print(f"applied: {action['type']} side={side} args={action.get('args')}")
    if isinstance(result, dict) and result.get("outcome"):
        print(f"  outcome: {result['outcome']}")
    cmd_status(args)


def cmd_fallback(args):
    """Apply the safe phase-appropriate fallback (advance_step /
    cmd_pass / end_card / legate_skip)."""
    state, scenario_id, history = load_state(Path(args.state))
    side = active_side(state)
    fb = safe_fallback_for_side(state, side)
    if fb is None:
        raise SystemExit("no safe fallback available")
    try:
        result = apply_action(state, fb)
    except IllegalAction as e:
        raise SystemExit(f"fallback rejected ({e.code}): {e}")
    history.append({
        "turn": len(history) + 1,
        "side": side,
        "action": fb,
        "reasoning": "safe_fallback",
        "phase": state.meta.phase,
        "step": state.meta.levy_step or state.meta.campaign_step,
        "result": result if isinstance(result, dict) else str(result),
    })
    save_state(state, scenario_id, history, Path(args.state))
    print(f"fallback applied: {fb}")
    cmd_status(args)


def cmd_history(args):
    _, _, history = load_state(Path(args.state))
    tail = history[-args.n:] if args.n > 0 else history
    print(f"=== last {len(tail)} of {len(history)} moves ===")
    for h in tail:
        side_short = "T" if h["side"] == "teutonic" else "R"
        atype = h["action"].get("type", "?")
        argspart = json.dumps(h["action"].get("args") or {}, default=str)
        print(f"  [{h['turn']:>3}][{side_short}] "
              f"{h['phase'][:4]}/{(h.get('step') or '')[:8]:<8} "
              f"{atype} {argspart}")


def cmd_terminal(args):
    state, _, _ = load_state(Path(args.state))
    if is_terminal(state):
        try:
            w = determine_scenario_winner(state)
            print(json.dumps({"terminal": True, "winner": w}))
        except Exception as e:
            print(json.dumps({"terminal": True, "winner_error": str(e)}))
    else:
        print(json.dumps({"terminal": False,
                          "active_side": active_side(state)}))


# ---------- main ----------------------------------------------------------


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--state", default=str(DEFAULT_PATH),
                    help=f"state file (default {DEFAULT_PATH})")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_start = sub.add_parser("start", help="create new game")
    p_start.add_argument("scenario")
    p_start.add_argument("--seed", type=int, default=1)
    p_start.set_defaults(func=cmd_start)

    p_status = sub.add_parser("status", help="whose turn, phase, VP")
    p_status.set_defaults(func=cmd_status)

    p_briefing = sub.add_parser("briefing", help="briefing for active side")
    p_briefing.set_defaults(func=cmd_briefing)

    p_actions = sub.add_parser("actions", help="legal actions for active side")
    p_actions.set_defaults(func=cmd_actions)

    p_apply = sub.add_parser("apply", help="apply an action")
    p_apply.add_argument("action", help="index (int) or JSON action dict")
    p_apply.add_argument("--reasoning", default=None,
                         help="optional rationale recorded in history")
    p_apply.set_defaults(func=cmd_apply)

    p_fb = sub.add_parser("fallback", help="apply safe phase-appropriate fallback")
    p_fb.set_defaults(func=cmd_fallback)

    p_hist = sub.add_parser("history", help="show recent moves")
    p_hist.add_argument("-n", type=int, default=20)
    p_hist.set_defaults(func=cmd_history)

    p_term = sub.add_parser("terminal", help="JSON terminal+winner check")
    p_term.set_defaults(func=cmd_terminal)

    args = ap.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
