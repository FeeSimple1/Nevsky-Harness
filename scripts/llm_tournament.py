"""R192 — LLM-vs-LLM tournament harness.

Runs configurable "agents" (deterministic strategy implementations
that mimic different LLM personas) head-to-head across all
loadable scenarios. Produces a leaderboard with win counts, VP
margins, and per-pairing breakdowns.

This is useful for:
  - Evaluating system-prompt variants of the LLM-play interface
    (run two prompt configurations against each other).
  - Surfacing additional bugs — a tournament generates many more
    games than the standard sweep, exercising rarer combinations.
  - Establishing a baseline before any future model swap.

The "agents" in this harness are NOT live LLMs (this is an
offline tool). They're deterministic strategies pulled from
scripts/self_play.py, scripts/strategic_agent.py, and a couple
of small custom personas defined here. Plug a real LLM in by
implementing the same `pick(state, side, history) -> action`
interface.

Run:
  PYTHONPATH=src python3 scripts/llm_tournament.py
    [--scenarios pleskau,watland,...]
    [--agents greedy,strategic,aggressive,conservative]
    [--rounds-per-pairing 2]   # one as teutonic, one as russian
    [--max-steps 20000]
    [--output tournament.json]

Default: every pair × every scenario × both sides (round-robin
across N agents -> N*(N-1) games per scenario × scenarios).
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

import nevsky.actions  # noqa: F401
from nevsky.actions import IllegalAction, apply_action
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import load_scenario

# Load self_play + strategic_agent modules at runtime.
_SCRIPTS = Path(__file__).resolve().parent
spec_sp = importlib.util.spec_from_file_location("sp_mod", _SCRIPTS / "self_play.py")
sp = importlib.util.module_from_spec(spec_sp)
spec_sp.loader.exec_module(sp)

spec_sa = importlib.util.spec_from_file_location("sa_mod", _SCRIPTS / "strategic_agent.py")
sa = importlib.util.module_from_spec(spec_sa)
spec_sa.loader.exec_module(sa)


_LOADABLE_SCENARIOS = [
    "watland", "pleskau", "peipus",
    "return_of_the_prince", "return_of_the_prince_nicolle",
    "crusade_on_novgorod",
]


# --- Agent personas ---------------------------------------------------------
# Each agent is `pick(state, side, recent_actions_counter) -> action_dict`
# Returns a fully-populated action (type, side, args). The caller may apply
# it directly via apply_action.


def _concrete(state):
    out = []
    for m in legal_moves(state, with_previews=False):
        if "args" in m and isinstance(m["args"], dict):
            out.append(m)
        else:
            try:
                out.extend(sp._instantiate_templated_move(state, m))
            except Exception:
                pass
    return out


def _action_only(pick) -> dict:
    return {k: v for k, v in pick.items() if k in ("type", "side", "args")}


def agent_greedy(state, side, recent):
    """Highest-priority self_play move; cycle through top-3 on ties."""
    moves = _concrete(state)
    if not moves:
        return None
    prioritized = sorted(moves, key=lambda m: -sp._move_priority(m, recent))
    step_count = sum(recent.values())
    return _action_only(prioritized[step_count % min(3, len(prioritized))])


def agent_strategic(state, side, recent):
    """Use strategic_agent.py scoring (combat-aggressive)."""
    moves = _concrete(state)
    if not moves:
        return None
    scored = sorted(moves, key=lambda m: -sa._action_score(state, m, side))
    return _action_only(scored[0])


def agent_aggressive(state, side, recent):
    """Like greedy but with combat-shape boosts: storm/sally/march to
    enemy heavily preferred."""
    moves = _concrete(state)
    if not moves:
        return None
    boost = {"cmd_storm": 30, "cmd_sally": 25, "cmd_siege": 15,
             "stand_battle": 30, "cmd_march": 8}
    def score(m):
        return sp._move_priority(m, recent) + boost.get(m.get("type"), 0)
    return _action_only(sorted(moves, key=lambda m: -score(m))[0])


def agent_conservative(state, side, recent):
    """Greedy with economy boosts and combat penalties."""
    moves = _concrete(state)
    if not moves:
        return None
    boost = {"cmd_tax": 20, "cmd_forage": 15, "cmd_supply": 12,
             "pay_with_coin": 18, "muster_lord": 10}
    penalty = {"cmd_storm": -40, "cmd_sally": -30, "stand_battle": -25,
               "cmd_siege": -20}
    def score(m):
        return (sp._move_priority(m, recent)
                + boost.get(m.get("type"), 0)
                + penalty.get(m.get("type"), 0))
    return _action_only(sorted(moves, key=lambda m: -score(m))[0])


AGENTS: dict[str, Callable] = {
    "greedy": agent_greedy,
    "strategic": agent_strategic,
    "aggressive": agent_aggressive,
    "conservative": agent_conservative,
}


# --- Game runner ------------------------------------------------------------


def play_game(scenario: str, teu_agent: str, rus_agent: str,
              seed: int = 0, max_steps: int = 20000):
    """Run one game; returns dict with result, steps, vp, winner."""
    state = load_scenario(scenario, seed=seed)
    for side in ("teutonic", "russian"):
        try:
            apply_action(state, {"type": "confirm_all_setup_transports",
                                 "side": side, "args": {}})
        except Exception:
            pass

    recent_t: Counter = Counter()
    recent_r: Counter = Counter()
    illegal_streak = 0
    last_box = None
    no_progress = 0

    for step in range(max_steps):
        if sp._is_terminal(state):
            break
        side = state.meta.active_player
        if side is None:
            break
        agent_name = teu_agent if side == "teutonic" else rus_agent
        recent = recent_t if side == "teutonic" else recent_r
        agent = AGENTS[agent_name]
        action = agent(state, side, recent)
        if action is None:
            break
        sig = (action["type"], action.get("side"),
               json.dumps(action.get("args", {}), default=str, sort_keys=True))
        recent[sig] += 1
        if state.meta.box != last_box:
            last_box = state.meta.box
            no_progress = 0
        no_progress += 1
        if no_progress > 200:
            break
        try:
            apply_action(state, action)
            illegal_streak = 0
        except IllegalAction:
            illegal_streak += 1
            if illegal_streak >= 3:
                # Fall through to safe action.
                from nevsky.llm.tools import safe_fallback_for_side
                fb = safe_fallback_for_side(state, side)
                try:
                    apply_action(state, fb)
                except Exception:
                    break
                illegal_streak = 0

    # Compute result.
    vp_t = state.calendar.teutonic_vp
    vp_r = state.calendar.russian_vp
    if vp_t > vp_r:
        winner = "teutonic"
    elif vp_r > vp_t:
        winner = "russian"
    else:
        winner = "draw"
    return {
        "scenario": scenario,
        "teu_agent": teu_agent,
        "rus_agent": rus_agent,
        "seed": seed,
        "steps": step + 1,
        "terminal": sp._is_terminal(state),
        "vp_teutonic": vp_t,
        "vp_russian": vp_r,
        "winner": winner,
    }


# --- Tournament driver ------------------------------------------------------


def run_tournament(scenarios, agents, seed: int = 1, max_steps: int = 20000):
    games = []
    pairings = [(a, b) for a in agents for b in agents if a != b]
    total = len(scenarios) * len(pairings)
    n = 0
    for scenario in scenarios:
        for teu, rus in pairings:
            n += 1
            r = play_game(scenario, teu, rus, seed=seed, max_steps=max_steps)
            games.append(r)
            mark = "T" if r["terminal"] else "."
            print(f"  [{n:>3}/{total}] {scenario:<30} "
                  f"{teu:>14} vs {rus:<14} -> {r['winner']:<9} "
                  f"({r['vp_teutonic']:.1f} - {r['vp_russian']:.1f}) "
                  f"steps={r['steps']:<5} {mark}")
    return games


def render_leaderboard(games) -> str:
    by_agent = defaultdict(lambda: {"wins": 0, "losses": 0, "draws": 0,
                                    "games": 0, "vp_for": 0.0, "vp_against": 0.0})
    for g in games:
        teu, rus = g["teu_agent"], g["rus_agent"]
        for agent, side in [(teu, "teutonic"), (rus, "russian")]:
            by_agent[agent]["games"] += 1
            opp_side = "russian" if side == "teutonic" else "teutonic"
            by_agent[agent]["vp_for"] += g[f"vp_{side}"]
            by_agent[agent]["vp_against"] += g[f"vp_{opp_side}"]
            if g["winner"] == side:
                by_agent[agent]["wins"] += 1
            elif g["winner"] == "draw":
                by_agent[agent]["draws"] += 1
            else:
                by_agent[agent]["losses"] += 1
    sorted_agents = sorted(by_agent.items(),
                           key=lambda kv: (-kv[1]["wins"], -kv[1]["vp_for"]))
    out = ["=== Tournament Leaderboard ===",
           f"{'Agent':<14} {'W':>4} {'L':>4} {'D':>4} {'Games':>6} "
           f"{'WinRate':>8} {'VP_for':>8} {'VP_avg':>8}"]
    for name, s in sorted_agents:
        wr = s["wins"] / s["games"] if s["games"] else 0.0
        vp_avg = (s["vp_for"] / s["games"]) if s["games"] else 0.0
        out.append(f"{name:<14} {s['wins']:>4} {s['losses']:>4} "
                   f"{s['draws']:>4} {s['games']:>6} {wr:>7.1%} "
                   f"{s['vp_for']:>8.1f} {vp_avg:>8.1f}")
    return "\n".join(out)


def render_matchups(games) -> str:
    """Per-pairing breakdown (Agent A vs Agent B)."""
    by_matchup = defaultdict(lambda: defaultdict(int))
    for g in games:
        key = f"{g['teu_agent']}(T) vs {g['rus_agent']}(R)"
        by_matchup[key][g["winner"]] += 1
    out = ["=== Per-matchup ==="]
    for k, counts in sorted(by_matchup.items()):
        out.append(f"  {k:<42} teu_wins={counts['teutonic']:>2} "
                   f"rus_wins={counts['russian']:>2} "
                   f"draw={counts['draw']:>2}")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", default=",".join(_LOADABLE_SCENARIOS))
    ap.add_argument("--agents", default=",".join(AGENTS.keys()))
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--max-steps", type=int, default=20000)
    ap.add_argument("--output", default="")
    args = ap.parse_args()

    scenarios = [s.strip() for s in args.scenarios.split(",") if s.strip()]
    agents = [a.strip() for a in args.agents.split(",") if a.strip()]
    for a in agents:
        if a not in AGENTS:
            print(f"Unknown agent: {a}; available: {list(AGENTS)}")
            return 1

    print(f"=== R192 LLM-tournament ===")
    print(f"scenarios: {scenarios}")
    print(f"agents:    {agents}")
    print(f"seed:      {args.seed}")
    print()
    games = run_tournament(scenarios, agents, seed=args.seed,
                           max_steps=args.max_steps)
    print()
    print(render_leaderboard(games))
    print()
    print(render_matchups(games))

    if args.output:
        Path(args.output).write_text(json.dumps(games, indent=2, default=str))
        print(f"\nSaved game-by-game results to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
