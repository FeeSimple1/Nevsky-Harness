#!/usr/bin/env python3
"""Self-play invariant fuzzer for the Nevsky harness.

Drives many full games from a fresh start by repeatedly choosing legal moves
(exactly as an automated player / the harness would), and after EVERY applied
action asserts a set of engine invariants. This is the cheap, repeatable
version of the adversarial sweeps that have repeatedly surfaced real bugs
(Rule 5.2 termination holes, stranded Routed units, re-opened turn state after
game over, etc.) that the curated unit tests did not exercise.

Invariants checked after every action and at game end:

  I1  No live Campaign with a zero-Lord side. If phase==campaign and the game
      is not terminal, BOTH sides must have >= 1 Mustered Lord (Rule 5.2 must
      have fired the instant a side reached zero).
  I2  game_over implies a winner is recorded (meta.winner is not None).
  I3  game_over implies meta.winner agrees with determine_scenario_winner.
  I4  game_over implies legal_moves() == [] (no move offered after the end).
  I5  game_over implies the turn is frozen (campaign_turn.in_feed_pay_disband
      is False; actions_remaining == 0).
  I6  No Mustered Lord carries a stranded Routed-units pile while no combat is
      pending (4.4.4 Losses must have resolved it).
  I7  VP markers stay within the legal 0..17.5 band.

Usage:
    python scripts/fuzz_invariants.py                 # default sweep
    python scripts/fuzz_invariants.py --games 120     # bigger sweep
    python scripts/fuzz_invariants.py --scenarios pleskau watland --seeds 1-50
Exit code is non-zero if any invariant is violated (suitable for CI).
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import random
import sys
from collections import Counter
from pathlib import Path

# Make `src/` importable whether run as a script or imported by pytest.
_REPO = Path(__file__).resolve().parent.parent
_SRC = _REPO / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from nevsky.actions import apply_action, IllegalAction  # noqa: E402
from nevsky.legal_moves import legal_moves  # noqa: E402
from nevsky.scenarios import determine_scenario_winner, load_scenario  # noqa: E402

# Load scripts/self_play.py (a script, not a package) for its move helpers.
_sp_spec = importlib.util.spec_from_file_location(
    "_nevsky_self_play", str(Path(__file__).resolve().parent / "self_play.py"))
sp = importlib.util.module_from_spec(_sp_spec)
_sp_spec.loader.exec_module(sp)  # type: ignore[union-attr]

DEFAULT_SCENARIOS = ("crusade_on_novgorod", "watland", "pleskau")
VP_CAP = 17.5


def _mustered(state, side: str) -> int:
    return sum(1 for l in state.lords.values()
              if l.side == side and l.state == "mustered")


def check_invariants(state) -> str | None:
    """Return a violation string, or None if the state is consistent."""
    m = state.meta
    terminal = (m.phase == "campaign" and m.campaign_step == "done")
    # I1
    if m.phase == "campaign" and not terminal and not m.game_over:
        if _mustered(state, "teutonic") == 0 or _mustered(state, "russian") == 0:
            return ("I1 live Campaign with a zero-Lord side "
                    f"(T={_mustered(state, 'teutonic')}, R={_mustered(state, 'russian')}, "
                    f"step={m.campaign_step})")
    if m.game_over:
        # I2
        if m.winner is None:
            return "I2 game_over but meta.winner is None"
        # I3
        canon = determine_scenario_winner(state)["winner"]
        if m.winner != canon:
            return f"I3 winner disagree: meta={m.winner} canonical={canon}"
        # I4
        if legal_moves(state):
            return "I4 game_over but legal_moves() is non-empty"
        # I5
        if state.campaign_turn.in_feed_pay_disband:
            return "I5 game_over but in_feed_pay_disband re-opened"
        if state.campaign_turn.actions_remaining != 0:
            return "I5 game_over but actions_remaining != 0"
    # I6
    if state.combat_pending is None:
        for lid, l in state.lords.items():
            if l.state == "mustered" and l.routed_units:
                return f"I6 stranded Routed units on {lid}: {dict(l.routed_units)}"
    # I7
    if not (0.0 <= state.calendar.teutonic_vp <= VP_CAP):
        return f"I7 teutonic_vp out of band: {state.calendar.teutonic_vp}"
    if not (0.0 <= state.calendar.russian_vp <= VP_CAP):
        return f"I7 russian_vp out of band: {state.calendar.russian_vp}"
    return None


def run_game(scenario: str, seed: int, policy: str = "priority",
             max_steps: int = 600) -> str | None:
    """Play one self-play game; return the first invariant violation or None."""
    s = load_scenario(scenario, seed=seed)
    rnd = random.Random(seed * 7 + (0 if policy == "priority" else 1))
    for side in ("teutonic", "russian"):
        try:
            apply_action(s, {"type": "confirm_all_setup_transports",
                             "side": side, "args": {}})
        except Exception:
            pass
    rac: Counter = Counter()
    for n in range(max_steps):
        v = check_invariants(s)
        if v:
            return f"{scenario}/seed{seed}/{policy} step{n}: {v}"
        if sp._is_terminal(s):
            break
        raw = legal_moves(s, with_previews=False)
        moves = []
        for mv in raw:
            if "args" in mv and isinstance(mv["args"], dict):
                moves.append(mv)
            else:
                moves.extend(sp._instantiate_templated_move(s, mv))
        if not moves:
            break
        if policy == "random":
            pick = rnd.choice(moves)
        else:
            pick = sorted(moves, key=lambda mm: -sp._move_priority(mm, rac))[
                n % min(3, len(moves))]
        act = {k: v for k, v in pick.items() if k in ("type", "side", "args")}
        if act["type"] == "aow_implement_card":
            act["args"] = sp._populate_event_args(s, act["args"].get("card_id"), act["args"])
        rac[(act["type"], act.get("side"))] += 1
        if n % 50 == 0 and n > 0:
            rac.clear()
        try:
            apply_action(s, act)
        except IllegalAction:
            recovered = False
            variants = (sp._expand_event_variants(s, pick)
                        if pick.get("type") == "aow_implement_card" else [])
            for cand in variants + [mm for mm in moves if mm is not pick]:
                a2 = {k: v for k, v in cand.items() if k in ("type", "side", "args")}
                try:
                    apply_action(s, a2)
                    recovered = True
                    break
                except IllegalAction:
                    continue
            if not recovered:
                break
    return check_invariants(s)


def run_sweep(scenarios, seeds, policies=("priority", "random"),
              max_steps: int = 600):
    """Return a list of violation strings (empty == all clean)."""
    violations = []
    for scen in scenarios:
        for seed in seeds:
            for pol in policies:
                v = run_game(scen, seed, pol, max_steps=max_steps)
                if v:
                    violations.append(v)
    return violations


def _parse_seeds(spec: str):
    if "-" in spec:
        a, b = spec.split("-", 1)
        return range(int(a), int(b) + 1)
    return [int(x) for x in spec.split(",") if x]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Nevsky self-play invariant fuzzer")
    ap.add_argument("--scenarios", nargs="+", default=list(DEFAULT_SCENARIOS))
    ap.add_argument("--seeds", default="1-20",
                    help="seed range 'A-B' or comma list (default 1-20)")
    ap.add_argument("--policies", nargs="+", default=["priority", "random"])
    ap.add_argument("--max-steps", type=int, default=600)
    ap.add_argument("--games", type=int, default=None,
                    help="optional cap on total games (overrides seed count)")
    args = ap.parse_args(argv)

    seeds = list(_parse_seeds(args.seeds))
    if args.games is not None:
        # spread the requested game count across scenarios x policies
        per = max(1, args.games // (len(args.scenarios) * len(args.policies)))
        seeds = list(range(1, per + 1))

    total = len(args.scenarios) * len(seeds) * len(args.policies)
    print(f"Fuzzing {total} games: scenarios={args.scenarios} "
          f"seeds={seeds[0]}..{seeds[-1]} policies={args.policies}")
    violations = run_sweep(args.scenarios, seeds, tuple(args.policies),
                           max_steps=args.max_steps)
    if violations:
        print(f"\nFAIL: {len(violations)} invariant violation(s):")
        for v in violations[:50]:
            print("  -", v)
        return 1
    print(f"\nOK: {total} games clean on all invariants (I1-I7).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
