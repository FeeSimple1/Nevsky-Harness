"""Active-play smoke test: force a Battle to actually happen by
pre-positioning Lords adjacent."""

from __future__ import annotations

import json
import sys
import traceback

from nevsky.actions import IllegalAction, apply_action
from nevsky.scenarios import load_scenario


def step(s, action: dict) -> dict:
    try:
        res = apply_action(s, action)
        print(f"  OK {action['type']:30} -> {json.dumps(res, default=str)[:200]}")
        return res
    except IllegalAction as e:
        print(f"  IL {action['type']:30} -> {e.code}: {e}")
        raise
    except Exception as e:
        print(f"  EX {action['type']:30} -> {type(e).__name__}: {e}")
        traceback.print_exc()
        raise


def main() -> int:
    print("=" * 60)
    print("Forced combat smoke test (Pleskau, hermann -> izborsk -> pskov siege)")
    print("=" * 60)
    s = load_scenario("pleskau", seed=11)

    # Position hermann at izborsk before any moves; preserve forces.
    s.lords["hermann"].location = "izborsk"

    # Skip Levy fast.
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})
    apply_action(s, {"type": "aow_shuffle", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "aow_draw", "side": "teutonic", "args": {}})
    deck = s.decks.teutonic
    while deck.pending_draw:
        from nevsky.static_data import load_cards
        cid = deck.pending_draw[0]
        c = load_cards()[cid]
        args = {"lord_id": "hermann"} if not c["no_event"] and c["capability_scope"] == "this_lord" else {}
        apply_action(s, {"type": "aow_implement_card", "side": "teutonic", "args": args})
    apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "aow_shuffle", "side": "russian", "args": {}})
    apply_action(s, {"type": "aow_draw", "side": "russian", "args": {}})
    deck = s.decks.russian
    while deck.pending_draw:
        from nevsky.static_data import load_cards
        cid = deck.pending_draw[0]
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

    # Plan: T plays hermann 3x, R plays gavrilo 1x then passes.
    from nevsky.campaign import _plan_target_size
    target = _plan_target_size(s.meta.box)
    apply_action(s, {"type": "plan_add_card", "side": "teutonic", "args": {"card": "hermann"}})
    apply_action(s, {"type": "plan_add_card", "side": "teutonic", "args": {"card": "hermann"}})
    apply_action(s, {"type": "plan_add_card", "side": "teutonic", "args": {"card": "hermann"}})
    for _ in range(target - 3):
        apply_action(s, {"type": "plan_add_card", "side": "teutonic", "args": {"card": "pass"}})
    apply_action(s, {"type": "finalize_plan", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "plan_add_card", "side": "russian", "args": {"card": "gavrilo"}})
    apply_action(s, {"type": "plan_add_card", "side": "russian", "args": {"card": "gavrilo"}})
    for _ in range(target - 2):
        apply_action(s, {"type": "plan_add_card", "side": "russian", "args": {"card": "pass"}})
    apply_action(s, {"type": "finalize_plan", "side": "russian", "args": {}})

    print("\n=== Activation ===")
    print(f"hermann@{s.lords['hermann'].location} forces={dict(s.lords['hermann'].forces)}")
    print(f"gavrilo@{s.lords['gavrilo'].location} forces={dict(s.lords['gavrilo'].forces)}")

    # T card 1: hermann marches izborsk -> pskov (should trigger Approach with gavrilo).
    print("\n--- T card 1: hermann marches izborsk -> pskov ---")
    step(s, {"type": "command_reveal", "side": "teutonic", "args": {}})
    res = step(s, {"type": "cmd_march", "side": "teutonic",
                    "args": {"lord_id": "hermann", "to": "pskov"}})
    if s.combat_pending is not None:
        print(f"  Approach! defender={s.combat_pending.defender_lords}")
        # gavrilo (carrying loot? no) chooses Stand.
        print(f"  gavrilo Laden: {s.lords['gavrilo'].assets}")
        try:
            battle_res = step(s, {"type": "stand_battle", "side": "russian", "args": {}})
            print(f"  Battle outcome: winner={battle_res.get('winner')} loser={battle_res.get('loser')}")
            print(f"  After battle: hermann@{s.lords['hermann'].location} forces={dict(s.lords['hermann'].forces)}")
            print(f"                 gavrilo@{s.lords['gavrilo'].location} forces={dict(s.lords['gavrilo'].forces)}")
            print(f"                 gavrilo state={s.lords['gavrilo'].state}")
            print(f"  pskov.siege_markers={s.locales['pskov'].siege_markers}")
        except Exception as e:
            print(f"  Battle EXCEPTION: {type(e).__name__}: {e}")
            traceback.print_exc()

    # FPD.
    step(s, {"type": "fpd_resolve", "side": "teutonic", "args": {}})
    step(s, {"type": "fpd_resolve", "side": "russian", "args": {}})

    # If hermann won and is at pskov with siege placed, try Storm next.
    if s.lords["hermann"].state == "mustered" and s.lords["hermann"].location == "pskov":
        print(f"\n--- R card 1: gavrilo (if alive) ---")
        # Skip R's gavrilo card.
        if s.campaign_turn.next_to_reveal == "russian":
            try:
                step(s, {"type": "command_reveal", "side": "russian", "args": {}})
                if s.campaign_turn.active_lord and s.campaign_turn.actions_remaining > 0:
                    step(s, {"type": "cmd_pass", "side": "russian",
                              "args": {"lord_id": s.campaign_turn.active_lord}})
                step(s, {"type": "fpd_resolve", "side": "teutonic", "args": {}})
                step(s, {"type": "fpd_resolve", "side": "russian", "args": {}})
            except Exception as e:
                print(f"  R reveal EXCEPTION: {type(e).__name__}: {e}")
                traceback.print_exc()

        if s.lords["hermann"].state == "mustered" and s.locales["pskov"].siege_markers > 0:
            print(f"\n--- T card 2: hermann Storm pskov ---")
            try:
                step(s, {"type": "command_reveal", "side": "teutonic", "args": {}})
                storm_res = step(s, {"type": "cmd_storm", "side": "teutonic",
                                      "args": {"lord_id": "hermann"}})
                print(f"  Storm result: {storm_res.get('battle', {}).get('winner')}")
                print(f"  pskov.teutonic_conquered={s.locales['pskov'].teutonic_conquered}")
                print(f"  hermann forces after storm={dict(s.lords['hermann'].forces)}")
            except Exception as e:
                print(f"  Storm EXCEPTION: {type(e).__name__}: {e}")
                traceback.print_exc()

    print("\n=== Final state ===")
    print(f"  T VP: {s.calendar.teutonic_vp}, R VP: {s.calendar.russian_vp}")
    for lid, l in s.lords.items():
        if l.state in ("mustered",):
            print(f"  {lid:14} state={l.state:9} loc={l.location or '-':10} forces={dict(l.forces)} assets={dict(l.assets)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
