"""R190 enumerator/handler round-trip sweep.

Implements the §2 audit from CROSS_PROJECT_LESSONS.md: at every
step, snapshot the state and replay every legal_moves shape
through apply_action. A raised IllegalAction signals an
enumerator/handler asymmetry (SMOKE-118/119/122 family).

Uses scripts/self_play.py's priority + templated-move expansion
so the sweep actually traverses the game rather than stalling
on a low-priority self-loop (aow_shuffle, plan_add_card pass).
The advance step uses the self-play policy; the probe step
runs every concrete move at the state through apply_action.

Run:  PYTHONPATH=src python3 scripts/roundtrip_sweep.py
       [--scenarios pleskau,...] [--seeds 1,2,3]
       [--max-steps 5000]

Exit code 0 always — informational sweep, promote findings to
SMOKE-NNN regression tests.
"""
from __future__ import annotations
import argparse
import json
import sys
import traceback
from collections import Counter

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

import nevsky.actions  # noqa: F401
from nevsky.actions import IllegalAction, apply_action
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import SCENARIO_IDS, load_scenario

# Reuse the priority + templated-move expansion from self_play.
from self_play import (
    _ACTION_PRIORITY,
    _move_priority,
    _instantiate_templated_move,
    _is_terminal,
)


# Lifecycle / plumbing moves we don't need to probe — they're
# unconditionally legal at the states where the enumerator emits
# them and would generate noisy passes.
_SKIP_PROBE_TYPES = {
    "advance_step", "command_reveal", "fpd_resolve",
    "end_card", "legate_skip", "finalize_plan", "aow_shuffle",
    "confirm_setup_transport", "confirm_all_setup_transports",
    "system_setup_complete", "end_campaign_resolve",
    "plan_add_card",  # gets enumerated to "pass" / Lord IDs;
                      # asymmetries here would have been caught
                      # in earlier rounds.
}


def _try_apply(s, action):
    try:
        apply_action(s, action)
        return False, "", ""
    except IllegalAction as e:
        return True, e.code, str(e)
    except Exception as e:
        return True, "CRASH:" + type(e).__name__, str(e)


def _concrete_moves(state):
    """Return list of concrete-args moves (templated expanded)."""
    out = []
    for m in legal_moves(state, with_previews=False):
        if "args" in m and isinstance(m["args"], dict):
            out.append(m)
        else:
            try:
                out.extend(_instantiate_templated_move(state, m))
            except Exception:
                pass
    return out


def sweep_one(scenario, seed, max_steps, verbose=False):
    s = load_scenario(scenario, seed=seed)
    # Skip setup-transport confirmation prefix the same way self_play does.
    for side in ("teutonic", "russian"):
        try:
            apply_action(s, {"type": "confirm_all_setup_transports",
                              "side": side, "args": {}})
        except Exception:
            pass

    findings = []
    total_probes = 0
    recent_action_counts = Counter()
    last_box = None
    no_progress_count = 0
    step = 0
    terminal = 0
    while step < max_steps:
        if _is_terminal(s):
            terminal = 1
            break
        moves = _concrete_moves(s)
        if not moves:
            break

        # Probe every concrete move at this state (except skip types).
        for m in moves:
            if m.get("type") in _SKIP_PROBE_TYPES:
                continue
            total_probes += 1
            snapshot = s.model_copy(deep=True)
            raised, code, msg = _try_apply(snapshot, m)
            if raised:
                findings.append({
                    "scenario": scenario, "seed": seed, "step": step,
                    "action_type": m.get("type"),
                    "side": m.get("side"),
                    "phase": s.meta.phase,
                    "campaign_step": s.meta.campaign_step,
                    "levy_step": getattr(s.meta, "levy_step", None),
                    "code": code,
                    "message": msg[:240],
                    "args": json.dumps(m.get("args"), default=str)[:240],
                })

        # Advance under the self_play priority policy.
        if s.meta.box != last_box:
            last_box = s.meta.box
            no_progress_count = 0
        prioritized = sorted(moves, key=lambda m: -_move_priority(m, recent_action_counts))
        pick = prioritized[step % min(3, len(prioritized))]
        action = {k: v for k, v in pick.items()
                  if k in ("type", "side", "args")}
        sig = (pick["type"], pick.get("side"),
               json.dumps(pick.get("args", {}), default=str, sort_keys=True))
        recent_action_counts[sig] += 1
        no_progress_count += 1
        if no_progress_count > 50:
            # Stuck — break to avoid infinite loops in degenerate states.
            break
        raised, code, msg = _try_apply(s, action)
        if raised:
            # The chosen advancing move itself errored; that's a
            # finding too. Break to avoid looping forever.
            findings.append({
                "scenario": scenario, "seed": seed, "step": step,
                "action_type": pick.get("type"),
                "side": pick.get("side"),
                "phase": s.meta.phase,
                "campaign_step": s.meta.campaign_step,
                "levy_step": getattr(s.meta, "levy_step", None),
                "code": "ADVANCE_BLOCK:" + code,
                "message": msg[:240],
                "args": json.dumps(pick.get("args"), default=str)[:240],
            })
            break
        step += 1
    return findings, step, total_probes, terminal


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", default=",".join(
        s for s in SCENARIO_IDS if s != "quickstart"))
    ap.add_argument("--seeds", default="1,2,3")
    ap.add_argument("--max-steps", type=int, default=5000)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    scenarios = [s.strip() for s in args.scenarios.split(",") if s.strip()]
    seeds = [int(x.strip()) for x in args.seeds.split(",") if x.strip()]

    print("=== R190 round-trip sweep ===")
    print(f"scenarios: {scenarios}")
    print(f"seeds: {seeds}")
    print(f"max-steps: {args.max_steps}")
    print()
    all_findings = []
    total_steps = 0
    total_probes = 0
    terminals = 0
    sessions = 0
    for sc in scenarios:
        for sd in seeds:
            sessions += 1
            try:
                findings, steps, probes, term = sweep_one(
                    sc, sd, args.max_steps, args.verbose)
            except Exception as e:
                print(f"!! sweep crashed {sc} seed={sd}: {type(e).__name__}: {e}")
                if args.verbose:
                    traceback.print_exc()
                continue
            total_steps += steps
            total_probes += probes
            terminals += term
            all_findings.extend(findings)
            print(f"  {sc:<35} seed={sd:<3} steps={steps:<5} "
                  f"probes={probes:<7} terminal={bool(term)} "
                  f"findings={len(findings)}")

    print()
    print("=== Summary ===")
    print(f"sessions:        {sessions}")
    print(f"terminal:        {terminals}/{sessions}")
    print(f"total steps:     {total_steps}")
    print(f"total probes:    {total_probes}")
    print(f"total findings:  {len(all_findings)}")
    print()

    if all_findings:
        by_code = Counter((f["action_type"], f["code"]) for f in all_findings)
        print("=== Findings grouped by (action_type, code) ===")
        for (atype, code), count in by_code.most_common():
            print(f"  {count:>5}  {atype:<35} {code}")
        print()
        print("=== First example per (action_type, code) ===")
        seen = set()
        for f in all_findings:
            key = (f["action_type"], f["code"])
            if key in seen:
                continue
            seen.add(key)
            print(f"  [{f['scenario']}/{f['seed']}/step{f['step']}/"
                  f"{f['phase']}/{f.get('campaign_step') or f.get('levy_step')}]")
            print(f"    action: {f['action_type']} side={f['side']} args={f['args']}")
            print(f"    code:   {f['code']}")
            print(f"    msg:    {f['message']}")
            print()
    else:
        print("(no findings — enumerator/handler are aligned on this sweep)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
