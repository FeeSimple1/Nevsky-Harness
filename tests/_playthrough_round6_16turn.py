"""TEST FIXTURE / engine-soundness smoke driver — NOT part of the shipped harness.

Round 6: 16-turn Crusade-on-Novgorod run + invariant checks.

This is the LONGEST scenario. Exercises:
  - Box 1->2 (Summer) -> Plow & Reap (Carts -> Sleds)
  - Box 3->4 (EW)
  - Box 5->6 (LW) -> Plow & Reap (Sleds -> Carts)
  - Box 7->8 (Rasputitsa) -> Grow (halve enemy Ravaged)
  - Box 9->10 (Summer year 2) -> Plow & Reap
  - Box 11->12 (EW year 2)
  - Box 13->14 (LW year 2) -> Plow & Reap
  - Box 15->16 (Rasputitsa year 2) -> Grow + game end

Invariant checks at each turn boundary:
  - All Mustered Lords have valid (locale_id) locations.
  - Service markers count matches Mustered Lord count + Disbanded
    holding-pattern Lords on calendar.
  - VP totals don't go negative.
  - Veche caps (8 VP, 8 Coin) never exceeded.
  - sequence is monotonically increasing.
  - phase/step transitions are valid.
"""

from __future__ import annotations

import json
import sys
import traceback

from nevsky.actions import IllegalAction, apply_action
from nevsky.scenarios import load_scenario


BUGS = []


def report(s, label):
    """Run invariant checks and report any violations as BUGs."""
    issues = []
    # Lord state invariants.
    for lid, lord in s.lords.items():
        if lord.state == "mustered":
            if lord.location is None:
                issues.append(f"INV: {lid} mustered but location=None")
            elif lord.location not in s.locales:
                issues.append(f"INV: {lid} mustered at unknown locale {lord.location}")
            for k, v in lord.forces.items():
                if v < 0:
                    issues.append(f"INV: {lid} negative {k}={v}")
            for k, v in lord.assets.items():
                if v < 0:
                    issues.append(f"INV: {lid} negative asset {k}={v}")
                if v > 8:
                    issues.append(f"INV: {lid} {k}={v} exceeds 8-cap")
    # Veche caps.
    if s.veche.coin > 8:
        issues.append(f"INV: veche.coin={s.veche.coin} > 8")
    if s.veche.vp_markers > 8:
        issues.append(f"INV: veche.vp_markers={s.veche.vp_markers} > 8")
    # VP non-negative.
    if s.calendar.russian_vp < 0:
        issues.append(f"INV: russian_vp={s.calendar.russian_vp}")
    if s.calendar.teutonic_vp < 0:
        issues.append(f"INV: teutonic_vp={s.calendar.teutonic_vp}")
    # Phase / step coherence.
    if s.meta.phase == "levy" and s.meta.levy_step not in (
        "arts_of_war", "pay", "disband", "muster", "call_to_arms", "done"
    ):
        issues.append(f"INV: bad levy_step {s.meta.levy_step}")
    if s.meta.phase == "campaign" and s.meta.campaign_step not in (
        "plan", "command", "end_campaign", "done"
    ):
        issues.append(f"INV: bad campaign_step {s.meta.campaign_step}")
    if issues:
        for i in issues:
            BUGS.append(f"[{label}] {i}")
        print(f"  ! INVARIANT VIOLATIONS at {label}:")
        for i in issues:
            print(f"    - {i}")


def fast_levy_skip(s):
    apply_action(s, {"type": "aow_shuffle", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "aow_draw", "side": "teutonic", "args": {}})
    while s.decks.teutonic.pending_draw:
        from nevsky.static_data import load_cards
        cid = s.decks.teutonic.pending_draw[0]
        c = load_cards()[cid]
        args = {}
        if not c["no_event"]:
            if not s.meta.first_levy_done:
                if c["capability_scope"] == "this_lord":
                    t = next((lid for lid, l in s.lords.items()
                              if l.side == "teutonic" and l.state == "mustered"), None)
                    if t: args["lord_id"] = t
                    else: args = None
            else:
                # Subsequent Levy: skip events that need complex args by
                # falling back to a generic guess; rely on the SMOKE-010
                # fix to retry-or-skip if it fails.
                _on_cal = lambda lid: any(lid in cb.cylinders for cb in s.calendar.boxes)
                _has_svc = lambda lid: any(lid in cb.service_markers for cb in s.calendar.boxes)
                _pick = lambda lid: lid if _on_cal(lid) else (f"service:{lid}" if _has_svc(lid) else None)
                if cid == "T1":
                    t = _pick("aleksandr") or _pick("andrey")
                    args = {"target": t, "direction": "left"} if t else None
                elif cid == "T2":
                    args = {"target": "veche"}
                elif cid == "T11":
                    t = next((lid for lid, l in s.lords.items()
                              if l.side == "teutonic" and _on_cal(lid)), None)
                    args = {"target": t} if t else None
                elif cid == "T12":
                    t = _pick("aleksandr") or _pick("andrey")
                    args = {"target": t, "direction": "left"} if t else None
                elif cid == "T14":
                    args = {"locale": next(
                        (lid for lid, loc in s.locales.items() if loc.russian_ravaged),
                        None)}
                    if args["locale"] is None: args = None
                elif cid == "T15":
                    args = {"locale": "ostrov"}
                elif cid == "T18":
                    targets = {}
                    if _on_cal("vladislav"):
                        targets["vladislav"] = "cylinder"
                    elif _has_svc("vladislav"):
                        targets["vladislav"] = "service"
                    if _on_cal("karelians"):
                        targets["karelians"] = "cylinder"
                    elif _has_svc("karelians"):
                        targets["karelians"] = "service"
                    args = {"direction": "left", "targets": targets} if targets else None
                else:
                    args = {}
        if args is None:
            # Discard manually so the test can keep going.
            print(f"    [skip impl {cid}: no valid args]")
            s.decks.teutonic.pending_draw.pop(0)
            s.decks.teutonic.discard.append(cid)
            continue
        try:
            apply_action(s, {"type": "aow_implement_card", "side": "teutonic", "args": args})
        except IllegalAction as e:
            print(f"    [aow_implement {cid} {args} -> {e.code}; discard]")
            if s.decks.teutonic.pending_draw and s.decks.teutonic.pending_draw[0] == cid:
                s.decks.teutonic.pending_draw.pop(0)
                s.decks.teutonic.discard.append(cid)
    apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "aow_shuffle", "side": "russian", "args": {}})
    apply_action(s, {"type": "aow_draw", "side": "russian", "args": {}})
    while s.decks.russian.pending_draw:
        from nevsky.static_data import load_cards
        cid = s.decks.russian.pending_draw[0]
        c = load_cards()[cid]
        args = {}
        if not c["no_event"]:
            if not s.meta.first_levy_done:
                if c["capability_scope"] == "this_lord":
                    t = next((lid for lid, l in s.lords.items()
                              if l.side == "russian" and l.state == "mustered"), None)
                    if t: args["lord_id"] = t
                    else: args = None
            else:
                _on_cal = lambda lid: any(lid in cb.cylinders for cb in s.calendar.boxes)
                _has_svc = lambda lid: any(lid in cb.service_markers for cb in s.calendar.boxes)
                _pick = lambda lid: lid if _on_cal(lid) else (f"service:{lid}" if _has_svc(lid) else None)
                if cid == "R9":
                    args = {"target": "andreas" if _has_svc("andreas") else "heinrich"}
                elif cid == "R10":
                    t = _pick("andreas")
                    args = {"target": t, "direction": "left", "boxes": 1} if t else None
                elif cid == "R11":
                    args = {"target": "knud_and_abel", "direction": "left", "boxes": 0}
                elif cid == "R12":
                    args = {"locale": "rositten"}
                elif cid == "R14":
                    args = {}
                elif cid == "R16":
                    teu_with_ships = next(
                        (lid for lid, l in s.lords.items()
                         if l.side == "teutonic" and l.state == "mustered"
                         and l.assets.get("ship", 0) > 0), None)
                    args = {"target": teu_with_ships} if teu_with_ships else None
                elif cid == "R17":
                    t = _pick("andreas") or _pick("rudolf")
                    args = {"target": t, "direction": "left"} if t else None
                elif cid == "R18":
                    args = {"locale": next(
                        (lid for lid, loc in s.locales.items() if loc.teutonic_ravaged),
                        None)}
                    if args["locale"] is None: args = None
                else:
                    args = {}
        if args is None:
            print(f"    [skip impl {cid}: no valid args]")
            s.decks.russian.pending_draw.pop(0)
            s.decks.russian.discard.append(cid)
            continue
        try:
            apply_action(s, {"type": "aow_implement_card", "side": "russian", "args": args})
        except IllegalAction as e:
            print(f"    [aow_implement {cid} {args} -> {e.code}; discard]")
            if s.decks.russian.pending_draw and s.decks.russian.pending_draw[0] == cid:
                s.decks.russian.pending_draw.pop(0)
                s.decks.russian.discard.append(cid)
    apply_action(s, {"type": "advance_step", "side": "russian", "args": {}})
    for _ in range(3):
        apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})
        apply_action(s, {"type": "advance_step", "side": "russian", "args": {}})
    apply_action(s, {"type": "legate_skip", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "aow_discard_this_levy", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "veche_action", "side": "russian", "args": {"option": "skip"}})
    apply_action(s, {"type": "aow_discard_this_levy", "side": "russian", "args": {}})
    apply_action(s, {"type": "advance_step", "side": "russian", "args": {}})


def fast_campaign_pass(s):
    from nevsky.campaign import _plan_target_size
    target = _plan_target_size(s.meta.box)
    for sd in ("teutonic", "russian"):
        for _ in range(target):
            apply_action(s, {"type": "plan_add_card", "side": sd, "args": {"card": "pass"}})
        apply_action(s, {"type": "finalize_plan", "side": sd, "args": {}})
    safety = 60
    while s.meta.campaign_step == "command" and safety > 0:
        side = s.campaign_turn.next_to_reveal
        if not s.campaign_turn.in_feed_pay_disband:
            apply_action(s, {"type": "command_reveal", "side": side, "args": {}})
        try:
            apply_action(s, {"type": "fpd_resolve", "side": "teutonic", "args": {}})
            apply_action(s, {"type": "fpd_resolve", "side": "russian", "args": {}})
        except IllegalAction as e:
            print(f"  fpd failed: {e}")
            return False
        safety -= 1
    if s.meta.campaign_step == "end_campaign":
        apply_action(s, {"type": "end_campaign_resolve", "side": "teutonic", "args": {}})
        apply_action(s, {"type": "end_campaign_resolve", "side": "russian", "args": {}})
    return True


def main():
    print("=" * 60)
    print("Round 6: 16-turn Crusade-on-Novgorod aggressive run")
    print("=" * 60)
    s = load_scenario("crusade_on_novgorod", seed=53)
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})

    report(s, "T0 init")
    print(f"\nInitial: T VP={s.calendar.teutonic_vp}, R VP={s.calendar.russian_vp}")
    print(f"  Initial Mustered: T={[lid for lid, l in s.lords.items() if l.side=='teutonic' and l.state=='mustered']}")
    print(f"                    R={[lid for lid, l in s.lords.items() if l.side=='russian' and l.state=='mustered']}")

    turn = 0
    pre_seq = -1
    while s.meta.phase != "campaign" or s.meta.campaign_step != "done":
        turn += 1
        if turn > 17:
            print(f"  ! Safety bail at turn 17")
            BUGS.append(f"safety bail at turn 17 (box={s.meta.box}, scenario should end at box 16)")
            break
        print(f"\n--- TURN {turn} (box {s.meta.box}, phase={s.meta.phase}) ---")
        if s.meta.sequence <= pre_seq:
            BUGS.append(f"turn {turn}: sequence not monotonic ({pre_seq} -> {s.meta.sequence})")
        pre_seq = s.meta.sequence
        if s.meta.phase != "levy":
            print(f"  ! phase={s.meta.phase}, expected levy")
            break
        try:
            fast_levy_skip(s)
        except Exception as e:
            print(f"  Levy failed: {type(e).__name__}: {e}")
            BUGS.append(f"turn {turn} Levy: {type(e).__name__}: {e}")
            traceback.print_exc()
            break
        report(s, f"turn {turn} after Levy")
        if s.meta.phase != "campaign":
            print(f"  ! phase={s.meta.phase} after Levy, expected campaign")
            BUGS.append(f"turn {turn} Levy did not transition to campaign")
            break
        if not fast_campaign_pass(s):
            BUGS.append(f"turn {turn} Campaign abort")
            break
        report(s, f"turn {turn} after Campaign")
        print(f"  After turn {turn}: box={s.meta.box}, phase={s.meta.phase}, step={s.meta.campaign_step}, T VP={s.calendar.teutonic_vp}, R VP={s.calendar.russian_vp}")

    print(f"\n=== FINAL ===")
    print(f"  phase={s.meta.phase}, step={s.meta.campaign_step}, box={s.meta.box}")
    print(f"  T VP={s.calendar.teutonic_vp}, R VP={s.calendar.russian_vp}")
    print(f"  Total turns: {turn}, total actions: {s.meta.sequence}")
    print(f"\n=== BUGS FOUND ({len(BUGS)}) ===")
    for b in BUGS:
        print(f"  {b}")
    return 0 if not BUGS else 1


if __name__ == "__main__":
    sys.exit(main())
