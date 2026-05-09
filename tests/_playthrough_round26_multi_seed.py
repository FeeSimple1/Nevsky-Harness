"""TEST FIXTURE / engine-soundness multi-seed sweep — NOT part of the
shipped harness.

Plays a scenario across many seeds with invariant checks at each turn
boundary. Catches state inconsistencies (orphaned markers, negative
force counts, Lord-state vs Calendar mismatch, sequence non-monotonic,
VP cap violation, etc.) that a single-seed run wouldn't surface.

Run: PYTHONPATH=src python3 tests/_playthrough_round26_multi_seed.py SCENARIO N
"""
from __future__ import annotations
import json, sys, traceback
from copy import deepcopy
from nevsky.scenarios import load_scenario, determine_scenario_winner
from nevsky.actions import apply_action, IllegalAction
from nevsky.legal_moves import legal_moves
from nevsky.render import paths_from
from nevsky.static_data import load_cards, load_locales
from nevsky.previews import vp_forecast


# =====================================================================
# Invariant checks (per-turn boundary)
# =====================================================================


def check_invariants(s, label):
    """Raise AssertionError if any invariant fails."""
    issues = []
    # Sequence monotonic across calls is checked outside.
    # Box bounds.
    if not (1 <= s.meta.box <= 16):
        issues.append(f"box out of bounds: {s.meta.box}")
    # All Lords valid state.
    for lid, lord in s.lords.items():
        if lord.state == "mustered":
            if lord.location is None:
                issues.append(f"{lid} mustered with no location")
            elif lord.location not in s.locales:
                issues.append(f"{lid} mustered at unknown locale {lord.location}")
            for k, v in lord.forces.items():
                if v < 0:
                    issues.append(f"{lid} negative {k}={v}")
            for k, v in lord.assets.items():
                if v < 0:
                    issues.append(f"{lid} negative asset {k}={v}")
                if v > 8:
                    issues.append(f"{lid} {k}={v} exceeds 8-cap (1.7.3)")
            for k, v in lord.routed_units.items():
                if v < 0:
                    issues.append(f"{lid} negative routed {k}={v}")
        elif lord.state == "removed":
            if lord.location is not None:
                issues.append(f"{lid} removed but location={lord.location}")
            if lord.forces or lord.assets or lord.routed_units:
                issues.append(f"{lid} removed but still has forces/assets/routed")
    # Veche caps.
    if s.veche.coin > 8:
        issues.append(f"veche.coin={s.veche.coin} > 8")
    if s.veche.vp_markers > 8:
        issues.append(f"veche.vp_markers={s.veche.vp_markers} > 8")
    if s.veche.coin < 0:
        issues.append(f"veche.coin negative {s.veche.coin}")
    if s.veche.vp_markers < 0:
        issues.append(f"veche.vp_markers negative {s.veche.vp_markers}")
    # VP non-negative; cap 17.5 per 5.1.
    if s.calendar.russian_vp < 0:
        issues.append(f"russian_vp={s.calendar.russian_vp} < 0")
    if s.calendar.teutonic_vp < 0:
        issues.append(f"teutonic_vp={s.calendar.teutonic_vp} < 0")
    if s.calendar.russian_vp > 17.5:
        issues.append(f"russian_vp={s.calendar.russian_vp} > 17.5 cap")
    if s.calendar.teutonic_vp > 17.5:
        issues.append(f"teutonic_vp={s.calendar.teutonic_vp} > 17.5 cap")
    # Phase / step coherence.
    if s.meta.phase == "levy" and s.meta.levy_step not in (
        "arts_of_war", "pay", "disband", "muster", "call_to_arms", "done"
    ):
        issues.append(f"bad levy_step={s.meta.levy_step}")
    if s.meta.phase == "campaign" and s.meta.campaign_step not in (
        "plan", "command", "end_campaign", "done"
    ):
        issues.append(f"bad campaign_step={s.meta.campaign_step}")
    # Calendar markers: each Lord cylinder should appear at most once
    # across boxes + off_left/right.
    for lid in s.lords:
        cyl_count = (
            sum(1 for cb in s.calendar.boxes if lid in cb.cylinders)
            + (1 if lid in s.calendar.off_left else 0)
            + (1 if lid in s.calendar.off_right else 0)
        )
        if cyl_count > 1:
            issues.append(f"{lid} cylinder appears {cyl_count} times on calendar")
        svc_count = (
            sum(1 for cb in s.calendar.boxes if lid in cb.service_markers)
            + (1 if lid in s.calendar.off_left_service else 0)
            + (1 if lid in s.calendar.off_right_service else 0)
        )
        if svc_count > 1:
            issues.append(f"{lid} service marker appears {svc_count} times on calendar")
    # Locale markers: counts non-negative.
    for lid, loc in s.locales.items():
        if loc.siege_markers < 0:
            issues.append(f"{lid}.siege_markers={loc.siege_markers}")
        if loc.teutonic_conquered < 0 or loc.russian_conquered < 0:
            issues.append(f"{lid} conq negative")
    return issues


# =====================================================================
# Driver
# =====================================================================


def step(s, act, expect_illegal=False):
    try:
        return apply_action(s, act)
    except IllegalAction:
        if expect_illegal: return None
        return None
    except Exception:
        raise


def implement_drawn(s, side):
    cards = load_cards()
    deck = s.decks.teutonic if side == "teutonic" else s.decks.russian
    while deck.pending_draw:
        cid = deck.pending_draw[0]
        c = cards[cid]
        scope = c["capability_scope"]
        if scope == "side_wide":
            r = step(s, {"type": "aow_implement_card", "side": side, "args": {}})
        elif scope == "this_lord":
            pin = next((lid for lid, l in s.lords.items()
                         if l.side == side and l.state == "mustered"), None)
            if pin is None:
                deck.pending_draw.pop(0); deck.discard.append(cid); continue
            r = step(s, {"type": "aow_implement_card", "side": side, "args": {"lord_id": pin}})
        else:
            deck.pending_draw.pop(0); deck.discard.append(cid); continue
        if r is None and deck.pending_draw and deck.pending_draw[0] == cid:
            deck.pending_draw.pop(0); deck.discard.append(cid)


def levy_phase(s):
    step(s, {"type": "aow_shuffle", "side": "teutonic", "args": {}})
    step(s, {"type": "aow_draw", "side": "teutonic", "args": {}})
    implement_drawn(s, "teutonic")
    step(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    step(s, {"type": "aow_shuffle", "side": "russian", "args": {}})
    step(s, {"type": "aow_draw", "side": "russian", "args": {}})
    implement_drawn(s, "russian")
    step(s, {"type": "advance_step", "side": "russian", "args": {}})
    # pay
    step(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    step(s, {"type": "advance_step", "side": "russian", "args": {}})
    # disband
    step(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    step(s, {"type": "advance_step", "side": "russian", "args": {}})
    # muster (auto)
    moves = legal_moves(s, with_previews=False)
    teu_m = [m for m in moves if m["type"] == "muster_lord"]
    if teu_m: step(s, teu_m[0])
    step(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    moves = legal_moves(s, with_previews=False)
    veche_b = [m for m in moves if m["type"] == "veche_action" and m["args"].get("option") == "B"]
    if veche_b: step(s, veche_b[0])
    moves = legal_moves(s, with_previews=False)
    rus_m = [m for m in moves if m["type"] == "muster_lord"]
    if rus_m: step(s, rus_m[0], expect_illegal=True)
    step(s, {"type": "advance_step", "side": "russian", "args": {}})
    # call_to_arms
    step(s, {"type": "legate_skip", "side": "teutonic", "args": {}})
    step(s, {"type": "aow_discard_this_levy", "side": "teutonic", "args": {}})
    step(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    moves = legal_moves(s, with_previews=False)
    veche = next((m for m in moves if m["type"] == "veche_action"), None)
    if veche: step(s, veche)
    else: step(s, {"type": "veche_action", "side": "russian", "args": {"option": "skip"}}, expect_illegal=True)
    step(s, {"type": "aow_discard_this_levy", "side": "russian", "args": {}})
    step(s, {"type": "advance_step", "side": "russian", "args": {}})


def make_plan(s):
    from nevsky.campaign import _plan_target_size
    target = _plan_target_size(s.meta.box)
    for side in ("teutonic", "russian"):
        own = [lid for lid, l in s.lords.items()
                if l.side == side and l.state == "mustered"]
        plan = own[:target]
        while len(plan) < target: plan.append("pass")
        plan = plan[:target]
        for c in plan:
            step(s, {"type": "plan_add_card", "side": side, "args": {"card": c}}, expect_illegal=True)
        step(s, {"type": "finalize_plan", "side": side, "args": {}}, expect_illegal=True)


def execute_lord(s, side, active):
    if active not in s.lords:
        step(s, {"type": "cmd_pass", "side": side, "args": {"lord_id": active}}, expect_illegal=True)
        return
    lord = s.lords[active]
    loc = lord.location
    if loc is None:
        step(s, {"type": "cmd_pass", "side": side, "args": {"lord_id": active}}, expect_illegal=True)
        return
    # Find nearest enemy stronghold reachable.
    static_loc = load_locales()
    paths = paths_from(s, loc, max_hops=4)
    target = None
    best = 999
    for tgt, path in paths.items():
        if not path: continue
        st = static_loc.get(tgt, {})
        terr = st.get("territory")
        if terr == ("russian" if side == "teutonic" else "teutonic"):
            if st.get("type") in ("fort", "city", "novgorod", "bishopric", "castle", "commandery"):
                if len(path) < best:
                    target = tgt; best = len(path)
    if target is None:
        step(s, {"type": "cmd_pass", "side": side, "args": {"lord_id": active}}, expect_illegal=True)
        return
    # March one hop.
    hop = paths[target][0]
    step(s, {"type": "cmd_march", "side": side,
              "args": {"lord_id": active, "to": hop}}, expect_illegal=True)
    # If at target with siege > 0, try Storm.
    if (s.lords.get(active) and s.lords[active].location == target
            and s.locales[target].siege_markers > 0
            and s.campaign_turn.actions_remaining > 0):
        try:
            fc = vp_forecast(s, {"type": "cmd_storm", "side": side,
                                  "args": {"lord_id": active}}, preview_trials=10)
            prev = fc.get("preview") or {}
            if prev.get("attacker_winrate", 0) > 0.4:
                step(s, {"type": "cmd_storm", "side": side,
                          "args": {"lord_id": active}}, expect_illegal=True)
        except Exception:
            pass
    if (s.lords.get(active) and s.campaign_turn.actions_remaining > 0
            and not s.campaign_turn.in_feed_pay_disband
            and s.combat_pending is None):
        step(s, {"type": "cmd_pass", "side": side, "args": {"lord_id": active}}, expect_illegal=True)


def handle_combat_pending(s):
    cp = s.combat_pending
    if cp is None: return
    side = cp.pending_response_by
    # Withdraw if possible, else stand.
    r = step(s, {"type": "withdraw", "side": side, "args": {}}, expect_illegal=True)
    if r is None:
        step(s, {"type": "stand_battle", "side": side, "args": {}}, expect_illegal=True)


def activations(s):
    safety = 80
    cp_safety = 6
    while s.meta.campaign_step == "command" and safety > 0:
        if s.combat_pending is not None:
            cp_safety -= 1
            if cp_safety <= 0:
                step(s, {"type": "stand_battle",
                          "side": s.combat_pending.pending_response_by,
                          "args": {}}, expect_illegal=True)
                cp_safety = 6; continue
            handle_combat_pending(s); continue
        cp_safety = 6
        side = s.campaign_turn.next_to_reveal
        prev_seq = s.meta.sequence
        if not s.campaign_turn.in_feed_pay_disband:
            step(s, {"type": "command_reveal", "side": side, "args": {}}, expect_illegal=True)
            active = s.campaign_turn.active_lord
            if active:
                execute_lord(s, side, active)
            if s.campaign_turn.actions_remaining > 0 and not s.campaign_turn.in_feed_pay_disband:
                step(s, {"type": "end_card", "side": side, "args": {}}, expect_illegal=True)
        step(s, {"type": "fpd_resolve", "side": "teutonic", "args": {}}, expect_illegal=True)
        step(s, {"type": "fpd_resolve", "side": "russian", "args": {}}, expect_illegal=True)
        if s.meta.sequence == prev_seq: break
        safety -= 1
    if s.meta.campaign_step == "end_campaign":
        step(s, {"type": "end_campaign_resolve", "side": "teutonic", "args": {}})
        step(s, {"type": "end_campaign_resolve", "side": "russian", "args": {}})


def play(scenario_id, seed, max_turns=20):
    """Returns dict {seed, turns, exception, invariant_violations, final}."""
    out = {"seed": seed, "turns": 0, "exception": None,
           "invariant_violations": [], "final": None}
    try:
        s = load_scenario(scenario_id, seed=seed)
        step(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
        step(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})
    except Exception as e:
        out["exception"] = f"setup: {type(e).__name__}: {e}"
        return out
    last_seq = -1
    turn = 0
    while s.meta.box <= s.meta.span_end_box and turn < max_turns:
        if s.meta.phase != "levy": break
        turn += 1
        try:
            levy_phase(s)
            issues = check_invariants(s, f"t{turn} after levy")
            if issues:
                out["invariant_violations"].extend([f"t{turn}/levy: {i}" for i in issues])
            make_plan(s)
            issues = check_invariants(s, f"t{turn} after plan")
            if issues:
                out["invariant_violations"].extend([f"t{turn}/plan: {i}" for i in issues])
            activations(s)
            issues = check_invariants(s, f"t{turn} after activations")
            if issues:
                out["invariant_violations"].extend([f"t{turn}/acts: {i}" for i in issues])
        except Exception as e:
            out["exception"] = f"t{turn}: {type(e).__name__}: {e}\n{traceback.format_exc()}"
            return out
        # Sequence monotonic.
        if s.meta.sequence <= last_seq:
            out["invariant_violations"].append(
                f"t{turn}: sequence not monotonic ({last_seq} -> {s.meta.sequence})"
            )
        last_seq = s.meta.sequence
    out["turns"] = turn
    final = determine_scenario_winner(s)
    out["final"] = final
    return out


def main():
    sid = sys.argv[1] if len(sys.argv) > 1 else "pleskau"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    print(f"Sweeping {sid} with {n} seeds...", file=sys.stderr)
    summary = {"scenario": sid, "trials": n,
               "exceptions": 0, "invariant_violations": 0,
               "winners": {"teutonic": 0, "russian": 0, "draw": 0},
               "all_violations": [], "exception_seeds": []}
    for seed in range(1, n+1):
        r = play(sid, seed)
        if r["exception"]:
            summary["exceptions"] += 1
            summary["exception_seeds"].append({"seed": seed, "exception": r["exception"][:200]})
        if r["invariant_violations"]:
            summary["invariant_violations"] += len(r["invariant_violations"])
            summary["all_violations"].append({"seed": seed, "violations": r["invariant_violations"][:5]})
        if r["final"]:
            w = r["final"]["winner"]
            if w in summary["winners"]:
                summary["winners"][w] += 1
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
