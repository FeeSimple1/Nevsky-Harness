"""Full-length Crusade diagnostic: external player, unchanged engine.

Uses resource-aware decisions, not future dice outcomes. Additional raw-JSON
Supply and re-Muster requests exercise legal operations missing from menus;
accepted missing requests are recorded separately, never patched into engine.
"""

from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import inspect
import json
import sys
import traceback
from collections import Counter, defaultdict, deque
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from fuzz_invariants import check_invariants
from llm_self_play import _concrete_actions

import nevsky.actions as actmod
import nevsky.campaign as camp
from nevsky.actions import (
    IllegalAction,
    _find_service_marker_box,
    _free_seats_for,
    _seats_of,
    apply_action,
)
from nevsky.held_actions import held_actions_for_side
from nevsky.scenarios import _compute_vp, determine_scenario_winner, load_scenario
from nevsky.state import GameState
from nevsky.static_data import load_cards, load_locales, load_lords, load_ways

_parser = argparse.ArgumentParser(description="Audited full-scenario self-play")
_parser.add_argument("--seed", type=int, required=True)
_parser.add_argument("--policy", choices=["logistics", "combined", "maritime"], default="logistics")
_parser.add_argument("--out", type=Path, required=True)
_parser.add_argument("--label", default="2258489")
_opts = _parser.parse_args()
OUT, SEED, POLICY, BASE = _opts.out, _opts.seed, _opts.policy, _opts.label
OUT.mkdir(parents=True, exist_ok=True)
SCENARIO = "crusade_on_novgorod"
LOCS, LORDS, CARDS = load_locales(), load_lords(), load_cards()
ADJ = defaultdict(list)
for w in load_ways():
    ADJ[w["a"]].append(w["b"])
    ADJ[w["b"]].append(w["a"])


def clone(s):
    # Engine history is append-only. Copy the list, sharing read-only entries.
    return copy.deepcopy(s, {id(s.history): list(s.history)})


def fingerprint(s):
    raw = s.model_dump(exclude={"history"})
    return hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()


@cache
def route(a, b):
    q, seen = deque([(a, [a])]), {a}
    while q:
        node, path = q.popleft()
        if node == b:
            return path
        for nxt in ADJ[node]:
            if nxt not in seen:
                seen.add(nxt)
                q.append((nxt, path + [nxt]))
    return []


@cache
def distance(a, b):
    p = route(a, b)
    return len(p) - 1 if p else 99


def roster(s, side):
    return [
        lid
        for lid, l in s.lords.items()
        if l.side == side and l.state == "mustered" and l.location is not None
    ]


def force(s, ids):
    weights = {
        "knights": 2.0,
        "sergeants": 1.7,
        "men_at_arms": 1.4,
        "light_horse": 1.2,
        "asiatic_horse": 1.6,
        "militia": 0.8,
        "serfs": 0.3,
    }
    return sum(weights.get(u, 1) * n for lid in ids for u, n in s.lords[lid].forces.items())


def minimal(a):
    return {k: copy.deepcopy(v) for k, v in a.items() if k in ("type", "side", "args")}


def snapshot(s):
    return {
        "box": s.meta.box,
        "phase": s.meta.phase,
        "step": s.meta.levy_step if s.meta.phase == "levy" else s.meta.campaign_step,
        "active": s.meta.active_player,
        "vp": {"teutonic": s.calendar.teutonic_vp, "russian": s.calendar.russian_vp},
        "lords": {
            lid: {
                "state": l.state,
                "at": l.location,
                "service": _find_service_marker_box(s, lid),
                "assets": dict(l.assets),
                "forces": dict(l.forces),
                "besieged": l.in_stronghold,
            }
            for lid, l in s.lords.items()
        },
    }


def run_game():
    s = load_scenario(SCENARIO, seed=SEED)
    history, findings, boundaries = [], [], []
    index = {}
    counts = Counter()
    visits, attempts = Counter(), Counter()
    previous_box = None
    roundtrips = 0
    states = gzip.open(OUT / "positions.jsonl.gz", "wt")

    def finding(kind, action=None, details=None):
        key = json.dumps([kind, action, details], sort_keys=True, default=str)
        if key in index:
            findings[index[key]]["occurrences"] += 1
            return
        n = len(findings)
        index[key] = n
        item = {
            "kind": kind,
            "first_action": len(history),
            "box": s.meta.box,
            "side": s.meta.active_player,
            "action": action,
            "details": details,
            "occurrences": 1,
            "state_file": f"finding_{n:03d}.state.json",
        }
        findings.append(item)
        (OUT / item["state_file"]).write_text(s.model_dump_json())
        print("FINDING", json.dumps({k: v for k, v in item.items() if k != "details"}), flush=True)

    def probe(action):
        p = clone(s)
        before = fingerprint(p)
        try:
            result = apply_action(p, minimal(action))
            return True, result
        except IllegalAction as exc:
            if fingerprint(p) != before:
                finding("rejected_action_mutates_state", minimal(action), {"code": exc.code})
            return False, {"code": exc.code, "message": str(exc)}
        except Exception as exc:
            finding("candidate_exception", minimal(action), {"error": repr(exc)})
            return False, {"exception": repr(exc)}

    def raw_requests(side, raw):
        extra = []
        if s.meta.phase == "levy" and s.meta.levy_step == "muster":
            offered = {
                a.get("args", {}).get("target_lord") for a in raw if a["type"] == "muster_lord"
            }
            for target, lord in s.lords.items():
                if lord.side != side or lord.state != "disbanded" or target == "aleksandr":
                    continue
                for by in roster(s, side):
                    for seat in _free_seats_for(s, target):
                        a = {
                            "type": "muster_lord",
                            "side": side,
                            "args": {"by_lord": by, "target_lord": target, "seat": seat},
                        }
                        ok, _ = probe(a)
                        if ok:
                            if target not in offered:
                                finding("missing_remuster_option", a, {"lord_state": lord.state})
                            extra.append(a)
                            break
                    if extra and extra[-1].get("args", {}).get("target_lord") == target:
                        break
        if (
            s.meta.phase == "campaign"
            and s.meta.campaign_step == "command"
            and not s.campaign_turn.in_feed_pay_disband
            and s.combat_pending is None
            and s.campaign_turn.actions_remaining > 0
        ):
            lid = s.campaign_turn.active_lord
            if lid is not None and s.lords[lid].side == side and not s.lords[lid].in_stronghold:
                l = s.lords[lid]
                if l.assets.get("provender", 0) >= 6:
                    return extra
                possible = set()
                for other, sl in LORDS.items():
                    if sl["side"] == side and s.lords[other].state != "removed":
                        possible.update(_seats_of(s, other))
                if l.assets.get("ship", 0):
                    possible.update(x for x, loc in LOCS.items() if loc.get("seaport"))
                sources = []
                for src in sorted(possible, key=lambda x: (distance(l.location, x), x)):
                    path = route(src, l.location)
                    if not path or len(path) > 4:
                        continue
                    source = {"locale_id": src, "route": path, "transport": "auto"}
                    a = {"type": "cmd_supply", "side": side, "args": {"sources": [source]}}
                    ok, result = probe(a)
                    if ok and result.get("added", 0) > 0:
                        sources.append(source)
                        extra.append(a)
                        if len(sources) == 3:
                            break
                if len(sources) > 1:
                    for n in range(2, len(sources) + 1):
                        a = {"type": "cmd_supply", "side": side, "args": {"sources": sources[:n]}}
                        if probe(a)[0]:
                            extra.append(a)
                if sources and not any(a["type"] == "cmd_supply" for a in raw):
                    finding("missing_supply_option", extra[-1], {"lord_id": lid, "at": l.location})
        if (
            s.meta.phase == "campaign"
            and s.meta.campaign_step == "command"
            and s.combat_pending is None
            and not s.campaign_turn.in_feed_pay_disband
            and s.campaign_turn.active_lord
            and s.campaign_turn.actions_remaining > 0
        ):
            lid = s.campaign_turn.active_lord
            lord = s.lords[lid]
            from nevsky.capabilities import has_lord_capability

            group = [lid] + ([lord.has_lower_lord] if lord.has_lower_lord else [])
            if any(has_lord_capability(s, x, "Converts") for x in group):
                offered = {
                    (a.get("args", {}).get("to"), a.get("args", {}).get("way_type"))
                    for a in raw
                    if a["type"] == "cmd_march"
                }
                for way in load_ways():
                    if lord.location not in (way["a"], way["b"]):
                        continue
                    dest = way["b"] if lord.location == way["a"] else way["a"]
                    candidate = {
                        "type": "cmd_march",
                        "side": side,
                        "args": {
                            "lord_id": lid,
                            "to": dest,
                            "way_type": way["type"],
                            "group": group,
                            "discard_excess_provender": True,
                        },
                    }
                    if (dest, way["type"]) not in offered and probe(candidate)[0]:
                        finding(
                            "missing_converts_march",
                            candidate,
                            {"actions_remaining": s.campaign_turn.actions_remaining},
                        )
        return extra

    def base_score(a, side):
        typ, args = a["type"], a.get("args", {})
        bx = s.meta.box
        own = roster(s, side)
        if typ == "aow_play_hold":
            cid = args["card_id"]
            if cid == "T3":
                return 450
            if cid == "R3":
                lord = s.lords[args["target"]]
                food = lord.assets.get("provender", 0)
                need = max(1, (sum(lord.forces.values()) + 5) // 6)
                return 420 - food * 10 if food <= need else -50
            if cid == "T13":
                return 160 if len(own) >= 4 else -50
        if typ == "aow_lordship_plus_2":
            if args.get("mode") == "lordship":
                return 130
            lid = args["lord_id"]
            from nevsky.actions import _find_cylinder_box

            pos = _find_cylinder_box(s, lid)
            return 120 if args.get("direction") == "left" and pos is not None and pos > bx else -50

        # Mandatory/progression choices lose to worthwhile voluntary decisions.
        progress = {
            "advance_step": 0,
            "end_card": -5,
            "cmd_pass": -6,
            "fpd_resolve": 0,
            "finalize_plan": 100,
            "command_reveal": 100,
            "aow_draw": 100,
            "aow_shuffle": 100,
            "disband_resolve": 100,
            "aow_discard_this_levy": -1,
            "legate_skip": -1,
        }
        if typ in progress:
            return progress[typ]
        if typ == "aow_implement_card":
            direction = args.get("direction")
            target = args.get("target", "")
            target_id = target.replace("service:", "") if isinstance(target, str) else ""
            target_side = s.lords[target_id].side if target_id in s.lords else None
            if target_side:
                good = (direction == "right") == (target_side == side)
                # Cylinders become available sooner by moving left; Service later by right.
                if not target.startswith("service:"):
                    good = not good
                return 110 + (10 if good else 0)
            return 110
        if typ in ("pay_with_coin", "pay_with_loot"):
            target = args.get("target_lord")
            service = _find_service_marker_box(s, target)
            goal = min(
                17,
                bx
                + (
                    5
                    if target in ("domash", "rudolf")
                    else 4
                    if s.lords[target].location not in _seats_of(s, target)
                    else 3
                ),
            )
            return 400 + (goal - service) * 30 if service is not None and service < goal else -20
        if typ == "muster_lord":
            by, target = args.get("by_lord"), args.get("target_lord")
            return (200 if len(own) < 4 else 40) + LORDS[target]["ratings"]["command"]
        if typ == "muster_vassal":
            by = args["by_lord"]
            return 65 if sum(s.lords[by].forces.values()) < 7 else -10
        if typ == "levy_transport":
            by, tr = args["by_lord"], args["transport_type"]
            wanted = (
                "sled" if camp._season_of_box(bx) in ("early_winter", "late_winter") else "cart"
            )
            have = s.lords[by].assets.get(tr, 0)
            if tr == wanted:
                return 140 - 30 * have if have < 3 else -10
            if tr == "boat" and have < 1:
                return 65
            return -10
        if typ == "levy_capability":
            cid, by = args["card_id"], args["by_lord"]
            cap = CARDS[cid].get("capability_name", "")
            desirable = {
                "Baggage Train": 85,
                "Teutonic Knights": 80,
                "Raiders": 65,
                "William of Modena": 90,
                "Orthodox": 75,
                "Archbishopric": 90,
                "Lodya": 65,
                "Smerdi": 30,
                "Stone Kremlin": 35,
                "Crusade": 60,
                "Stonemasons": 55,
                "Cogs": 65,
            }
            return desirable.get(cap, 25) - 40 * len(s.lords[by].this_lord_capabilities)
        if typ == "veche_action":
            option = args.get("option")
            if option == "B":
                return 250
            if option == "A":
                return 55
            if option == "C":
                return 40
            return 25
        if typ.startswith("veche_"):
            return 80
        if typ == "legate_arrives":
            return 80
        if typ == "legate_move":
            return 15 if args.get("locale_id") != s.legate.locale_id else -20
        if typ == "legate_use":
            return {"2a": 160, "2b": 70, "2c": 40}.get(args.get("sub_option"), 10)
        if typ == "plan_add_card":
            lid = args.get("card")
            if lid == "pass":
                return -1
            deck = getattr(s.decks, side)
            l = s.lords[lid]
            margin = (_find_service_marker_box(s, lid) or bx) - bx
            at_seat = l.location in _seats_of(s, lid)
            urgency = max(0, 4 - margin - l.assets.get("coin", 0))
            val = 100 + 15 * urgency if at_seat else 100
            if s.locales[l.location].siege_markers:
                val += 15
            val += LORDS[lid]["ratings"]["command"]
            return val - 45 * deck.plan.count(lid)
        if typ == "place_lieutenant":
            return -10
        if typ == "stand_battle":
            cp = s.combat_pending
            ratio = force(s, cp.defender_lords) / max(1, force(s, cp.attacker_group))
            return (160 if ratio >= 0.8 else 50) - (40 if args.get("concede") else 0)
        if typ == "withdraw":
            return 125
        if typ == "avoid_battle":
            return 100
        if typ == "play_ambush_block":
            return 90
        if typ == "decline_ambush_block":
            return 10
        if typ == "end_campaign_resolve":
            return 100
        lid = args.get("lord_id") or s.campaign_turn.active_lord
        if lid not in s.lords:
            return 5
        l = s.lords[lid]
        service = _find_service_marker_box(s, lid) or bx
        food, coin = l.assets.get("provender", 0), l.assets.get("coin", 0)
        feed = max(1, (sum(l.forces.values()) + 5) // 6)
        target_food = 2 * feed
        if typ == "cmd_tax":
            return (
                270
                if service - bx + coin < (6 if lid in ("domash", "rudolf") else 4)
                else (80 if coin < 3 else -10)
            )
        if typ in ("cmd_supply", "cmd_forage"):
            qty = len(args.get("sources", [])) if typ == "cmd_supply" else 1
            return (240 if food < target_food else 30 if food < target_food + 2 else -10) + qty
        if typ == "cmd_siege":
            return 145 - (80 if args.get("decline_surrender") else 0)
        if typ == "cmd_storm":
            defenders = [
                x
                for x in roster(s, "russian" if side == "teutonic" else "teutonic")
                if s.lords[x].location == l.location
            ]
            attackers = [
                x for x in own if s.lords[x].location == l.location and not s.lords[x].in_stronghold
            ]
            ratio = force(s, attackers) / max(2.5, force(s, defenders))
            return (
                165
                if ratio >= 2
                and sum(
                    s.lords[x].forces.get("men_at_arms", 0) + s.lords[x].forces.get("militia", 0)
                    for x in attackers
                )
                >= 3
                else 20
            )
        if typ == "cmd_sally":
            return 120
        if typ in ("cmd_ravage", "cmd_raiders_ravage"):
            return 175 if food < target_food or coin < 1 else 155
        if typ in ("cmd_stonemasons", "cmd_stone_kremlin"):
            return 150
        if typ == "cmd_muster_serf":
            return 40 if sum(l.forces.values()) < 6 else -10
        if typ == "legate_command_bonus":
            return 100
        if typ in ("cmd_march", "cmd_sail"):
            dest = args.get("to") or args.get("destination")
            # Keep a recruiting and financial reserve on each side. This is
            # solely a player's policy: no engine rules/termination override.
            if lid in ("domash", "rudolf") and l.location in _seats_of(s, lid):
                return -60
            if args.get("concede"):
                return -100
            seats = _seats_of(s, lid)
            home_dist = min((distance(l.location, x) for x in seats), default=99)
            new_home_dist = min((distance(dest, x) for x in seats), default=99)
            if service - bx + coin < 2:
                return 225 + 10 * (home_dist - new_home_dist) if new_home_dist < home_dist else -20
            # Defensive Russian line, offensive Teutonic axes; counterattack later.
            if side == "teutonic":
                goals = (
                    ["izborsk", "pskov"]
                    if lid in ("hermann", "yaroslav", "heinrich", "rudolf")
                    else ["kaibolovo", "koporye"]
                )
            else:
                goals = (
                    ["pskov", "izborsk"]
                    if lid in ("gavrilo", "domash", "aleksandr", "andrey")
                    else ["kaibolovo", "koporye"]
                )
            goals = [
                g
                for g in goals
                if g in LOCS
                and (side == "russian" or getattr(s.locales[g], f"{side}_conquered") == 0)
            ]
            if not goals:
                goals = ["pskov"] if side == "russian" else ["novgorod"]
            target = min(goals, key=lambda x: distance(l.location, x))
            gain = distance(l.location, target) - distance(dest, target)
            enemies = [
                x
                for x, e in s.lords.items()
                if e.side != side
                and e.state == "mustered"
                and e.location == dest
                and not e.in_stronghold
            ]
            own_group = args.get("group") or [lid]
            ratio = force(s, own_group) / max(1, force(s, enemies))
            if enemies and ratio < 1.1:
                return -30
            value = 110 + 25 * gain + (30 if enemies else 0)
            if side == "russian" and l.location == target and not enemies:
                value -= 110
            if args.get("discard_excess_provender"):
                value -= 35
            value -= 18 * visits[(bx, lid, dest)]
            return value
        return 5

    def score(a, side):
        val = base_score(a, side)
        typ, args = a["type"], a.get("args", {})
        if POLICY == "combined":
            if typ == "place_lieutenant":
                val = 180
            elif typ == "stand_battle" and not args.get("concede"):
                val += 65 + (12 if args.get("holds") else 0)
            elif typ == "cmd_storm":
                val += 25
            elif typ == "cmd_march" and len(args.get("group", [])) > 1:
                val += 20
            elif typ == "levy_capability" and args.get("card_id") in ("T3", "T14", "T17", "R18"):
                val += 100
        elif POLICY == "maritime":
            if typ == "levy_capability" and args.get("card_id") in (
                "T13",
                "T18",
                "T12",
                "R8",
                "R9",
            ):
                val += 110
            elif typ == "levy_transport" and args.get("transport_type") == "ship":
                val = 160 - s.lords[args["by_lord"]].assets.get("ship", 0) * 25
            elif typ == "cmd_sail":
                val += 75
            elif typ in ("legate_arrives", "legate_use"):
                val += 100
            elif typ == "aow_play_hold" and args.get("card_id") == "T13":
                val += 30
        # Stable tie-break variation, independent of the engine dice or future outcomes.
        digest = hashlib.sha256(
            f"{SEED}:{POLICY}:{s.meta.box}:{json.dumps(minimal(a), sort_keys=True)}".encode()
        ).digest()
        return val + int.from_bytes(digest[:2], "big") / 65536 * 8

    def independent_audit(action, before_state):
        for sd in ("teutonic", "russian"):
            vp = getattr(s.calendar, sd + "_vp")
            expected = [] if vp < 1 else [min(16, int(vp))]
            actual = [cb.box for cb in s.calendar.boxes if getattr(cb, sd + "_victory_marker")]
            if actual != expected:
                finding(
                    "calendar_marker_stale",
                    action,
                    {"side": sd, "vp": vp, "actual": actual, "expected": expected},
                )
        for lid, l in s.lords.items():
            from nevsky.actions import _find_cylinder_box

            pos = _find_cylinder_box(s, lid)
            if l.state in ("disbanded", "ready") and pos is not None:
                ready = pos <= s.meta.box
                if l.state == "disbanded" and ready:
                    finding(
                        "stale_readiness", action, {"lord": lid, "cylinder": pos, "state": l.state}
                    )
            lower = l.has_lower_lord
            if lower is not None and s.combat_pending is None:
                other = s.lords[lower]
                if (
                    other.lieutenant_of != lid
                    or other.location != l.location
                    or other.state != "mustered"
                ):
                    finding(
                        "lieutenant_pair_inconsistent",
                        action,
                        {
                            "lieutenant": lid,
                            "lower": lower,
                            "locations": [l.location, other.location],
                            "lower_state": other.state,
                        },
                    )
        order = s.meta.muster_lord_order
        if len(order) != len(set(order)):
            finding("muster_reentry", action, {"order": order})
        if s.combat_pending is None:
            for locale in s.locales:
                occupants = [
                    l.side
                    for l in s.lords.values()
                    if l.state == "mustered" and l.location == locale and not l.in_stronghold
                ]
                if len(set(occupants)) > 1:
                    finding("opposed_unbesieged_colocation", action, {"locale": locale})
        if (
            action["type"] == "end_campaign_resolve"
            and before_state.meta.box >= before_state.meta.span_end_box
        ):
            old = {
                lid: [dict(l.assets), dict(l.forces), list(l.this_lord_capabilities)]
                for lid, l in before_state.lords.items()
            }
            new = {
                lid: [dict(l.assets), dict(l.forces), list(l.this_lord_capabilities)]
                for lid, l in s.lords.items()
            }
            if old != new:
                finding("final_turn_mat_changed", action)

    try:
        for side in ("teutonic", "russian"):
            a = {"type": "confirm_all_setup_transports", "side": side, "args": {}}
            result = apply_action(s, a)
            history.append({"action": a, "result": result, "box": s.meta.box})
        for step in range(6500):
            if s.meta.game_over:
                break
            if s.meta.box != previous_box:
                boundaries.append(snapshot(s))
                previous_box = s.meta.box
                print(
                    "ENTER_BOX",
                    s.meta.box,
                    "VP",
                    s.calendar.teutonic_vp,
                    s.calendar.russian_vp,
                    "LORDS",
                    roster(s, "teutonic"),
                    roster(s, "russian"),
                    flush=True,
                )
                (OUT / f"box_{s.meta.box:02d}.state.json").write_text(s.model_dump_json())
            side = s.meta.active_player or "teutonic"
            before_menu = fingerprint(s)
            states.write(
                json.dumps(
                    {"index": len(history), "state": s.model_dump(exclude={"history"})},
                    separators=(",", ":"),
                )
                + "\n"
            )
            raw = _concrete_actions(s, side)
            if POLICY == "combined":
                variants = []
                for original in raw:
                    if original["type"] != "stand_battle" or original.get("args", {}).get(
                        "concede"
                    ):
                        continue
                    for held in original.get("holds_available", []):
                        chosen = minimal(original)
                        holds = {held["key"]: held["card"]}
                        for key, choices in held.get("requires", {}).items():
                            if choices:
                                holds[key] = choices[0]
                        chosen["args"]["holds"] = holds
                        variants.append(chosen)
                raw.extend(variants)
            opponent = "russian" if side == "teutonic" else "teutonic"
            # The opposing player separately sees only their own any-time
            # Holds. Ordinary activation and hidden opponent cards are not
            # handed to the active player.
            interruptions = held_actions_for_side(s, opponent, interrupts_only=True)
            menu = []
            for a in raw:
                if not isinstance(a.get("args"), dict):
                    # Capability swaps remain discretionary; do not auto-cycle cards.
                    continue
                ok, result = probe(a)
                if ok:
                    menu.append(a)
                else:
                    finding("menu_rejected", minimal(a), result)
            menu.extend(raw_requests(side, raw))
            usable_interrupts = [a for a in interruptions if score(a, opponent) >= 300]
            if usable_interrupts:
                menu = usable_interrupts
                side = opponent
            if fingerprint(s) != before_menu:
                finding("menu_mutates_live_state")
                break
            if not menu:
                finding("no_legal_moves", details={"raw": raw})
                break
            # A player's explicit Wastage choice preserves money and useful transport.
            for a in menu:
                if a["type"] == "end_campaign_resolve":
                    waste = {}
                    for lid, opts in a.get("candidates", {}).get("wastage", {}).items():
                        l = s.lords[lid]
                        preference = [
                            "serfs",
                            "boat",
                            "ship",
                            "cart",
                            "sled",
                            "provender",
                            "loot",
                            "coin",
                        ]
                        valid = sorted(
                            opts,
                            key=lambda x: (
                                0
                                if x.startswith("capability:")
                                else 10 + (preference.index(x) if x in preference else 9)
                            ),
                        )
                        if valid:
                            waste[lid] = valid[0]
                    if waste:
                        candidate = minimal(a)
                        candidate["args"]["wastage"] = waste
                        if probe(candidate)[0]:
                            a["args"] = candidate["args"]
            action = minimal(
                max(
                    menu,
                    key=lambda a: (
                        score(a, side)
                        - 200
                        * max(
                            0, attempts[(s.meta.box, json.dumps(minimal(a), sort_keys=True))] - 12
                        )
                    ),
                )
            )
            audited_before = clone(s)
            expected_state = clone(s)
            expected = apply_action(expected_state, copy.deepcopy(action))
            context = {
                "box": s.meta.box,
                "phase": s.meta.phase,
                "step": s.meta.levy_step if s.meta.phase == "levy" else s.meta.campaign_step,
                "side": side,
                "action": action,
                "score": score(action, side),
            }
            result = apply_action(s, copy.deepcopy(action))
            if fingerprint(s) != fingerprint(expected_state) or result != expected:
                finding("nondeterministic_apply", action)
            history.append(
                {
                    **context,
                    "result": result,
                    "vp_after": [s.calendar.teutonic_vp, s.calendar.russian_vp],
                }
            )
            independent_audit(action, audited_before)
            counts[action["type"]] += 1
            attempts[(context["box"], json.dumps(action, sort_keys=True))] += 1
            if action["type"] in ("cmd_march", "cmd_sail"):
                args = action["args"]
                visits[
                    (context["box"], args.get("lord_id"), args.get("to") or args.get("destination"))
                ] += 1
            if step % 20 == 0:
                reloaded = GameState.model_validate_json(s.model_dump_json())
                if fingerprint(reloaded) != fingerprint(s):
                    finding("save_reload_mismatch", action)
                s = reloaded
                roundtrips += 1
            violation = check_invariants(s)
            if violation:
                finding("invariant", action, {"violation": violation})
            for sd in ("teutonic", "russian"):
                deck = getattr(s.decks, sd)
                physical = []
                for zone in (
                    "deck",
                    "discard",
                    "removed",
                    "holds",
                    "pending_draw",
                    "capabilities_in_play",
                    "this_levy_events",
                    "this_campaign_events",
                ):
                    physical.extend(getattr(deck, zone, []))
                for lord in s.lords.values():
                    if lord.side == sd:
                        physical.extend(lord.this_lord_capabilities)
                present = Counter(physical)
                expected_cards = {cid for cid, card in CARDS.items() if card["side"] == sd}
                missing = sorted(expected_cards - set(present))
                duplicates = {cid: n for cid, n in present.items() if n != 1}
                if missing or duplicates:
                    finding(
                        "card_conservation",
                        action,
                        {"side": sd, "missing": missing, "duplicates": duplicates},
                    )
                expected_vp = max(0.0, min(17.5, _compute_vp(sd, s.locales, s.veche, s.calendar)))
                actual = getattr(s.calendar, f"{sd}_vp")
                if expected_vp != actual:
                    finding(
                        "vp_marker_accounting_mismatch",
                        details={"side": sd, "computed": expected_vp, "actual": actual},
                    )
            for lid, l in s.lords.items():
                for name, pile in (("assets", l.assets), ("forces", l.forces)):
                    if any(v < 0 for v in pile.values()):
                        finding(
                            "negative_resource", details={"lord": lid, "pile": name, "values": pile}
                        )
                if l.state == "mustered" and l.location is None:
                    finding("mustered_without_location", details={"lord": lid})
            if step % 100 == 0:
                print("PROGRESS", len(history), "box", s.meta.box, flush=True)
        else:
            finding("step_limit")
    except Exception as exc:
        finding("play_exception", details={"error": repr(exc), "traceback": traceback.format_exc()})

    states.close()
    final = snapshot(s)
    (OUT / "final.state.json").write_text(s.model_dump_json())
    (OUT / "transcript.json").write_text(json.dumps(history, indent=2, default=str))
    (OUT / "findings.json").write_text(json.dumps(findings, indent=2, default=str))
    (OUT / "boundaries.json").write_text(json.dumps(boundaries + [final], indent=2, default=str))
    # Independently reconstruct every committed action from a fresh scenario.
    replay = load_scenario(SCENARIO, seed=SEED)
    replay_errors = []
    try:
        for n, row in enumerate(history):
            res = apply_action(replay, copy.deepcopy(row["action"]))
            if res != row["result"]:
                replay_errors.append({"action": n, "kind": "result_mismatch"})
        if replay.model_dump() != s.model_dump():
            replay_errors.append({"kind": "final_state_mismatch"})
    except Exception as exc:
        replay_errors.append({"action": n, "error": repr(exc)})
    report = {
        "scenario": SCENARIO,
        "seed": SEED,
        "engine_commit": BASE,
        "policy": POLICY,
        "terminal": s.meta.game_over,
        "last_box": s.meta.box,
        "boxes_entered": [b["box"] for b in boundaries],
        "winner": determine_scenario_winner(s) if s.meta.game_over else None,
        "actions_including_setup": len(history),
        "action_counts": dict(counts),
        "save_reload_checks": roundtrips,
        "replay_errors": replay_errors,
        "finding_groups": len(findings),
        "finding_kinds": dict(Counter(f["kind"] for f in findings)),
        "finding_occurrences": dict(
            sum((Counter({f["kind"]: f["occurrences"]}) for f in findings), Counter())
        ),
        "final": final,
    }
    (OUT / "summary.json").write_text(json.dumps(report, indent=2, default=str))
    print(
        "LONG_CRUSADE_REPORT",
        json.dumps({k: v for k, v in report.items() if k != "final"}, default=str),
        flush=True,
    )
    funcs = [
        (actmod, "_h_muster_lord"),
        (actmod, "_is_ready"),
        (camp, "_h_cmd_supply"),
        (camp, "_h_end_campaign_resolve"),
    ]
    sources = []
    for mod, name in funcs:
        fn = getattr(mod, name, None)
        if fn:
            text, start = inspect.getsourcelines(fn)
            sources.append(f"### {mod.__name__}.{name} line {start}\n" + "".join(text))
    (OUT / "source_context.txt").write_text("\n\n".join(sources))


if __name__ == "__main__":
    run_game()
