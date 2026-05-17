"""Self-play driver with smart arg population.

Strategy:
  1. Pick highest-priority concrete move (legal_moves with args dict).
  2. For aow_implement_card events, populate event-specific args from
     current state.
  3. For templated moves (args_template + candidates), instantiate
     concrete args from candidates.
  4. Cycle through top moves to break ties; penalize repeated actions
     to avoid loops.

Used to surface integration bugs not caught by static probing.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import traceback
from collections import Counter
from typing import Any

from nevsky.actions import IllegalAction, apply_action
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import determine_scenario_winner, load_scenario
from nevsky.state import GameState
from nevsky.static_data import load_lords, load_locales


_ACTION_PRIORITY = {
    "advance_step": 100,
    "end_campaign_resolve": 100,
    "finalize_plan": 95,
    "command_reveal": 95,
    "end_card": 60,
    "fpd_resolve": 90,
    "stand_battle": 85,
    "avoid_battle": 70,
    "withdraw": 50,
    "aow_implement_card": 80,
    "muster_lord": 70,
    "muster_vassal": 65,
    "levy_capability": 60,
    "levy_transport": 55,
    "pay_with_coin": 75,
    "pay_with_loot": 70,
    "disband_resolve": 80,
    "cmd_pass": 40,
    "legate_skip": 80,
    "legate_arrives": 60,
    "legate_use": 50,
    "veche_action": 60,
    "aow_discard_this_levy": 70,
    "plan_add_card": 60,
    "cmd_march": 40,
    "cmd_tax": 35,
    "cmd_forage": 30,
    "cmd_supply": 25,
    "cmd_ravage": 25,
    "cmd_sail": 30,
    "cmd_siege": 35,
    "cmd_storm": 35,
    "cmd_sally": 35,
    "aow_draw": 35,
    "aow_shuffle": 5,
    "place_lieutenant": 10,
    "confirm_setup_transport": 100,
    "confirm_all_setup_transports": 100,
    "system_setup_complete": 100,
    "cmd_stone_kremlin": 30,
    "cmd_stonemasons": 30,
    "cmd_muster_serf": 30,
    "cmd_raiders_ravage": 25,
}


def _populate_event_args(state, cid, args):
    """Populate event-specific args for aow_implement_card. Resolves
    dynamic choices from current state."""
    new = dict(args)
    cal = state.calendar

    def cyl_on_cal(lid):
        if lid in cal.off_left or lid in cal.off_right:
            return True
        return any(lid in cb.cylinders for cb in cal.boxes)

    def service_on_cal(lid):
        if lid in cal.off_left_service or lid in cal.off_right_service:
            return True
        return any(lid in cb.service_markers for cb in cal.boxes)

    def first_on_calendar(lord_ids):
        for lid in lord_ids:
            if cyl_on_cal(lid):
                return lid
        return None

    def first_with_service(lord_ids):
        for lid in lord_ids:
            if service_on_cal(lid):
                return lid
        return None

    # T1 Grand Prince: prefer cylinder over service; pick whichever Lord
    # is actually on Calendar.
    if cid == "T1":
        if cyl_on_cal("andrey"):
            new.setdefault("target", "andrey")
        elif cyl_on_cal("aleksandr"):
            new.setdefault("target", "aleksandr")
        elif service_on_cal("andrey") and service_on_cal("aleksandr"):
            # Furthest right service (SMOKE-102): pick higher-box one.
            def sbox(lid):
                for cb in cal.boxes:
                    if lid in cb.service_markers:
                        return cb.box
                return 0
            if sbox("andrey") >= sbox("aleksandr"):
                new.setdefault("target", "service:andrey")
            else:
                new.setdefault("target", "service:aleksandr")
        elif service_on_cal("andrey"):
            new.setdefault("target", "service:andrey")
        elif service_on_cal("aleksandr"):
            new.setdefault("target", "service:aleksandr")
        new.setdefault("direction", "left")
    # T12 Khan Baty
    elif cid == "T12":
        if cyl_on_cal("andrey"):
            new.setdefault("target", "andrey")
        elif cyl_on_cal("aleksandr"):
            new.setdefault("target", "aleksandr")
        elif service_on_cal("andrey"):
            new.setdefault("target", "service:andrey")
        elif service_on_cal("aleksandr"):
            new.setdefault("target", "service:aleksandr")
        new.setdefault("direction", "left")
    elif cid == "T2":
        new.setdefault("target", "veche")
    elif cid == "T11":
        # Pick a Teutonic Lord with cylinder on Calendar
        for lid, l in state.lords.items():
            if l.side == "teutonic" and cyl_on_cal(lid):
                new.setdefault("target", lid)
                break
        else:
            new.setdefault("target", "andreas")
    elif cid == "T14":
        # Find a Russian-ravaged locale in Livonia/Estonia
        static = load_locales()
        for lid, loc in state.locales.items():
            if loc.russian_ravaged and static[lid].get("territory") in ("teutonic", "crusader"):
                new.setdefault("locale", lid)
                break
        else:
            # Fallback: any russian_ravaged locale
            for lid, loc in state.locales.items():
                if loc.russian_ravaged:
                    new.setdefault("locale", lid)
                    break
    elif cid == "R18":
        static = load_locales()
        for lid, loc in state.locales.items():
            if loc.teutonic_ravaged and static[lid].get("territory") == "russian":
                new.setdefault("locale", lid)
                break
        else:
            for lid, loc in state.locales.items():
                if loc.teutonic_ravaged:
                    new.setdefault("locale", lid)
                    break
    elif cid == "T15":
        # Russian-territory locale within 2 of ostrov, not ravaged, no Russian Lord/Stronghold
        from nevsky.static_data import load_ways
        static = load_locales()
        ways = load_ways()
        adj = {}
        for w in ways:
            adj.setdefault(w["a"], []).append(w["b"])
            adj.setdefault(w["b"], []).append(w["a"])
        visited = {"ostrov": 0}
        frontier = ["ostrov"]
        for d in range(1, 3):
            nxt = []
            for n in frontier:
                for m in adj.get(n, []):
                    if m not in visited:
                        visited[m] = d
                        nxt.append(m)
            frontier = nxt
        for lid in visited:
            if (lid in state.locales and static[lid].get("territory") == "russian"
                    and not state.locales[lid].russian_ravaged
                    and not state.locales[lid].teutonic_ravaged
                    and not any(l.side == "russian" and l.location == lid
                                for l in state.lords.values())):
                new.setdefault("locale", lid)
                break
        else:
            new.setdefault("locale", "ostrov")
    elif cid == "R12":
        # Mirror of T15 with rositten
        from nevsky.static_data import load_ways
        static = load_locales()
        ways = load_ways()
        adj = {}
        for w in ways:
            adj.setdefault(w["a"], []).append(w["b"])
            adj.setdefault(w["b"], []).append(w["a"])
        visited = {"rositten": 0}
        frontier = ["rositten"]
        for d in range(1, 3):
            nxt = []
            for n in frontier:
                for m in adj.get(n, []):
                    if m not in visited:
                        visited[m] = d
                        nxt.append(m)
            frontier = nxt
        for lid in visited:
            if (lid in state.locales
                    and static[lid].get("subregion") == "crusader_livonia"
                    and not state.locales[lid].russian_ravaged
                    and not state.locales[lid].teutonic_ravaged
                    and not any(l.side == "teutonic" and l.location == lid
                                for l in state.lords.values())):
                new.setdefault("locale", lid)
                break
    elif cid == "T18":
        new.setdefault("targets", {"vladislav": "cylinder", "karelians": "cylinder"})
        new.setdefault("direction", "right")
    elif cid == "R9":
        # Andreas or Heinrich; pick one whose Service is at >= 2
        cal = state.calendar
        def sbox(lid):
            for cb in cal.boxes:
                if lid in cb.service_markers:
                    return cb.box
            return None
        for target in ("andreas", "heinrich"):
            b = sbox(target)
            if b is not None and b >= 2:
                new.setdefault("target", target)
                break
        else:
            new.setdefault("target", "andreas")  # may raise; agent recovers
    elif cid == "R10":
        if cyl_on_cal("andreas"):
            new.setdefault("target", "andreas")
        elif service_on_cal("andreas"):
            new.setdefault("target", "service:andreas")
        else:
            new.setdefault("target", "andreas")  # may fail; agent recovers
        new.setdefault("direction", "left")
    elif cid == "R11":
        new.setdefault("target", "knud_and_abel")
        new.setdefault("direction", "left")
        new.setdefault("boxes", 1)
    elif cid == "R16":
        for lid, l in state.lords.items():
            if l.side == "teutonic" and l.state == "mustered":
                new.setdefault("target", lid)
                break
        else:
            new.setdefault("target", "andreas")
    elif cid == "R17":
        for tgt in ("andreas", "rudolf"):
            if cyl_on_cal(tgt):
                new.setdefault("target", tgt)
                break
        else:
            new.setdefault("target", "service:andreas")
        new.setdefault("direction", "left")
    return new


def _instantiate_templated_move(state, move):
    """Convert a templated move (args_template + candidates) into one
    or more concrete moves with `args` dict. Returns a list of
    candidate concrete moves; empty if none could be built."""
    out = []
    typ = move["type"]
    side = move.get("side")
    cands = move.get("candidates", {})
    if typ == "pay_with_coin":
        payers = cands.get("payers", [])
        targets = cands.get("targets", [])
        # Build all (payer, target) pairs, prioritizing self-pay (same Lord).
        for payer in payers:
            # Self-pay first (always legal: own Coin -> own Service).
            if payer != "veche" and payer in targets:
                out.append({"type": typ, "side": side,
                             "args": {"from": f"lord:{payer}",
                                      "target_lord": payer, "units": 1}})
        # Then co-located cross-pays
        for payer in payers:
            if payer == "veche":
                # Veche -> any non-besieged Russian Lord
                for target in targets:
                    out.append({"type": typ, "side": side,
                                 "args": {"from": "veche",
                                          "target_lord": target, "units": 1}})
            else:
                payer_loc = state.lords.get(payer)
                if payer_loc is None:
                    continue
                for target in targets:
                    if target == payer:
                        continue  # already added self-pay above
                    tgt_loc = state.lords.get(target)
                    if (tgt_loc is not None and tgt_loc.location is not None
                            and tgt_loc.location == payer_loc.location):
                        out.append({"type": typ, "side": side,
                                     "args": {"from": f"lord:{payer}",
                                              "target_lord": target, "units": 1}})
    elif typ == "pay_with_loot":
        payers = cands.get("payers", [])
        targets = cands.get("targets", [])
        # Self-pay first
        for payer in payers:
            if payer in targets:
                out.append({"type": typ, "side": side,
                             "args": {"from_lord": payer,
                                      "target_lord": payer, "units": 1}})
        # Then co-located cross-pays
        for payer in payers:
            payer_loc = state.lords.get(payer)
            if payer_loc is None:
                continue
            for target in targets:
                if target == payer:
                    continue
                tgt_loc = state.lords.get(target)
                if (tgt_loc is not None and tgt_loc.location is not None
                        and tgt_loc.location == payer_loc.location):
                    out.append({"type": typ, "side": side,
                                 "args": {"from_lord": payer,
                                          "target_lord": target, "units": 1}})
    return out


def _move_priority(move, recent_action_counts):
    p = _ACTION_PRIORITY.get(move["type"], 15)
    sig = (move["type"], move.get("side"),
           json.dumps(move.get("args", {}), default=str, sort_keys=True))
    rep = recent_action_counts.get(sig, 0)
    if rep >= 2:
        p -= 200
    return p


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
    last_box = None
    no_progress_count = 0

    for step_n in range(max_steps):
        if _is_terminal(s):
            break
        if s.meta.box != last_box:
            last_box = s.meta.box
            no_progress_count = 0
        moves_raw = legal_moves(s, with_previews=False)

        # Build a concrete-args list — include direct concrete moves
        # AND templated moves expanded.
        moves = []
        for m in moves_raw:
            if "args" in m and isinstance(m["args"], dict):
                moves.append(m)
            else:
                moves.extend(_instantiate_templated_move(s, m))

        if not moves:
            error = {"reason": "no_legal_moves", "step": step_n,
                     "phase": s.meta.phase,
                     "levy_step": s.meta.levy_step,
                     "campaign_step": s.meta.campaign_step,
                     "active_player": s.meta.active_player,
                     "active_lord": s.campaign_turn.active_lord,
                     "actions_remaining": s.campaign_turn.actions_remaining,
                     "raw_count": len(moves_raw),
                     "raw_sample": [m.get("type") for m in moves_raw[:5]]}
            break

        prioritized = sorted(moves, key=lambda m: -_move_priority(m, recent_action_counts))
        pick = prioritized[step_n % min(3, len(prioritized))]
        action = {k: v for k, v in pick.items() if k in ("type", "side", "args")}
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
            for cand in prioritized[1:20]:
                act = {k: v for k, v in cand.items() if k in ("type", "side", "args")}
                if act["type"] == "aow_implement_card":
                    cid = act["args"].get("card_id")
                    act["args"] = _populate_event_args(s, cid, act["args"])
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
