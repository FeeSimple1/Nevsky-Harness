"""Replay capture — runs a self-play and records action sequence
plus per-Campaign-end state snapshots for strategic analysis.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from typing import Any

from nevsky.actions import IllegalAction, apply_action
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import determine_scenario_winner, load_scenario

# Load self_play
spec = importlib.util.spec_from_file_location("sp", "scripts/self_play.py")
sp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sp)


def capture(scenario, seed, max_steps=20000):
    s = load_scenario(scenario, seed=seed)
    for side in ("teutonic", "russian"):
        try:
            apply_action(s, {"type": "confirm_all_setup_transports",
                              "side": side, "args": {}})
        except Exception:
            pass

    history = []
    snapshots = []
    last_box = None
    last_phase = None

    from collections import Counter
    rac = Counter()

    for step_n in range(max_steps):
        if sp._is_terminal(s):
            snapshots.append({
                "step": step_n, "box": s.meta.box,
                "phase": s.meta.phase, "campaign_step": s.meta.campaign_step,
                "t_vp": s.calendar.teutonic_vp, "r_vp": s.calendar.russian_vp,
                "t_mustered": [lid for lid, l in s.lords.items()
                               if l.side == "teutonic" and l.state == "mustered"],
                "r_mustered": [lid for lid, l in s.lords.items()
                               if l.side == "russian" and l.state == "mustered"],
                "marker": "terminal",
            })
            break

        moves_raw = legal_moves(s, with_previews=False)
        moves = []
        for m in moves_raw:
            if "args" in m and isinstance(m["args"], dict):
                moves.append(m)
            else:
                moves.extend(sp._instantiate_templated_move(s, m))
        if not moves:
            break

        # Snapshot on campaign-end boundary
        if (s.meta.box != last_box and last_box is not None) or \
           (last_phase == "campaign" and s.meta.phase == "levy"):
            snapshots.append({
                "step": step_n, "box": s.meta.box, "phase": s.meta.phase,
                "campaign_step": s.meta.campaign_step,
                "t_vp": s.calendar.teutonic_vp, "r_vp": s.calendar.russian_vp,
                "marker": "phase_transition",
            })

        last_box = s.meta.box
        last_phase = s.meta.phase

        prioritized = sorted(moves, key=lambda m: -sp._move_priority(m, rac))
        pick = prioritized[step_n % min(3, len(prioritized))]
        action = {k: v for k, v in pick.items() if k in ("type", "side", "args")}
        if action["type"] == "aow_implement_card":
            cid = action["args"].get("card_id")
            action["args"] = sp._populate_event_args(s, cid, action["args"])
        sig = (action["type"], action.get("side"),
               json.dumps(action.get("args", {}), default=str, sort_keys=True))
        rac[sig] += 1
        if step_n % 50 == 0 and step_n > 0:
            rac.clear()

        try:
            result = apply_action(s, action)
            history.append({"step": step_n, "action": action,
                            "outcome": _summarize_result(result)})
            if isinstance(result, dict) and result.get("game_over"):
                break
        except IllegalAction:
            recovered = False
            same_variants = sp._expand_event_variants(s, pick) if pick.get("type") == "aow_implement_card" else []
            for cand in same_variants + list(prioritized[1:]):
                act = {k: v for k, v in cand.items() if k in ("type", "side", "args")}
                if act["type"] == "aow_implement_card" and cand not in same_variants:
                    cid = act["args"].get("card_id")
                    act["args"] = sp._populate_event_args(s, cid, act["args"])
                try:
                    apply_action(s, act)
                    recovered = True
                    history.append({"step": step_n, "action": act,
                                    "outcome": "fallback"})
                    break
                except IllegalAction:
                    continue
            if not recovered:
                break

    final = {
        "scenario": scenario, "seed": seed, "history": history,
        "snapshots": snapshots,
        "terminal": sp._is_terminal(s),
        "final_box": s.meta.box,
        "final_t_vp": s.calendar.teutonic_vp,
        "final_r_vp": s.calendar.russian_vp,
        "final_t_mustered": [lid for lid, l in s.lords.items()
                              if l.side == "teutonic" and l.state == "mustered"],
        "final_r_mustered": [lid for lid, l in s.lords.items()
                              if l.side == "russian" and l.state == "mustered"],
    }
    if sp._is_terminal(s):
        try:
            final["winner"] = determine_scenario_winner(s)
        except Exception as e:
            final["winner_error"] = str(e)
    return final


def _summarize_result(result):
    if not isinstance(result, dict):
        return None
    # Pull the most informative fields
    keys = ["outcome", "winner", "loser", "added", "removed", "to",
            "ravaged_color", "battle", "conquest_change", "ransom",
            "siege_lifted", "no_op", "advanced", "game_over"]
    return {k: result[k] for k in keys if k in result}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario")
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    r = capture(args.scenario, args.seed)
    print(json.dumps(r, indent=2, default=str))


if __name__ == "__main__":
    sys.exit(main() or 0)
