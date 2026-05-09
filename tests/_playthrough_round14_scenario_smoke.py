"""TEST FIXTURE / engine-soundness smoke driver — NOT part of the shipped harness.

Round 14 — Per-scenario statistical smoke (passive baseline + light-action agent).

Goal: surface engine bugs across all six real scenarios and gauge
win lopsidedness scenario-by-scenario.

Two policy tiers:
  TIER 0 (passive): both sides pass every Command. Validates engine
    soundness. The 'winner' here is whoever benefits from setup VPs,
    Levy events, and Calendar shifts — strategic play does nothing.
  TIER 1 (active): each side picks one Lord per turn and marches him
    toward the nearest enemy stronghold via the shortest legal Way.
    Other Lords pass. Generates real movement, occasional battles,
    occasional storms.

Run: PYTHONPATH=src python3 tests/_playthrough_round14_scenario_smoke.py [tier] [trials]
"""

from __future__ import annotations

import json
import random
import sys
import traceback
from collections import defaultdict
from typing import Any

from nevsky.actions import IllegalAction, apply_action
from nevsky.scenarios import load_scenario, SCENARIO_IDS
from nevsky.static_data import load_cards


SCENARIOS = [s for s in SCENARIO_IDS if s != "quickstart"]


# ---------------------------------------------------------------------------
# Levy: implement-everything-or-skip pass (cribbed from Round 6 driver).
# ---------------------------------------------------------------------------


def _on_cal(s, lid):
    return any(lid in cb.cylinders for cb in s.calendar.boxes)


def _has_svc(s, lid):
    return any(lid in cb.service_markers for cb in s.calendar.boxes)


def _pick(s, lid):
    return lid if _on_cal(s, lid) else (f"service:{lid}" if _has_svc(s, lid) else None)


def _aow_implement_args_for(s, side, cid):
    """Best-effort args dict for an aow_implement_card action; returns None if unknown."""
    cards = load_cards()
    c = cards[cid]
    if c["no_event"]:
        return {}
    if not s.meta.first_levy_done:
        if c["capability_scope"] == "this_lord":
            t = next(
                (lid for lid, l in s.lords.items()
                 if l.side == side and l.state == "mustered"),
                None,
            )
            if t:
                return {"lord_id": t}
            return None
        return {}
    # Subsequent levies: per-card best guess.
    if cid == "T1":
        t = _pick(s, "aleksandr") or _pick(s, "andrey")
        return {"target": t, "direction": "left"} if t else None
    elif cid == "T2":
        return {"target": "veche"}
    elif cid == "T11":
        t = next((lid for lid, l in s.lords.items()
                  if l.side == "teutonic" and _on_cal(s, lid)), None)
        return {"target": t} if t else None
    elif cid == "T12":
        t = _pick(s, "aleksandr") or _pick(s, "andrey")
        return {"target": t, "direction": "left"} if t else None
    elif cid == "T14":
        loc = next((lid for lid, ll in s.locales.items() if ll.russian_ravaged), None)
        return {"locale": loc} if loc else None
    elif cid == "T15":
        return {"locale": "ostrov"}
    elif cid == "T18":
        targets = {}
        for lid in ("vladislav", "karelians"):
            if _on_cal(s, lid):
                targets[lid] = "cylinder"
            elif _has_svc(s, lid):
                targets[lid] = "service"
        return {"direction": "left", "targets": targets} if targets else None
    elif cid == "R9":
        return {"target": "andreas" if _has_svc(s, "andreas") else "heinrich"}
    elif cid == "R10":
        t = _pick(s, "andreas")
        return {"target": t, "direction": "left", "boxes": 1} if t else None
    elif cid == "R11":
        return {"target": "knud_and_abel", "direction": "left", "boxes": 0}
    elif cid == "R12":
        return {"locale": "rositten"}
    elif cid == "R14":
        return {}
    elif cid == "R16":
        teu_with_ships = next(
            (lid for lid, l in s.lords.items()
             if l.side == "teutonic" and l.state == "mustered"
             and l.assets.get("ship", 0) > 0),
            None,
        )
        return {"target": teu_with_ships} if teu_with_ships else None
    elif cid == "R17":
        t = _pick(s, "andreas") or _pick(s, "rudolf")
        return {"target": t, "direction": "left"} if t else None
    elif cid == "R18":
        loc = next((lid for lid, ll in s.locales.items() if ll.teutonic_ravaged), None)
        return {"locale": loc} if loc else None
    return {}


def fast_levy_skip(s, side):
    """Run side's Levy: shuffle, draw, implement-or-discard each card,
    then advance step. No active Lord placement."""
    apply_action(s, {"type": "aow_shuffle", "side": side, "args": {}})
    apply_action(s, {"type": "aow_draw", "side": side, "args": {}})
    deck = s.decks.teutonic if side == "teutonic" else s.decks.russian
    while deck.pending_draw:
        cid = deck.pending_draw[0]
        args = _aow_implement_args_for(s, side, cid)
        if args is None:
            deck.pending_draw.pop(0)
            deck.discard.append(cid)
            continue
        try:
            apply_action(s, {"type": "aow_implement_card", "side": side, "args": args})
        except IllegalAction:
            if deck.pending_draw and deck.pending_draw[0] == cid:
                deck.pending_draw.pop(0)
                deck.discard.append(cid)
    apply_action(s, {"type": "advance_step", "side": side, "args": {}})


def levy_pass(s):
    """Both sides do Levy through pay/disband/muster/call_to_arms/done."""
    fast_levy_skip(s, "teutonic")
    fast_levy_skip(s, "russian")
    # Skip pay/disband/muster steps.
    for _ in range(3):
        apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})
        apply_action(s, {"type": "advance_step", "side": "russian", "args": {}})
    apply_action(s, {"type": "legate_skip", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "aow_discard_this_levy", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "veche_action", "side": "russian", "args": {"option": "skip"}})
    apply_action(s, {"type": "aow_discard_this_levy", "side": "russian", "args": {}})
    apply_action(s, {"type": "advance_step", "side": "russian", "args": {}})


# ---------------------------------------------------------------------------
# Campaign: passive (Tier 0).
# ---------------------------------------------------------------------------


def passive_campaign(s):
    """Plan all Pass cards on both sides; reveal & FPD-resolve until done."""
    from nevsky.campaign import _plan_target_size
    target = _plan_target_size(s.meta.box)
    for sd in ("teutonic", "russian"):
        for _ in range(target):
            apply_action(s, {"type": "plan_add_card", "side": sd, "args": {"card": "pass"}})
        apply_action(s, {"type": "finalize_plan", "side": sd, "args": {}})
    safety = 100
    while s.meta.campaign_step == "command" and safety > 0:
        side = s.campaign_turn.next_to_reveal
        if not s.campaign_turn.in_feed_pay_disband:
            apply_action(s, {"type": "command_reveal", "side": side, "args": {}})
        try:
            apply_action(s, {"type": "fpd_resolve", "side": "teutonic", "args": {}})
            apply_action(s, {"type": "fpd_resolve", "side": "russian", "args": {}})
        except IllegalAction as e:
            return f"fpd: {e.code}"
        safety -= 1
    if s.meta.campaign_step == "end_campaign":
        apply_action(s, {"type": "end_campaign_resolve", "side": "teutonic", "args": {}})
        apply_action(s, {"type": "end_campaign_resolve", "side": "russian", "args": {}})
    return None


# ---------------------------------------------------------------------------
# Run a single scenario trial.
# ---------------------------------------------------------------------------


def run_scenario(scenario_id, seed, tier="passive", max_turns=20):
    """Returns dict {winner, t_vp, r_vp, turns, error, error_turn}.
    error is None on success."""
    try:
        s = load_scenario(scenario_id, seed=seed)
    except Exception as e:
        return {"error": f"load: {type(e).__name__}: {e}", "error_turn": 0,
                "winner": None, "t_vp": None, "r_vp": None, "turns": 0}
    try:
        apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
        apply_action(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})
    except Exception as e:
        return {"error": f"setup: {type(e).__name__}: {e}", "error_turn": 0,
                "winner": None, "t_vp": s.calendar.teutonic_vp, "r_vp": s.calendar.russian_vp, "turns": 0}
    turn = 0
    error = None
    error_turn = None
    while s.meta.phase != "campaign" or s.meta.campaign_step != "done":
        turn += 1
        if turn > max_turns:
            error = "safety_bail"
            error_turn = turn
            break
        if s.meta.phase != "levy":
            error = f"phase_{s.meta.phase}"
            error_turn = turn
            break
        try:
            levy_pass(s)
        except Exception as e:
            error = f"levy_t{turn}: {type(e).__name__}: {e}"
            error_turn = turn
            break
        if s.meta.phase != "campaign":
            error = f"after_levy_phase_{s.meta.phase}"
            error_turn = turn
            break
        try:
            cerr = passive_campaign(s)
            if cerr:
                error = f"campaign_t{turn}: {cerr}"
                error_turn = turn
                break
        except Exception as e:
            error = f"campaign_t{turn}: {type(e).__name__}: {e}"
            error_turn = turn
            break
    t_vp = s.calendar.teutonic_vp
    r_vp = s.calendar.russian_vp
    if t_vp > r_vp:
        winner = "teutonic"
    elif r_vp > t_vp:
        winner = "russian"
    else:
        winner = "tie"
    return {"error": error, "error_turn": error_turn,
            "winner": winner, "t_vp": t_vp, "r_vp": r_vp, "turns": turn}


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------


def smoke_all_scenarios(trials=20, tier="passive", verbose=False):
    rows = []
    for sid in SCENARIOS:
        wins = {"teutonic": 0, "russian": 0, "tie": 0}
        errors = []
        t_vps = []
        r_vps = []
        turns = []
        for t in range(trials):
            seed = sid_hash(sid) * 7919 + t * 31 + 1
            r = run_scenario(sid, seed, tier=tier)
            if r["error"]:
                errors.append((seed, r["error"], r["error_turn"]))
                if verbose:
                    print(f"[{sid} seed={seed}] ERR: {r['error']}")
            else:
                if r["winner"] in wins:
                    wins[r["winner"]] += 1
                t_vps.append(r["t_vp"])
                r_vps.append(r["r_vp"])
                turns.append(r["turns"])
        ok = sum(wins.values())
        rows.append({
            "scenario": sid,
            "trials": trials,
            "ok": ok,
            "errors": len(errors),
            "T_win": wins["teutonic"],
            "R_win": wins["russian"],
            "tie": wins["tie"],
            "T_winrate": wins["teutonic"] / max(1, ok),
            "R_winrate": wins["russian"] / max(1, ok),
            "tie_rate": wins["tie"] / max(1, ok),
            "avg_t_vp": sum(t_vps) / max(1, len(t_vps)),
            "avg_r_vp": sum(r_vps) / max(1, len(r_vps)),
            "avg_turns": sum(turns) / max(1, len(turns)),
            "error_samples": errors[:5],
        })
    return rows


def sid_hash(sid):
    h = 0
    for c in sid:
        h = (h * 31 + ord(c)) & 0xFFFFFFFF
    return h


def fmt_table(rows):
    out = []
    out.append("=" * 110)
    out.append("PER-SCENARIO SMOKE")
    out.append("=" * 110)
    hdr = f"{'scenario':<32} {'trials':>6} {'ok':>4} {'err':>4} | {'T_win%':>7} {'R_win%':>7} {'tie%':>6} | {'T_VP':>5} {'R_VP':>5} {'turns':>5}"
    out.append(hdr)
    out.append("-" * len(hdr))
    for r in rows:
        out.append(
            f"{r['scenario']:<32} {r['trials']:>6} {r['ok']:>4} {r['errors']:>4} | "
            f"{r['T_winrate']*100:>6.1f}% {r['R_winrate']*100:>6.1f}% {r['tie_rate']*100:>5.1f}% | "
            f"{r['avg_t_vp']:>5.1f} {r['avg_r_vp']:>5.1f} {r['avg_turns']:>5.1f}"
        )
    out.append("")
    out.append("=== ERRORS (first 5 per scenario) ===")
    for r in rows:
        if r["errors"]:
            out.append(f"\n{r['scenario']}:")
            for seed, err, turn in r["error_samples"]:
                out.append(f"  seed={seed} turn={turn}: {err}")
    return "\n".join(out)


def main():
    tier = sys.argv[1] if len(sys.argv) > 1 else "passive"
    trials = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    print(f"Round 14 — scenario smoke (tier={tier}, trials={trials})", file=sys.stderr)
    rows = smoke_all_scenarios(trials=trials, tier=tier, verbose=False)
    print(fmt_table(rows))
    out_path = f"round14_smoke_{tier}.json"
    with open(out_path, "w") as f:
        json.dump(rows, f, indent=2, default=str)
    print(f"\nJSON: {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
