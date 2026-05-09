"""TEST FIXTURE / engine-soundness smoke driver — NOT part of the shipped harness.

Round 4 smoke test: Sack-by-Storm + Lieutenants + Veche actions."""

from __future__ import annotations

import json
import sys
import traceback

from nevsky.actions import IllegalAction, apply_action
from nevsky.scenarios import load_scenario


def step(s, action, *, expect_illegal=False):
    try:
        res = apply_action(s, action)
        head = json.dumps(res, default=str)[:160]
        print(f"  OK {action['type']:30} -> {head}")
        return res
    except IllegalAction as e:
        if expect_illegal:
            print(f"  IL_OK {action['type']:30} -> {e.code}")
            return None
        print(f"  IL_BAD {action['type']:30} -> {e.code}: {e}")
        raise
    except Exception as e:
        print(f"  EX {action['type']:30} -> {type(e).__name__}: {e}")
        traceback.print_exc()
        raise


def main() -> int:
    print("=" * 60)
    print("Round 4 smoke: Sack-by-Storm at Pskov + Lieutenants + Veche")
    print("=" * 60)
    s = load_scenario("pleskau", seed=29)

    # ===== TEST 1: Lieutenants pairing during Plan =====
    print("\n--- Setup: skip Levy 1 ---")
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})
    # Skip Levy fast.
    apply_action(s, {"type": "aow_shuffle", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "aow_draw", "side": "teutonic", "args": {}})
    while s.decks.teutonic.pending_draw:
        from nevsky.static_data import load_cards
        cid = s.decks.teutonic.pending_draw[0]
        c = load_cards()[cid]
        args = {"lord_id": "hermann"} if not c["no_event"] and c["capability_scope"] == "this_lord" else {}
        apply_action(s, {"type": "aow_implement_card", "side": "teutonic", "args": args})
    apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "aow_shuffle", "side": "russian", "args": {}})
    apply_action(s, {"type": "aow_draw", "side": "russian", "args": {}})
    while s.decks.russian.pending_draw:
        from nevsky.static_data import load_cards
        cid = s.decks.russian.pending_draw[0]
        c = load_cards()[cid]
        args = {"lord_id": "gavrilo"} if not c["no_event"] and c["capability_scope"] == "this_lord" else {}
        apply_action(s, {"type": "aow_implement_card", "side": "russian", "args": args})
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

    # Pre-position: hermann + yaroslav + knud_and_abel all at izborsk, ready to Storm pskov.
    s.lords["hermann"].location = "izborsk"
    s.lords["yaroslav"].location = "izborsk"
    s.lords["knud_and_abel"].location = "izborsk"
    # Pre-position Russian gavrilo at pskov in_stronghold (Besieged from siege).
    s.lords["gavrilo"].location = "pskov"
    s.lords["gavrilo"].in_stronghold = True
    s.locales["pskov"].siege_markers = 3  # 3 markers in place

    print(f"\n[Plan] Lieutenants: knud_and_abel serves under yaroslav at izborsk\n"
          f"  (Hermann is secondary Marshal active in Pleskau -> can't be Lieutenant per Q-003)")
    # Test 1: Try place_lieutenant during Plan.
    from nevsky.campaign import _plan_target_size
    target = _plan_target_size(s.meta.box)
    res = step(s, {"type": "place_lieutenant", "side": "teutonic",
                    "args": {"lieutenant": "yaroslav", "lower_lord": "knud_and_abel"}})
    assert s.lords["knud_and_abel"].lieutenant_of == "yaroslav"
    assert s.lords["yaroslav"].has_lower_lord == "knud_and_abel"

    # Plan: hermann x2, yaroslav x1 (will resolve as Pass), then 3 Pass.
    # Plan target = 6 (Summer, Pleskau).
    apply_action(s, {"type": "plan_add_card", "side": "teutonic", "args": {"card": "hermann"}})
    apply_action(s, {"type": "plan_add_card", "side": "teutonic", "args": {"card": "hermann"}})
    apply_action(s, {"type": "plan_add_card", "side": "teutonic", "args": {"card": "yaroslav"}})
    for _ in range(target - 3):
        apply_action(s, {"type": "plan_add_card", "side": "teutonic", "args": {"card": "pass"}})
    apply_action(s, {"type": "finalize_plan", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "plan_add_card", "side": "russian", "args": {"card": "gavrilo"}})
    for _ in range(target - 1):
        apply_action(s, {"type": "plan_add_card", "side": "russian", "args": {"card": "pass"}})
    apply_action(s, {"type": "finalize_plan", "side": "russian", "args": {}})

    # ===== TEST 2: T card 1 - hermann Storms pskov (group: hermann + group at locale) =====
    print(f"\n[T card 1] hermann Storm pskov (3 attackers vs 1 defender + Garrison)")
    step(s, {"type": "command_reveal", "side": "teutonic", "args": {}})
    print(f"  hermann actions={s.campaign_turn.actions_remaining}")
    # First, hermann needs to march from izborsk to pskov to begin a Storm.
    # Actually since gavrilo is in_stronghold and siege_markers > 0 already,
    # the besiegers need to BE at pskov. Let me move them there directly.
    s.lords["hermann"].location = "pskov"
    s.lords["yaroslav"].location = "pskov"
    s.lords["knud_and_abel"].location = "pskov"
    pre_t_vp = s.calendar.teutonic_vp
    pre_pskov_conq = s.locales["pskov"].russian_conquered
    storm_res = step(s, {"type": "cmd_storm", "side": "teutonic",
                          "args": {"lord_id": "hermann"}})
    print(f"  Storm winner: {storm_res['battle']['winner']}")
    print(f"  pskov.teutonic_conquered={s.locales['pskov'].teutonic_conquered}")
    print(f"  pskov.russian_conquered={s.locales['pskov'].russian_conquered}")
    print(f"  pskov.siege_markers={s.locales['pskov'].siege_markers}")
    print(f"  T VP: {pre_t_vp} -> {s.calendar.teutonic_vp}")
    print(f"  hermann assets after: {dict(s.lords['hermann'].assets)}")
    print(f"  gavrilo state: {s.lords['gavrilo'].state}")

    # FPD.
    step(s, {"type": "fpd_resolve", "side": "teutonic", "args": {}})
    step(s, {"type": "fpd_resolve", "side": "russian", "args": {}})

    # ===== TEST 3: R reveals gavrilo (removed) -> auto-pass =====
    print(f"\n[R card 1] gavrilo reveal (should pass since removed)")
    step(s, {"type": "command_reveal", "side": "russian", "args": {}})
    print(f"  outcome: active_lord={s.campaign_turn.active_lord}")
    step(s, {"type": "fpd_resolve", "side": "teutonic", "args": {}})
    step(s, {"type": "fpd_resolve", "side": "russian", "args": {}})

    # ===== TEST 4: T card 2 - hermann (Pass) + yaroslav reveal as Lower Lord =====
    print(f"\n[T card 2] yaroslav (lower lord) reveal (should pass)")
    while s.meta.campaign_step == "command":
        side = s.campaign_turn.next_to_reveal
        if not s.campaign_turn.in_feed_pay_disband:
            res = step(s, {"type": "command_reveal", "side": side, "args": {}})
            outcome = res.get("outcome")
            if outcome == "pass_lower_lord":
                print(f"  Lower-Lord pass: {res.get('lieutenant_of')} carries it")
            elif outcome == "active":
                if s.campaign_turn.active_lord and s.campaign_turn.actions_remaining > 0:
                    step(s, {"type": "cmd_pass", "side": side,
                              "args": {"lord_id": s.campaign_turn.active_lord}})
        step(s, {"type": "fpd_resolve", "side": "teutonic", "args": {}})
        step(s, {"type": "fpd_resolve", "side": "russian", "args": {}})

    # ===== TEST 5: end_campaign_resolve unstacks Lieutenants =====
    print(f"\n[End Campaign]")
    if s.meta.campaign_step == "end_campaign":
        step(s, {"type": "end_campaign_resolve", "side": "teutonic", "args": {}})
        step(s, {"type": "end_campaign_resolve", "side": "russian", "args": {}})
    print(f"  After EOC: hermann.has_lower_lord={s.lords['hermann'].has_lower_lord}")
    print(f"  yaroslav.lieutenant_of={s.lords['yaroslav'].lieutenant_of}")

    print("\n=== Final state ===")
    print(f"  T VP: {s.calendar.teutonic_vp}, R VP: {s.calendar.russian_vp}")
    for lid, l in s.lords.items():
        if l.state in ("mustered", "removed"):
            print(f"  {lid:14} state={l.state:9} loc={l.location or '-':10} forces={dict(l.forces)} assets={dict(l.assets)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
