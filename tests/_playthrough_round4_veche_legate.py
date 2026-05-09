"""TEST FIXTURE / engine-soundness smoke driver — NOT part of the shipped harness.

Round 4b: Veche actions + Legate use sub-options."""

from __future__ import annotations

import json
import sys
import traceback

from nevsky.actions import IllegalAction, apply_action
from nevsky.scenarios import load_scenario


def step(s, action, *, expect_illegal=False):
    try:
        res = apply_action(s, action)
        head = json.dumps(res, default=str)[:200]
        print(f"  OK {action['type']:30} -> {head}")
        return res
    except IllegalAction as e:
        if expect_illegal:
            print(f"  IL_OK {action['type']:30} -> {e.code}")
            return None
        print(f"  IL_BAD {action['type']:30} -> {e.code}: {e}")
        raise


def main() -> int:
    print("=" * 60)
    print("Round 4b: Veche actions + Legate use (RotP)")
    print("=" * 60)
    s = load_scenario("return_of_the_prince", seed=11)

    print(f"\n[Setup] Veche state: vp={s.veche.vp_markers}, coin={s.veche.coin}")
    print(f"  aleksandr state: {s.lords['aleksandr'].state}, andrey state: {s.lords['andrey'].state}")
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})

    # Skip Levy fast.
    apply_action(s, {"type": "aow_shuffle", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "aow_draw", "side": "teutonic", "args": {}})
    while s.decks.teutonic.pending_draw:
        from nevsky.static_data import load_cards
        cid = s.decks.teutonic.pending_draw[0]
        c = load_cards()[cid]
        args = {"lord_id": "andreas"} if not c["no_event"] and c["capability_scope"] == "this_lord" else {}
        apply_action(s, {"type": "aow_implement_card", "side": "teutonic", "args": args})
    apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "aow_shuffle", "side": "russian", "args": {}})
    apply_action(s, {"type": "aow_draw", "side": "russian", "args": {}})
    while s.decks.russian.pending_draw:
        from nevsky.static_data import load_cards
        cid = s.decks.russian.pending_draw[0]
        c = load_cards()[cid]
        args = {"lord_id": "aleksandr"} if not c["no_event"] and c["capability_scope"] == "this_lord" else {}
        apply_action(s, {"type": "aow_implement_card", "side": "russian", "args": args})
    apply_action(s, {"type": "advance_step", "side": "russian", "args": {}})
    for _ in range(3):
        apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})
        apply_action(s, {"type": "advance_step", "side": "russian", "args": {}})

    # ===== TEST: Legate Arrives (T13 William of Modena required) =====
    print(f"\n[CtA T] Force William of Modena in play; place Legate at Riga")
    s.legate.william_of_modena_in_play = True
    s.legate.location = "card"
    if "T13" not in s.decks.teutonic.capabilities_in_play:
        s.decks.teutonic.capabilities_in_play.append("T13")

    res = step(s, {"type": "legate_arrives", "side": "teutonic", "args": {"bishopric": "riga"}})
    print(f"  Legate at: {s.legate.locale_id}")

    # Test Legate Use sub-option 2c at Riga (Andreas at Riga? Let me check)
    print(f"  Lords at riga: {[lid for lid, l in s.lords.items() if l.location == 'riga']}")
    riga_lord = next((lid for lid, l in s.lords.items() if l.side == "teutonic" and l.location == "riga"), None)
    if riga_lord:
        print(f"  Try Legate USE 2c on {riga_lord} (extra Muster)")
        step(s, {"type": "legate_use", "side": "teutonic",
                  "args": {"sub_option": "2c", "target_lord": riga_lord}})
        print(f"  After Legate USE 2c: {riga_lord}.lordship_used={s.lords[riga_lord].lordship_used}")
    else:
        print(f"  No T Lord at riga; skipping Legate 2c")
        step(s, {"type": "legate_skip", "side": "teutonic", "args": {}})

    apply_action(s, {"type": "aow_discard_this_levy", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})

    # ===== Russian CtA: Veche options =====
    print(f"\n[CtA R] Veche state: vp={s.veche.vp_markers}, coin={s.veche.coin}")
    # Try Decline first.
    print(f"  aleksandr cyl pos: {[cb.box for cb in s.calendar.boxes if 'aleksandr' in cb.cylinders]}")
    print(f"  andrey cyl pos: {[cb.box for cb in s.calendar.boxes if 'andrey' in cb.cylinders]}")
    levy_box = next(cb.box for cb in s.calendar.boxes if cb.has_levy_campaign_marker)
    print(f"  levy box = {levy_box}")
    # Decline available iff aleksandr or andrey is Ready.
    pre_vp = s.veche.vp_markers
    res = step(s, {"type": "veche_action", "side": "russian", "args": {"option": "D"}}, expect_illegal=True)
    if res is None:
        # Skip if Decline not available.
        print(f"  Decline unavailable; skipping")
        step(s, {"type": "veche_action", "side": "russian", "args": {"option": "skip"}})
    else:
        print(f"  After Decline: vp={s.veche.vp_markers}, slid={res.get('slid')}")

    apply_action(s, {"type": "aow_discard_this_levy", "side": "russian", "args": {}})
    apply_action(s, {"type": "advance_step", "side": "russian", "args": {}})

    print(f"\n=== After CtA: phase={s.meta.phase}, campaign_step={s.meta.campaign_step}")
    print(f"  Veche: vp={s.veche.vp_markers}, coin={s.veche.coin}")
    print(f"  Legate location={s.legate.location} locale={s.legate.locale_id}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
