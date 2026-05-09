"""TEST FIXTURE / engine-soundness smoke driver — NOT part of the shipped harness.

Round 3 smoke test: 5-turn Watland (boxes 4-8) playthrough.

Crosses:
  Box 4 Early Winter
  Box 5 Late Winter
  Box 6 Late Winter -- last LW -> Plow & Reap (Sleds -> Carts)
  Box 7 Rasputitsa
  Box 8 Rasputitsa  -- last Rasputitsa -> Grow + game end

Goal: surface bugs at phase boundaries (Calendar advance, season transitions,
Plow & Reap, Grow, Service-marker carry-over, asset Wastage, Levy ->
Campaign -> Levy cycle integrity).
"""

from __future__ import annotations

import json
import sys
import traceback

from nevsky.actions import IllegalAction, apply_action
from nevsky.scenarios import load_scenario


def step(s, action, *, expect_illegal=False, quiet=False):
    try:
        res = apply_action(s, action)
        if not quiet:
            head = json.dumps(res, default=str)[:160]
            print(f"  OK {action['type']:30} -> {head}")
        return res
    except IllegalAction as e:
        if expect_illegal:
            return None
        print(f"  IL {action['type']:30} -> {e.code}: {e}")
        raise
    except Exception as e:
        print(f"  EX {action['type']:30} -> {type(e).__name__}: {e}")
        traceback.print_exc()
        raise


def show_calendar(s):
    print("  Calendar:")
    for cb in s.calendar.boxes:
        marks = []
        if cb.has_levy_campaign_marker:
            marks.append(f"[{cb.levy_campaign_face}]")
        if cb.cylinders:
            marks.append("cyl=" + ",".join(cb.cylinders))
        if cb.service_markers:
            marks.append("svc=" + ",".join(cb.service_markers))
        if cb.russian_victory_marker:
            marks.append("R-VP")
        if cb.teutonic_victory_marker:
            marks.append("T-VP")
        if marks:
            print(f"    box{cb.box:2}: {' '.join(marks)}")
    if s.calendar.off_left:
        print(f"    off_left: {s.calendar.off_left}")
    if s.calendar.off_right:
        print(f"    off_right: {s.calendar.off_right}")


def show_lords(s, label):
    print(f"  {label}:")
    for lid, l in s.lords.items():
        if l.state == "mustered":
            forces = ",".join(f"{k}{v}" for k, v in l.forces.items() if v)
            assets = ",".join(f"{k}{v}" for k, v in l.assets.items() if v)
            extra = " in_stronghold" if l.in_stronghold else ""
            print(f"    {lid:14} {l.side:8} @ {l.location or '-':10} {forces:40} | {assets}{extra}")
        elif l.state == "disbanded":
            print(f"    {lid:14} disbanded")
        elif l.state == "removed":
            print(f"    {lid:14} REMOVED")


def run_levy_skip(s):
    """Skip Levy: AoW shuffle/draw/implement, advance, advance, ..."""
    # T side.
    apply_action(s, {"type": "aow_shuffle", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "aow_draw", "side": "teutonic", "args": {}})
    while s.decks.teutonic.pending_draw:
        from nevsky.static_data import load_cards
        cid = s.decks.teutonic.pending_draw[0]
        c = load_cards()[cid]
        args = {}
        if not c["no_event"]:
            if not s.meta.first_levy_done:
                # First Levy implements as capability; this_lord requires lord_id.
                if c["capability_scope"] == "this_lord":
                    args["lord_id"] = next(
                        (lid for lid, l in s.lords.items()
                         if l.side == "teutonic" and l.state == "mustered"),
                        None,
                    )
                    if args["lord_id"] is None:
                        # No mustered Teu lord; fall through (may error).
                        args = {}
            else:
                def _on_calendar_t(lid):
                    if lid not in s.lords:
                        return False
                    if lid in s.calendar.off_left or lid in s.calendar.off_right:
                        return True
                    return any(lid in cb.cylinders for cb in s.calendar.boxes)
                def _has_service_t(lid):
                    if lid not in s.lords:
                        return False
                    if lid in s.calendar.off_right:
                        return True
                    return any(lid in cb.service_markers for cb in s.calendar.boxes)
                def _pick_t(lid):
                    if _on_calendar_t(lid):
                        return lid
                    if _has_service_t(lid):
                        return f"service:{lid}"
                    return None
                if cid == "T1":
                    t = _pick_t("aleksandr") or _pick_t("andrey")
                    args = {"target": t, "direction": "left"} if t else {}
                elif cid == "T2":
                    args = {"target": "veche"}
                elif cid == "T11":
                    t = next((lid for lid, l in s.lords.items()
                              if l.side == "teutonic" and _on_calendar_t(lid)), None)
                    args = {"target": t} if t else {}
                elif cid == "T12":
                    t = _pick_t("aleksandr") or _pick_t("andrey")
                    args = {"target": t, "direction": "left"} if t else {}
                elif cid == "T14":
                    args = {"locale": next(
                        (lid for lid, loc in s.locales.items() if loc.russian_ravaged),
                        "harrien")}
                elif cid == "T15":
                    args = {"locale": "ostrov"}
                elif cid == "T18":
                    targets = {}
                    if _on_calendar_t("vladislav"):
                        targets["vladislav"] = "cylinder"
                    elif _has_service_t("vladislav"):
                        targets["vladislav"] = "service"
                    if _on_calendar_t("karelians"):
                        targets["karelians"] = "cylinder"
                    elif _has_service_t("karelians"):
                        targets["karelians"] = "service"
                    args = {"direction": "left", "targets": targets} if targets else {}
        try:
            apply_action(s, {"type": "aow_implement_card", "side": "teutonic", "args": args})
        except IllegalAction as e:
            # Some events can fail (no R Ravaged to remove, etc.); discard manually.
            print(f"    aow_implement_card({cid}) failed: {e.code}; manually discarding")
            s.decks.teutonic.pending_draw.pop(0)
            s.decks.teutonic.discard.append(cid)
    apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})

    # R side.
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
                    args["lord_id"] = next(
                        (lid for lid, l in s.lords.items()
                         if l.side == "russian" and l.state == "mustered"),
                        None,
                    )
                    if args["lord_id"] is None:
                        args = {}
            else:
                # Smart args picker: prefer service-marker shifts when the
                # cylinder isn't on the Calendar, etc.
                def _on_calendar(lord_id):
                    if lord_id not in s.lords:
                        return False
                    if lord_id in s.calendar.off_left or lord_id in s.calendar.off_right:
                        return True
                    return any(lord_id in cb.cylinders for cb in s.calendar.boxes)
                def _has_service(lord_id):
                    if lord_id not in s.lords:
                        return False
                    if lord_id in s.calendar.off_right:
                        return True
                    return any(lord_id in cb.service_markers for cb in s.calendar.boxes)
                def _pick_target(lord_id):
                    if _on_calendar(lord_id):
                        return lord_id
                    if _has_service(lord_id):
                        return f"service:{lord_id}"
                    return None
                if cid == "R9":
                    args = {"target": "andreas" if _has_service("andreas") else "heinrich"}
                elif cid == "R10":
                    t = _pick_target("andreas")
                    args = {"target": t, "direction": "left", "boxes": 1} if t else {}
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
                         and l.assets.get("ship", 0) > 0),
                        next(lid for lid, l in s.lords.items()
                             if l.side == "teutonic" and l.state == "mustered"),
                    )
                    args = {"target": teu_with_ships}
                elif cid == "R17":
                    t = _pick_target("andreas") or _pick_target("rudolf")
                    args = {"target": t, "direction": "left"} if t else {}
                elif cid == "R18":
                    args = {"locale": next(
                        (lid for lid, loc in s.locales.items() if loc.teutonic_ravaged),
                        "tesovo")}
        try:
            apply_action(s, {"type": "aow_implement_card", "side": "russian", "args": args})
        except IllegalAction as e:
            print(f"    aow_implement_card({cid}) failed: {e.code}; manually discarding")
            s.decks.russian.pending_draw.pop(0)
            s.decks.russian.discard.append(cid)
    apply_action(s, {"type": "advance_step", "side": "russian", "args": {}})

    # Pay (skip).
    apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "advance_step", "side": "russian", "args": {}})

    # Disband.
    apply_action(s, {"type": "disband_resolve", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "disband_resolve", "side": "russian", "args": {}})
    apply_action(s, {"type": "advance_step", "side": "russian", "args": {}})

    # Muster (skip - try later if needed).
    apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "advance_step", "side": "russian", "args": {}})

    # CtA.
    apply_action(s, {"type": "legate_skip", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "aow_discard_this_levy", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "veche_action", "side": "russian", "args": {"option": "skip"}})
    apply_action(s, {"type": "aow_discard_this_levy", "side": "russian", "args": {}})
    apply_action(s, {"type": "advance_step", "side": "russian", "args": {}})


def run_campaign_pass_all(s):
    """Plan all-pass; loop activation; run end-of-Campaign."""
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
            print(f"  fpd_resolve failed: {e}")
            break
        safety -= 1

    if s.meta.campaign_step == "end_campaign":
        apply_action(s, {"type": "end_campaign_resolve", "side": "teutonic", "args": {}})
        apply_action(s, {"type": "end_campaign_resolve", "side": "russian", "args": {}})


def main() -> int:
    print("=" * 60)
    print("Round 3 multi-turn smoke test (Watland, boxes 4-8)")
    print("=" * 60)
    s = load_scenario("watland", seed=23)
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})

    pre_total_assets_t = sum(
        sum(l.assets.values())
        for l in s.lords.values()
        if l.side == "teutonic" and l.state == "mustered"
    )
    print(f"\nInitial T-side total assets (sum across mustered Teu lords): {pre_total_assets_t}")
    show_calendar(s)
    show_lords(s, "Lords at scenario start")

    turn = 0
    while s.meta.phase != "campaign" or s.meta.campaign_step != "done":
        turn += 1
        print(f"\n========== TURN {turn} (box {s.meta.box}) ==========")
        if s.meta.phase != "levy":
            print(f"  Already past Levy? phase={s.meta.phase}, step={s.meta.campaign_step}")
            break
        try:
            run_levy_skip(s)
        except Exception as e:
            print(f"  Levy failed: {type(e).__name__}: {e}")
            traceback.print_exc()
            break
        if s.meta.phase != "campaign":
            print(f"  Levy didn't transition to Campaign? phase={s.meta.phase}")
            break
        try:
            run_campaign_pass_all(s)
        except Exception as e:
            print(f"  Campaign failed: {type(e).__name__}: {e}")
            traceback.print_exc()
            break
        print(f"  After turn {turn}: box={s.meta.box} phase={s.meta.phase} step={s.meta.campaign_step}")
        show_lords(s, f"Lords after turn {turn}")
        if turn > 8:
            print("  Safety bail at 8 turns")
            break

    print(f"\n=== FINAL ===")
    print(f"  phase={s.meta.phase}, campaign_step={s.meta.campaign_step}, box={s.meta.box}")
    print(f"  T VP: {s.calendar.teutonic_vp}, R VP: {s.calendar.russian_vp}")
    show_calendar(s)
    show_lords(s, "Final Lords")
    print(f"  Total turns played: {turn}")
    print(f"  Sequence: {s.meta.sequence}, history len: {len(s.history)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
