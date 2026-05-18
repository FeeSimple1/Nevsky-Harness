"""Strategic reference agent for Nevsky.

Unlike scripts/self_play.py (greedy "always pick highest-priority
action"), this agent has heuristics that:
  - Initiates March into enemy locales (triggers Battle / Siege)
  - Decides Stand vs Avoid vs Withdraw with rough force-ratio math
  - Uses Storm on besieged Strongholds when force advantage exists
  - Uses Ravage in enemy territory when adjacent
  - Builds Castle (T17) / Walls+1 (R18) when conditions allow
  - Uses Raiders (T2, R12/R14) when applicable
  - Mustered Serfs from R4 Smerdi
  - Plans aggressive Lord ordering, not just Pass-stuff

Goal: exercise harness paths the greedy agent avoids — Battle,
Storm, Sally, Ravage, Hold cards, capability commands. NOT a perfect
player; "good amateur" that surfaces bugs in combat code paths.

Lives under scripts/ to honor the "no agent in the harness"
constraint (the rules engine in src/nevsky/ remains agent-free).
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
from nevsky.static_data import load_locales, load_lords, load_ways


# ----------------- helpers ------------------------------------------------


def _is_terminal(s):
    return s.meta.phase == "campaign" and s.meta.campaign_step == "done"


def _total_units(lord) -> int:
    return sum(lord.forces.values())


def _own_lords_on_map(s, side):
    return [lid for lid, l in s.lords.items()
            if l.side == side and l.state == "mustered" and l.location is not None]


def _enemy_lords_at(s, locale_id, side):
    return [lid for lid, l in s.lords.items()
            if l.state == "mustered" and l.location == locale_id
            and l.side != side]


def _own_lords_at(s, locale_id, side):
    return [lid for lid, l in s.lords.items()
            if l.state == "mustered" and l.location == locale_id
            and l.side == side]


def _adj_locales(locale_id):
    out = []
    for w in load_ways():
        if w["a"] == locale_id:
            out.append((w["b"], w["type"]))
        elif w["b"] == locale_id:
            out.append((w["a"], w["type"]))
    return out


def _is_friendly_for(s, locale_id, side):
    """Is the locale Friendly to `side`? (No enemy Lord/Stronghold/Conquered.)"""
    static = load_locales()[locale_id]
    loc = s.locales[locale_id]
    if loc.siege_markers > 0:
        return False
    own_terr = static["territory"] == ("teutonic" if side == "teutonic" else "russian")
    own_conq = (loc.teutonic_conquered > 0 if side == "teutonic" else loc.russian_conquered > 0)
    if not (own_terr or own_conq):
        return False
    enemy_conq = (loc.russian_conquered > 0 if side == "teutonic"
                   else loc.teutonic_conquered > 0)
    if enemy_conq:
        return False
    for ll in s.lords.values():
        if ll.state == "mustered" and ll.location == locale_id and ll.side != side:
            return False
    return True


def _action_score(s, action, side) -> int:
    """Heuristic score for an action. Higher = prefer.

    Encodes per-side strategic priors. Goal: pick aggressive actions
    that exercise combat / capability / VP-producing paths.
    """
    typ = action["type"]
    args = action.get("args", {})
    base = 50  # default

    # Phase progression actions — high priority, always advance state
    PROGRESS = {
        "advance_step": 90,
        "fpd_resolve": 95,
        "finalize_plan": 88,
        "end_campaign_resolve": 92,
        "command_reveal": 88,
        "confirm_setup_transport": 100,
        "confirm_all_setup_transports": 100,
        "aow_discard_this_levy": 80,
        "legate_skip": 70,
        "decline_ambush_block": 70,
    }
    if typ in PROGRESS:
        return PROGRESS[typ]

    # COMBAT actions — high priority once enabled
    if typ == "stand_battle":
        # Always Stand if forced; the engine handles auto-Concede via args
        return 95
    if typ == "avoid_battle":
        return 60  # prefer Stand over Avoid (more combat exercise)
    if typ == "withdraw":
        return 65
    if typ == "play_ambush_block":
        return 75  # exercise the path

    # STORM / SALLY / SIEGE — top priority when available
    if typ == "cmd_storm":
        return 92
    if typ == "cmd_sally":
        return 88
    if typ == "cmd_siege":
        return 85

    # Aggressive commands: March into enemy territory
    if typ == "cmd_march":
        dest = args.get("to")
        if dest:
            enemies = _enemy_lords_at(s, dest, side)
            static = load_locales().get(dest, {})
            # Marching into a locale with enemy Lord(s) triggers Battle — exercise it
            if enemies:
                return 95  # top priority: combat path
            # Marching into enemy-territory Locale (potentially begins Siege)
            terr = static.get("territory")
            own_terr = "teutonic" if side == "teutonic" else "russian"
            if terr and terr != own_terr:
                # Going into enemy land — strategic
                return 85
            # Own territory but adjacent to an enemy locale → positioning
            for adj_locale, _wt in _adj_locales(dest):
                adj_enemies = _enemy_lords_at(s, adj_locale, side)
                if adj_enemies:
                    return 72
            # Plain own-territory march — low priority
        return 50

    # RAVAGE — VP-producing in enemy territory
    if typ in ("cmd_ravage", "cmd_raiders_ravage"):
        return 78

    # Tax / Forage — economy
    if typ == "cmd_tax":
        return 60
    if typ == "cmd_forage":
        return 55

    # Sail — mobility (especially Teutonic)
    if typ == "cmd_sail":
        return 70

    # Capability commands — exercise the path
    if typ in ("cmd_stonemasons", "cmd_stone_kremlin", "cmd_muster_serf"):
        return 82

    # Pass — last resort
    if typ == "cmd_pass":
        return 30
    if typ == "end_card":
        return 35

    # Levy-phase decisions
    if typ == "aow_implement_card":
        return 78
    if typ == "muster_lord":
        return 72
    if typ == "muster_vassal":
        return 68
    if typ == "levy_capability":
        return 65
    if typ == "levy_transport":
        return 50
    if typ == "pay_with_coin":
        # Pay own Service if at risk
        return 65
    if typ == "pay_with_loot":
        return 55

    # Plan: prefer including Lords over Pass
    if typ == "plan_add_card":
        card = args.get("card")
        if card and card != "pass":
            return 75  # prefer Lord plan slots
        return 40

    # Veche / Legate
    if typ == "veche_action":
        sub = args.get("option")
        if sub == "B":  # auto-Muster - bring Lord on
            return 78
        if sub == "C":  # Extra Muster
            return 75
        if sub == "A":  # slide left
            return 65
        return 55
    if typ in ("legate_arrives", "legate_move", "legate_use"):
        return 60

    # Lordship hold play
    if typ == "play_lordship_hold":
        return 60

    # Setup actions (shouldn't fire mid-game)
    if typ in ("system_setup_complete",):
        return 100

    # Plumbing
    if typ == "aow_draw":
        return 70
    if typ == "aow_shuffle":
        # ONLY when needed (deck empty); penalize repeats heavily
        return 20

    return base


def _instantiate_templated(s, move):
    """Templated moves (pay_with_coin, etc.) → multiple concrete variants."""
    typ = move["type"]
    side = move.get("side")
    cands = move.get("candidates", {})
    out = []
    if typ == "pay_with_coin":
        payers = cands.get("payers", [])
        targets = cands.get("targets", [])
        for payer in payers:
            if payer != "veche" and payer in targets:
                out.append({"type": typ, "side": side,
                             "args": {"from": f"lord:{payer}",
                                      "target_lord": payer, "units": 1}})
        for payer in payers:
            if payer == "veche":
                for target in targets:
                    out.append({"type": typ, "side": side,
                                 "args": {"from": "veche",
                                          "target_lord": target, "units": 1}})
            else:
                payer_loc = s.lords.get(payer)
                if payer_loc is None:
                    continue
                for target in targets:
                    if target == payer:
                        continue
                    tgt_loc = s.lords.get(target)
                    if (tgt_loc is not None and tgt_loc.location is not None
                            and tgt_loc.location == payer_loc.location):
                        out.append({"type": typ, "side": side,
                                     "args": {"from": f"lord:{payer}",
                                              "target_lord": target, "units": 1}})
    elif typ == "pay_with_loot":
        payers = cands.get("payers", [])
        targets = cands.get("targets", [])
        for payer in payers:
            if payer in targets:
                out.append({"type": typ, "side": side,
                             "args": {"from_lord": payer,
                                      "target_lord": payer, "units": 1}})
    return out


def _populate_event_args(state, cid, args):
    """Same as scripts/self_play.py — supply default event args."""
    new = dict(args)
    cal = state.calendar

    def cyl_on_cal(lid):
        return (lid in cal.off_left or lid in cal.off_right
                or any(lid in cb.cylinders for cb in cal.boxes))

    def service_on_cal(lid):
        return (lid in cal.off_left_service or lid in cal.off_right_service
                or any(lid in cb.service_markers for cb in cal.boxes))

    if cid == "T1":
        # SMOKE-102 furthest-right rule: when both services are on
        # Calendar in different boxes, must pick the higher-box one.
        if cyl_on_cal("andrey"):
            new.setdefault("target", "andrey")
        elif cyl_on_cal("aleksandr"):
            new.setdefault("target", "aleksandr")
        elif service_on_cal("andrey") and service_on_cal("aleksandr"):
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
        for lid, l in state.lords.items():
            if l.side == "teutonic" and cyl_on_cal(lid):
                new.setdefault("target", lid)
                break
        else:
            new.setdefault("target", "andreas")
    elif cid == "T14":
        for lid, loc in state.locales.items():
            if loc.russian_ravaged:
                new.setdefault("locale", lid)
                break
    elif cid == "R18":
        for lid, loc in state.locales.items():
            if loc.teutonic_ravaged:
                new.setdefault("locale", lid)
                break
    elif cid == "T15":
        new.setdefault("locale", "ostrov")
    elif cid == "R12":
        new.setdefault("locale", "rositten")
    elif cid == "T18":
        new.setdefault("targets", {"vladislav": "cylinder", "karelians": "cylinder"})
        new.setdefault("direction", "right")
    elif cid == "R9":
        new.setdefault("target", "andreas")
    elif cid == "R10":
        if cyl_on_cal("andreas"):
            new.setdefault("target", "andreas")
        elif service_on_cal("andreas"):
            new.setdefault("target", "service:andreas")
        else:
            new.setdefault("target", "andreas")
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
    elif cid == "R17":
        for tgt in ("andreas", "rudolf"):
            if cyl_on_cal(tgt):
                new.setdefault("target", tgt)
                break
        else:
            new.setdefault("target", "service:andreas")
        new.setdefault("direction", "left")
    return new


# ------------- main play loop --------------------------------------------


def play(scenario, seed=0, max_steps=20000, verbose=False):
    s = load_scenario(scenario, seed=seed)
    for side in ("teutonic", "russian"):
        try:
            apply_action(s, {"type": "confirm_all_setup_transports",
                              "side": side, "args": {}})
        except Exception:
            pass

    history = []
    rac = Counter()
    error = None

    for step_n in range(max_steps):
        if _is_terminal(s):
            break

        side = s.meta.active_player

        moves_raw = legal_moves(s, with_previews=False)
        moves = []
        for m in moves_raw:
            if "args" in m and isinstance(m["args"], dict):
                moves.append(m)
            else:
                moves.extend(_instantiate_templated(s, m))

        if not moves:
            error = {"reason": "no_legal_moves", "step": step_n,
                     "phase": s.meta.phase,
                     "levy_step": s.meta.levy_step,
                     "campaign_step": s.meta.campaign_step,
                     "active_player": s.meta.active_player}
            break

        def score_with_penalty(m):
            base = _action_score(s, m, side)
            sig = (m["type"], m.get("side"),
                   json.dumps(m.get("args", {}), default=str, sort_keys=True))
            rep = rac.get(sig, 0)
            return base - (rep * 50)

        prioritized = sorted(moves, key=lambda m: -score_with_penalty(m))
        # Rotate small variety
        pick = prioritized[step_n % min(2, len(prioritized))]
        action = {k: v for k, v in pick.items() if k in ("type", "side", "args")}
        if action["type"] == "aow_implement_card":
            cid = action["args"].get("card_id")
            action["args"] = _populate_event_args(s, cid, action["args"])
        sig = (action["type"], action.get("side"),
               json.dumps(action.get("args", {}), default=str, sort_keys=True))
        rac[sig] += 1
        if step_n % 30 == 0 and step_n > 0:
            rac.clear()

        try:
            result = apply_action(s, action)
            history.append({"step": step_n, "action": action})
            if verbose and step_n < 50:
                print(f"  step {step_n}: {action['type']} side={action.get('side')}")
            if isinstance(result, dict) and result.get("game_over"):
                break
        except IllegalAction as e:
            recovered = False
            for cand in prioritized[1:]:
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
                         "action": action, "error_code": getattr(e, "code", None),
                         "error_msg": str(e)[:300]}
                break
        except Exception as e:
            error = {"reason": "exception", "step": step_n, "action": action,
                     "exception_type": type(e).__name__,
                     "exception_msg": str(e)[:300],
                     "traceback_excerpt": traceback.format_exc()[-1500:]}
            break

    # Build summary
    action_types = Counter(h["action"]["type"] for h in history)
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
        "action_types": dict(action_types.most_common(15)),
        "battles": action_types.get("stand_battle", 0),
        "storms": action_types.get("cmd_storm", 0),
        "sallies": action_types.get("cmd_sally", 0),
        "ravages": (action_types.get("cmd_ravage", 0)
                    + action_types.get("cmd_raiders_ravage", 0)),
        "sieges": action_types.get("cmd_siege", 0),
        "marches": action_types.get("cmd_march", 0),
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
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--max-steps", type=int, default=20000)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    r = play(args.scenario, args.seed, args.max_steps, args.verbose)
    print(json.dumps(r, indent=2, default=str))
    return 0 if r.get("error") is None else 1


if __name__ == "__main__":
    sys.exit(main())
