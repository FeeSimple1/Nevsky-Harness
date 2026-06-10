#!/usr/bin/env python3
"""Targeted subsystem fuzzers for the Nevsky harness.

Where scripts/fuzz_invariants.py drives whole self-play games, this module
hammers individual subsystems with far more variety than reachable self-play
produces, auditing every result against the shared check_invariants (I1-I12):

  * fuzz_combat        -- randomized Storms, Sallies and Battles (random
                          forces, garrison, walls, siege markers, concede,
                          withdraw), including a fraction rigged so the acting
                          side's last Lord is at stake (Rule 5.2 interplay).
  * fuzz_aow_events    -- implement every Arts-of-War Event card (T1-T18,
                          R1-R18) with a populated target AND bare (the
                          no-target reveal-and-discard fallback).
  * fuzz_veche         -- drive self-play to Russian Call-to-Arms states and
                          exercise every enumerated Veche option on a clone.

Each fuzzer returns a list of violation strings (empty == clean). The CLI runs
all three and exits non-zero on any violation (CI-friendly).

    python scripts/fuzz_subsystems.py
    python scripts/fuzz_subsystems.py --combat 800 --seeds 1-12
"""
from __future__ import annotations

import argparse
import importlib.util
import random
import sys
import traceback
from collections import Counter
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SRC = _REPO / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import nevsky.actions  # noqa: F401,E402  (establish import order)
from nevsky.scenarios import determine_scenario_winner, load_scenario  # noqa: E402
from nevsky.actions import apply_action, IllegalAction  # noqa: E402
from nevsky.legal_moves import legal_moves  # noqa: E402
from nevsky.state import CombatPending  # noqa: E402
from nevsky.static_data import load_lords  # noqa: E402

# Reuse the canonical audit and the self-play move helpers from fuzz_invariants.
_fi_spec = importlib.util.spec_from_file_location(
    "_nevsky_fuzz_invariants", str(Path(__file__).resolve().parent / "fuzz_invariants.py"))
_fi = importlib.util.module_from_spec(_fi_spec)
_fi_spec.loader.exec_module(_fi)  # type: ignore[union-attr]
check_invariants = _fi.check_invariants
sp = _fi.sp

SCENARIOS = ("crusade_on_novgorod", "watland", "pleskau")
TEU_UNITS = ["knights", "sergeants", "men_at_arms", "militia"]
RUS_UNITS = ["militia", "men_at_arms", "light_horse", "asiatic_horse", "serfs"]
TEU_SH = ["reval", "dorpat", "odenpah", "riga", "fellin", "wenden"]
RUS_SH = ["pskov", "novgorod", "ladoga", "izborsk", "koporye", "rusa"]


def _clone(s):
    return s.model_copy(deep=True)


def _rforces(rnd, units, hi=6):
    n = rnd.randint(1, 3)
    return {u: rnd.randint(1, hi) for u in rnd.sample(units, n)}


def _lords(s, side):
    return [lid for lid, l in s.lords.items() if l.side == side]


def _cmd_ctx(s, side, lord):
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = side
    s.campaign_turn.next_to_reveal = side
    s.campaign_turn.active_card = lord
    s.campaign_turn.active_lord = lord
    s.campaign_turn.in_feed_pay_disband = False
    s.lords[lord].moved_fought = False
    s.campaign_turn.actions_remaining = max(1, int(load_lords()[lord]["ratings"]["command"]))


# --------------------------------------------------------------------------
# Combat
# --------------------------------------------------------------------------
def _setup_storm(s, rnd):
    atk = rnd.choice(["teutonic", "russian"]); dfn = "russian" if atk == "teutonic" else "teutonic"
    loc = rnd.choice(RUS_SH if dfn == "russian" else TEU_SH)
    al = _lords(s, atk)[0]; dl = _lords(s, dfn)[0]
    s.lords[al].state = "mustered"; s.lords[al].location = loc; s.lords[al].in_stronghold = False
    s.lords[al].forces = _rforces(rnd, TEU_UNITS if atk == "teutonic" else RUS_UNITS)
    s.lords[dl].state = "mustered"; s.lords[dl].location = loc; s.lords[dl].in_stronghold = True
    s.lords[dl].forces = _rforces(rnd, TEU_UNITS if dfn == "teutonic" else RUS_UNITS)
    s.locales[loc].siege_markers = rnd.randint(1, 3)
    if rnd.random() < 0.3:
        s.locales[loc].walls_plus_one = True
    _cmd_ctx(s, atk, al)
    args = {"lord_id": al}
    if rnd.random() < 0.4:
        args["concede"] = rnd.choice([True, 1, 2])
    return {"type": "cmd_storm", "side": atk, "args": args}, atk, al


def _setup_sally(s, rnd):
    bes = rnd.choice(["teutonic", "russian"]); enemy = "russian" if bes == "teutonic" else "teutonic"
    loc = rnd.choice(TEU_SH if bes == "teutonic" else RUS_SH)
    bl = _lords(s, bes)[0]; el = _lords(s, enemy)[0]
    s.lords[bl].state = "mustered"; s.lords[bl].location = loc; s.lords[bl].in_stronghold = True
    s.lords[bl].forces = _rforces(rnd, TEU_UNITS if bes == "teutonic" else RUS_UNITS)
    s.lords[el].state = "mustered"; s.lords[el].location = loc; s.lords[el].in_stronghold = False
    s.lords[el].forces = _rforces(rnd, TEU_UNITS if enemy == "teutonic" else RUS_UNITS)
    s.locales[loc].siege_markers = rnd.randint(1, 4)
    _cmd_ctx(s, bes, bl)
    args = {"lord_id": bl}
    if rnd.random() < 0.4:
        args["concede"] = rnd.choice([True, 1, 2])
    return {"type": "cmd_sally", "side": bes, "args": args}, bes, bl


def _setup_battle(s, rnd):
    atk = rnd.choice(["teutonic", "russian"]); dfn = "russian" if atk == "teutonic" else "teutonic"
    loc = rnd.choice(RUS_SH + TEU_SH)
    al = _lords(s, atk)[0]; dl = _lords(s, dfn)[0]
    for lid, side in ((al, atk), (dl, dfn)):
        s.lords[lid].state = "mustered"; s.lords[lid].location = loc; s.lords[lid].in_stronghold = False
        s.lords[lid].forces = _rforces(rnd, TEU_UNITS if side == "teutonic" else RUS_UNITS)
    s.meta.phase = "campaign"; s.meta.campaign_step = "command"; s.meta.active_player = dfn
    s.combat_pending = CombatPending(
        attacker_side=atk, attacker_group=[al],
        from_locale="dorpat" if loc != "dorpat" else "odenpah",
        to_locale=loc, way_type="trackway", defender_side=dfn,
        defender_lords=[dl], pending_response_by=dfn, laden=False)
    args = {}
    if rnd.random() < 0.35:
        args["concede"] = "defender"
    if rnd.random() < 0.5:
        args["withdraw_losers"] = True
    return {"type": "stand_battle", "side": dfn, "args": args}, dfn, dl


def fuzz_combat(iters=500, seed_base=0):
    issues = []
    for i in range(iters):
        rnd = random.Random((i + seed_base) * 2654435761 % (2 ** 31))
        kind = rnd.choice(["storm", "sally", "battle"])
        s = load_scenario(rnd.choice(SCENARIOS), seed=rnd.randint(1, 99))
        force52 = rnd.random() < 0.25
        try:
            if kind == "storm":
                act, actor, keep = _setup_storm(s, rnd)
            elif kind == "sally":
                act, actor, keep = _setup_sally(s, rnd)
            else:
                act, actor, keep = _setup_battle(s, rnd)
            if force52:  # leave the combatant as the side's only Mustered Lord
                for lid, l in s.lords.items():
                    if l.side == actor and l.state == "mustered" and lid != keep:
                        l.state = "disbanded"
            apply_action(s, act)
        except IllegalAction:
            continue  # illegal setup (e.g. no_storm locale) -- skip
        except Exception as e:
            issues.append(f"combat#{i} {kind} EXCEPTION {e!r} :: "
                          + " | ".join(traceback.format_exc().splitlines()[-2:]))
            continue
        try:
            v = check_invariants(s)
            if v:
                issues.append(f"combat#{i} {kind}: {v}")
            if s.combat_pending is not None:
                issues.append(f"combat#{i} {kind}: combat_pending not cleared")
            determine_scenario_winner(s)
        except Exception as e:
            issues.append(f"combat#{i} {kind} POST_EXCEPTION {e!r}")
    return issues


# --------------------------------------------------------------------------
# Arts of War events
# --------------------------------------------------------------------------
def _deck(s, side):
    return s.decks.teutonic if side == "teutonic" else s.decks.russian


def fuzz_aow_events(seeds=(1, 2, 3, 4, 5)):
    issues = []
    cards = [f"T{i}" for i in range(1, 19)] + [f"R{i}" for i in range(1, 19)]
    for seed in seeds:
        for cid in cards:
            side = "teutonic" if cid.startswith("T") else "russian"
            s = load_scenario("crusade_on_novgorod", seed=seed)
            for sd in ("teutonic", "russian"):
                try:
                    apply_action(s, {"type": "confirm_all_setup_transports", "side": sd, "args": {}})
                except Exception:
                    pass
            # Subsequent-Levy Arts of War so the card resolves as an EVENT.
            s.meta.phase = "levy"; s.meta.levy_step = "arts_of_war"; s.meta.active_player = side
            s.meta.first_levy_done = True
            s.meta.aow_drawn_t = True; s.meta.aow_drawn_r = True
            d = _deck(s, side)
            for pile in (d.deck, d.discard, d.holds, d.this_levy_events,
                         d.this_campaign_events, d.pending_draw, d.capabilities_in_play):
                while cid in pile:
                    pile.remove(cid)
            d.pending_draw = [cid]
            for variant in ("populated", "bare"):
                c = _clone(s)
                args = {"card_id": cid}
                if variant == "populated":
                    args = sp._populate_event_args(c, cid, {"card_id": cid})
                try:
                    apply_action(c, {"type": "aow_implement_card", "side": side, "args": args})
                except IllegalAction as e:
                    recovered = False
                    for v in sp._expand_event_variants(
                            c, {"type": "aow_implement_card", "side": side, "args": {"card_id": cid}}):
                        try:
                            apply_action(c, {k: val for k, val in v.items()
                                             if k in ("type", "side", "args")})
                            recovered = True
                            break
                        except IllegalAction:
                            continue
                    if not recovered and variant == "bare":
                        issues.append(f"aow {cid}/{variant} seed{seed}: bare implement REJECTED ({e.code})")
                    continue
                except Exception as e:
                    issues.append(f"aow {cid}/{variant} seed{seed} EXCEPTION {e!r}")
                    continue
                v = check_invariants(c)
                if v:
                    issues.append(f"aow {cid}/{variant} seed{seed}: {v}")
                try:
                    determine_scenario_winner(c)
                except Exception as e:
                    issues.append(f"aow {cid}/{variant} seed{seed} WINNER_CRASH {e!r}")
    return issues


# --------------------------------------------------------------------------
# Veche
# --------------------------------------------------------------------------
def fuzz_veche(scenarios=SCENARIOS, seeds=range(1, 9), max_steps=400):
    issues = []
    for scen in scenarios:
        for seed in seeds:
            s = load_scenario(scen, seed=seed)
            for side in ("teutonic", "russian"):
                try:
                    apply_action(s, {"type": "confirm_all_setup_transports", "side": side, "args": {}})
                except Exception:
                    pass
            rac: Counter = Counter()
            for n in range(max_steps):
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
                for mv in (m for m in moves if m["type"] == "veche_action"):
                    c = _clone(s)
                    try:
                        apply_action(c, {k: v for k, v in mv.items() if k in ("type", "side", "args")})
                    except IllegalAction:
                        continue
                    except Exception as e:
                        issues.append(f"veche {scen}/{seed} step{n} {mv['args']} EXCEPTION {e!r}")
                        continue
                    v = check_invariants(c)
                    if v:
                        issues.append(f"veche {scen}/{seed} step{n} {mv['args']}: {v}")
                    try:
                        determine_scenario_winner(c)
                    except Exception as e:
                        issues.append(f"veche {scen}/{seed} step{n} WINNER_CRASH {e!r}")
                pick = sorted(moves, key=lambda mm: -sp._move_priority(mm, rac))[n % min(3, len(moves))]
                act = {k: v for k, v in pick.items() if k in ("type", "side", "args")}
                if act["type"] == "aow_implement_card":
                    act["args"] = sp._populate_event_args(s, act["args"].get("card_id"), act["args"])
                rac[(act["type"], act.get("side"))] += 1
                if n % 50 == 0 and n > 0:
                    rac.clear()
                try:
                    apply_action(s, act)
                except IllegalAction:
                    ok = False
                    variants = (sp._expand_event_variants(s, pick)
                                if pick.get("type") == "aow_implement_card" else [])
                    for cand in variants + [mm for mm in moves if mm is not pick]:
                        try:
                            apply_action(s, {k: v for k, v in cand.items() if k in ("type", "side", "args")})
                            ok = True
                            break
                        except IllegalAction:
                            continue
                    if not ok:
                        break
    return issues


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Nevsky subsystem fuzzers")
    ap.add_argument("--combat", type=int, default=500, help="number of randomized combats")
    ap.add_argument("--seeds", default="1-5", help="seed range for AoW/Veche, e.g. 1-8")
    args = ap.parse_args(argv)
    seeds = list(_fi._parse_seeds(args.seeds))

    all_issues = []
    print(f"[1/3] Combat fuzz: {args.combat} randomized Storms/Sallies/Battles ...")
    ci = fuzz_combat(args.combat)
    print("      clean" if not ci else f"      {len(ci)} issue(s)")
    all_issues += ci
    print("[2/3] Arts-of-War event fuzz: 36 cards x "
          f"{len(seeds)} seeds (populated + bare) ...")
    ai = fuzz_aow_events(seeds)
    print("      clean" if not ai else f"      {len(ai)} issue(s)")
    all_issues += ai
    print(f"[3/3] Veche fuzz: all options across seeds {seeds[0]}..{seeds[-1]} ...")
    vi = fuzz_veche(seeds=seeds)
    print("      clean" if not vi else f"      {len(vi)} issue(s)")
    all_issues += vi

    if all_issues:
        print(f"\nFAIL: {len(all_issues)} subsystem invariant violation(s):")
        for x in all_issues[:50]:
            print("  -", x)
        return 1
    print("\nOK: all subsystem fuzzers clean (combat, Arts-of-War events, Veche).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
