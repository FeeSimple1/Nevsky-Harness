"""Self-play driver — loads a scenario, queries legal_moves, picks
the highest-priority action, applies it, repeats until game_over.
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from collections import Counter
from typing import Any

from nevsky.actions import IllegalAction, apply_action
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import determine_scenario_winner, load_scenario
from nevsky.state import GameState


_ACTION_PRIORITY = {
    "advance_step": 100,
    "end_campaign_resolve": 100,
    "finalize_plan": 95,
    "command_reveal": 95,
    "end_card": 90,
    "fpd_resolve": 90,
    "stand_battle": 85,
    "avoid_battle": 75,
    "withdraw": 70,
    "aow_implement_card": 80,
    "muster_lord": 70,
    "muster_vassal": 65,
    "levy_capability": 60,
    "levy_transport": 55,
    "pay_with_coin": 50,
    "pay_with_loot": 45,
    "disband_resolve": 80,
    "cmd_pass": 40,
    "legate_skip": 80,
    "veche_action": 60,
    "aow_discard_this_levy": 70,
    "plan_add_card": 60,
    "cmd_march": 30,
    "cmd_tax": 25,
    "cmd_forage": 25,
    "cmd_supply": 20,
    "cmd_ravage": 20,
    "cmd_sail": 25,
    "cmd_siege": 30,
    "cmd_storm": 30,
    "cmd_sally": 30,
    "aow_draw": 35,
    "aow_shuffle": 5,
    "place_lieutenant": 10,
    "confirm_setup_transport": 100,
    "confirm_all_setup_transports": 100,
    "system_setup_complete": 100,
}


def _move_priority(move, recent_action_counts):
    p = _ACTION_PRIORITY.get(move["type"], 15)
    sig = (move["type"], move.get("side"),
           json.dumps(move.get("args", {}), default=str, sort_keys=True))
    rep = recent_action_counts.get(sig, 0)
    if rep >= 2:
        p -= 200
    return p


def _populate_event_args(state, cid, args):
    """Populate event-specific args for aow_implement_card when the
    card is being implemented as an event (subsequent Levy). Returns
    a new args dict with defaults filled in for known events.

    Conservative defaults that satisfy the event resolver's input
    validation. If the resolver still raises (e.g., 'too_far' for
    Mindaugas), the agent's IllegalAction fallback kicks in.
    """
    new = dict(args)
    # T1, T12: shift Aleksandr or Andrey cylinder (default andrey)
    if cid in ("T1", "T12"):
        new.setdefault("target", "andrey")
        new.setdefault("direction", "left")
    # T2 Torzhok: pick Veche (safer fallback than empty Domash)
    elif cid == "T2":
        new.setdefault("target", "veche")
    # T11 Pope Gregory: first mustered T Lord on Calendar
    elif cid == "T11":
        for lid, l in state.lords.items():
            if l.side == "teutonic" and l.state in ("mustered", "ready"):
                new.setdefault("target", lid)
                break
        else:
            new.setdefault("target", "andreas")
    # T14 / R18 Bountiful Harvest: locale with appropriate ravaged
    elif cid == "T14":
        for lid, loc in state.locales.items():
            if loc.russian_ravaged:
                new.setdefault("locale", lid)
                break
        else:
            new.setdefault("locale", "warbola")  # bishopric/town fallback
    elif cid == "R18":
        for lid, loc in state.locales.items():
            if loc.teutonic_ravaged:
                new.setdefault("locale", lid)
                break
        else:
            new.setdefault("locale", "novgorod")
    # T15 Mindaugas T: a Russian-territory locale near ostrov
    elif cid == "T15":
        new.setdefault("locale", "ostrov")
    # R12 Mindaugas R: a Livonian locale near rositten
    elif cid == "R12":
        new.setdefault("locale", "rositten")
    # T18 Swedish Crusade: shift vladislav AND karelians
    elif cid == "T18":
        new.setdefault("targets", {"vladislav": "cylinder", "karelians": "cylinder"})
        new.setdefault("direction", "right")
    # R9 Osilian Revolt: pick andreas
    elif cid == "R9":
        new.setdefault("target", "andreas")
    # R10 Batu Khan — target andreas cylinder if on Calendar, else service
    elif cid == "R10":
        cyl_on_cal = any("andreas" in cb.cylinders for cb in state.calendar.boxes) \
                     or "andreas" in state.calendar.off_left \
                     or "andreas" in state.calendar.off_right
        new.setdefault("target", "andreas" if cyl_on_cal else "service:andreas")
        new.setdefault("direction", "left")
    # R11 Valdemar
    elif cid == "R11":
        new.setdefault("target", "knud_and_abel")
        new.setdefault("direction", "left")
        new.setdefault("boxes", 1)
    # R14 Prussian Revolt
    elif cid == "R14":
        pass  # no required args
    # R15 Death of Pope - no required args
    elif cid == "R15":
        pass
    # R16 Tempest: first teutonic mustered Lord
    elif cid == "R16":
        for lid, l in state.lords.items():
            if l.side == "teutonic" and l.state == "mustered":
                new.setdefault("target", lid)
                break
        else:
            new.setdefault("target", "andreas")
    # R17 Dietrich R
    elif cid == "R17":
        new.setdefault("target", "andreas")
        new.setdefault("direction", "left")
    return new


def _is_terminal(s):
    return s.meta.phase == "campaign" and s.meta.campaign_step == "done"


def step_self_play(scenario, seed=0, max_steps=10000, verbose=False):
    s = load_scenario(scenario, seed=seed)
    for side in ("teutonic", "russian"):
        try:
            apply_action(s, {"type": "confirm_all_setup_transports",
                              "side": side, "args": {}})
        except Exception:
            pass
    history = []
    recent_action_counts = Counter()
    error = None
    for step_n in range(max_steps):
        if _is_terminal(s):
            break
        moves_raw = legal_moves(s, with_previews=False)
        # Skip moves with no concrete `args` (templated like
        # pay_with_coin which uses args_template + candidates).
        moves = [m for m in moves_raw if "args" in m and isinstance(m["args"], dict)]
        if not moves:
            error = {"reason": "no_legal_moves", "step": step_n,
                     "phase": s.meta.phase,
                     "levy_step": s.meta.levy_step,
                     "campaign_step": s.meta.campaign_step,
                     "active_player": s.meta.active_player,
                     "active_lord": s.campaign_turn.active_lord,
                     "actions_remaining": s.campaign_turn.actions_remaining}
            break
        prioritized = sorted(moves, key=lambda m: -_move_priority(m, recent_action_counts))
        pick = prioritized[step_n % min(3, len(prioritized))]
        action = {k: v for k, v in pick.items() if k in ("type", "side", "args")}
        # Populate event args for aow_implement_card (legal_moves only
        # supplies card_id; event resolvers need event-specific args).
        if action["type"] == "aow_implement_card":
            cid = action["args"].get("card_id")
            action["args"] = _populate_event_args(s, cid, action["args"])
        sig = (action["type"], action.get("side"),
               json.dumps(action.get("args", {}), default=str, sort_keys=True))
        recent_action_counts[sig] += 1
        if step_n % 50 == 0 and step_n > 0:
            recent_action_counts.clear()
        try:
            result = apply_action(s, action)
            history.append({"step": step_n, "action": action})
            if verbose and step_n < 50:
                print(f"  step {step_n}: {action['type']} side={action.get('side')}")
            if isinstance(result, dict) and result.get("game_over"):
                break
        except IllegalAction as e:
            recovered = False
            for cand in prioritized[1:10]:
                act = {k: v for k, v in cand.items() if k in ("type", "side", "args")}
                try:
                    apply_action(s, act)
                    history.append({"step": step_n, "action": act, "fallback": True})
                    recovered = True
                    break
                except IllegalAction:
                    continue
            if not recovered:
                error = {"reason": "illegal_action", "step": step_n,
                         "action": action,
                         "error_code": getattr(e, "code", None),
                         "error_msg": str(e)[:300]}
                break
        except Exception as e:
            error = {"reason": "exception", "step": step_n, "action": action,
                     "exception_type": type(e).__name__,
                     "exception_msg": str(e)[:300],
                     "traceback_excerpt": traceback.format_exc()[-1500:]}
            break
    final = {
        "scenario": scenario, "seed": seed,
        "steps_taken": len(history),
        "terminal": _is_terminal(s),
        "phase": s.meta.phase,
        "campaign_step": s.meta.campaign_step,
        "box": s.meta.box,
        "russian_vp": s.calendar.russian_vp,
        "teutonic_vp": s.calendar.teutonic_vp,
        "russian_mustered": sum(1 for l in s.lords.values()
                                  if l.side == "russian" and l.state == "mustered"),
        "teutonic_mustered": sum(1 for l in s.lords.values()
                                  if l.side == "teutonic" and l.state == "mustered"),
        "error": error,
    }
    if _is_terminal(s):
        try:
            final["winner"] = determine_scenario_winner(s)
        except Exception as e:
            final["winner_error"] = str(e)
    return final


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-steps", type=int, default=10000)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    result = step_self_play(args.scenario, args.seed, args.max_steps, args.verbose)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("error") is None else 1


if __name__ == "__main__":
    sys.exit(main())
