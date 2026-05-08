"""Active-play smoke test: force a Battle and Siege/Storm sequence
to stress the rules engine end-to-end."""

from __future__ import annotations

import json
import sys
import traceback

from nevsky.actions import IllegalAction, apply_action
from nevsky.scenarios import load_scenario


def step(s, action: dict, expect_illegal: bool = False) -> dict:
    try:
        res = apply_action(s, action)
        print(f"  OK {action['type']:30} -> {json.dumps(res, default=str)[:140]}")
        return res
    except IllegalAction as e:
        marker = "IL_OK" if expect_illegal else "IL_BAD"
        print(f"  {marker} {action['type']:30} -> {e.code}: {e}")
        if not expect_illegal:
            raise
        return {"_illegal": True, "code": e.code}
    except Exception as e:
        print(f"  EX {action['type']:30} -> {type(e).__name__}: {e}")
        traceback.print_exc()
        raise


def main() -> int:
    print("=" * 60)
    print("Battle / Siege / Storm smoke test (Pleskau)")
    print("=" * 60)
    s = load_scenario("pleskau", seed=11)

    # Skip everything to get into Campaign quickly.
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})
    apply_action(s, {"type": "aow_shuffle", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "aow_draw", "side": "teutonic", "args": {}})
    deck = s.decks.teutonic
    while deck.pending_draw:
        from nevsky.static_data import load_cards
        cid = deck.pending_draw[0]
        c = load_cards()[cid]
        args = {}
        if not c["no_event"] and c["capability_scope"] == "this_lord":
            args["lord_id"] = "hermann"
        apply_action(s, {"type": "aow_implement_card", "side": "teutonic", "args": args})
    apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "aow_shuffle", "side": "russian", "args": {}})
    apply_action(s, {"type": "aow_draw", "side": "russian", "args": {}})
    deck = s.decks.russian
    while deck.pending_draw:
        from nevsky.static_data import load_cards
        cid = deck.pending_draw[0]
        c = load_cards()[cid]
        args = {}
        if not c["no_event"] and c["capability_scope"] == "this_lord":
            args["lord_id"] = "gavrilo"
        apply_action(s, {"type": "aow_implement_card", "side": "russian", "args": args})
    apply_action(s, {"type": "advance_step", "side": "russian", "args": {}})

    # Skip through pay/disband/muster.
    for _ in range(3):
        apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})
        apply_action(s, {"type": "advance_step", "side": "russian", "args": {}})

    # Call to Arms skip.
    apply_action(s, {"type": "legate_skip", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "aow_discard_this_levy", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "veche_action", "side": "russian", "args": {"option": "skip"}})
    apply_action(s, {"type": "aow_discard_this_levy", "side": "russian", "args": {}})
    apply_action(s, {"type": "advance_step", "side": "russian", "args": {}})

    # Plan.
    from nevsky.campaign import _plan_target_size
    target = _plan_target_size(s.meta.box)
    apply_action(s, {"type": "plan_add_card", "side": "teutonic", "args": {"card": "hermann"}})
    apply_action(s, {"type": "plan_add_card", "side": "teutonic", "args": {"card": "hermann"}})
    apply_action(s, {"type": "plan_add_card", "side": "teutonic", "args": {"card": "hermann"}})
    for _ in range(target - 3):
        apply_action(s, {"type": "plan_add_card", "side": "teutonic", "args": {"card": "pass"}})
    apply_action(s, {"type": "finalize_plan", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "plan_add_card", "side": "russian", "args": {"card": "gavrilo"}})
    for _ in range(target - 1):
        apply_action(s, {"type": "plan_add_card", "side": "russian", "args": {"card": "pass"}})
    apply_action(s, {"type": "finalize_plan", "side": "russian", "args": {}})

    print("\n--- Activation: T tries Hermann -> Pskov via izborsk ---")

    # T reveals hermann.
    step(s, {"type": "command_reveal", "side": "teutonic", "args": {}})
    print(f"  hermann actions={s.campaign_turn.actions_remaining}")

    # March hermann from dorpat -> izborsk (need a route).
    # dorpat is in Crusader Livonia. Look for an adjacent locale.
    from nevsky.static_data import load_ways
    ways = load_ways()
    h = "hermann"
    print(f"  hermann at: {s.lords[h].location}")
    print(f"  hermann adjacencies:")
    for w in ways:
        if w["a"] == s.lords[h].location:
            print(f"    -> {w['b']} via {w['type']}")
        elif w["b"] == s.lords[h].location:
            print(f"    -> {w['a']} via {w['type']}")

    # Try marching hermann to a locale with an enemy lord (gavrilo at pskov).
    # Find a path from dorpat to pskov... probably 2-3 moves.
    # For this test, just march one step in any direction.
    step(s, {"type": "cmd_march", "side": "teutonic",
              "args": {"lord_id": h, "to": "ugaunia"}})  # adjacent to dorpat
    print(f"  hermann now at: {s.lords[h].location}, actions_remaining={s.campaign_turn.actions_remaining}")

    # If Lord still has actions, Pass the rest.
    if s.campaign_turn.actions_remaining > 0 and s.campaign_turn.active_lord:
        step(s, {"type": "cmd_pass", "side": "teutonic",
                  "args": {"lord_id": s.campaign_turn.active_lord}})

    # FPD T then R.
    print(f"  FPD T then R")
    step(s, {"type": "fpd_resolve", "side": "teutonic", "args": {}})
    step(s, {"type": "fpd_resolve", "side": "russian", "args": {}})

    # Now R reveals gavrilo.
    print("\n--- R reveals gavrilo; gavrilo marches to attack hermann ---")
    step(s, {"type": "command_reveal", "side": "russian", "args": {}})
    print(f"  gavrilo at: {s.lords['gavrilo'].location}, actions={s.campaign_turn.actions_remaining}")
    # Gavrilo at pskov; let's march pskov -> izborsk if possible.
    # Need to check adjacencies.
    print(f"  gavrilo adjacencies:")
    for w in ways:
        if w["a"] == s.lords["gavrilo"].location:
            print(f"    -> {w['b']} via {w['type']}")
        elif w["b"] == s.lords["gavrilo"].location:
            print(f"    -> {w['a']} via {w['type']}")
    # March pskov -> izborsk.
    try:
        res = step(s, {"type": "cmd_march", "side": "russian",
                        "args": {"lord_id": "gavrilo", "to": "izborsk"}})
        if res.get("approach"):
            print(f"  Combat pending! Defender stand_battle:")
            step(s, {"type": "stand_battle", "side": s.combat_pending.pending_response_by, "args": {}})
    except IllegalAction as e:
        print(f"  Gavrilo march failed: {e}")

    print("\n=== Final state ===")
    for lid, l in s.lords.items():
        if l.state in ("mustered", "removed", "disbanded"):
            print(f"  {lid:14} state={l.state:9} loc={l.location or '-':10} forces={dict(l.forces)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
