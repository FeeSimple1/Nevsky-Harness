"""TEST FIXTURE / engine-soundness smoke driver — NOT part of the shipped harness.

Second smoke pass: force Storm + try Veche actions + multi-Lord plan.
Goal: surface bugs not exposed by the first smoke pass."""

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
        marker = "IL_OK" if expect_illegal else "IL_BAD"
        print(f"  {marker} {action['type']:30} -> {e.code}: {e}")
        if not expect_illegal:
            raise
        return None
    except Exception as e:
        print(f"  EX {action['type']:30} -> {type(e).__name__}: {e}")
        traceback.print_exc()
        raise


def main() -> int:
    print("=" * 60)
    print("Storm + Veche smoke pass (Watland)")
    print("=" * 60)
    s = load_scenario("watland", seed=23)

    # Set up: place a Russian Lord besieged inside Pskov-stronghold
    # so we can test Storm. Watland scenario: pskov is Conquered (Teu)
    # at start. Move andreas to pskov as besieger (he's Teu) and put
    # gavrilo at pskov as defender? No — we need defender INSIDE the
    # stronghold. Let's restructure:
    #
    # gavrilo (Russian) sits at pskov in_stronghold=True; the Stronghold
    # type is "city" with Russian-side garrison. But pskov starts
    # Teutonic-Conquered in Watland. For Storm, attacker needs to be
    # opposite-side from stronghold ownership. Since pskov is
    # Teu-Conquered, gavrilo besieging it would be Russian.
    #
    # Simpler: use Pleskau where pskov is Russian and Teu can attack.
    s2 = load_scenario("pleskau", seed=23)

    # Skip Levy fast.
    apply_action(s2, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    apply_action(s2, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})
    apply_action(s2, {"type": "aow_shuffle", "side": "teutonic", "args": {}})
    apply_action(s2, {"type": "aow_draw", "side": "teutonic", "args": {}})
    while s2.decks.teutonic.pending_draw:
        from nevsky.static_data import load_cards
        cid = s2.decks.teutonic.pending_draw[0]
        c = load_cards()[cid]
        args = {"lord_id": "hermann"} if not c["no_event"] and c["capability_scope"] == "this_lord" else {}
        apply_action(s2, {"type": "aow_implement_card", "side": "teutonic", "args": args})
    apply_action(s2, {"type": "advance_step", "side": "teutonic", "args": {}})
    apply_action(s2, {"type": "aow_shuffle", "side": "russian", "args": {}})
    apply_action(s2, {"type": "aow_draw", "side": "russian", "args": {}})
    while s2.decks.russian.pending_draw:
        from nevsky.static_data import load_cards
        cid = s2.decks.russian.pending_draw[0]
        c = load_cards()[cid]
        args = {"lord_id": "gavrilo"} if not c["no_event"] and c["capability_scope"] == "this_lord" else {}
        apply_action(s2, {"type": "aow_implement_card", "side": "russian", "args": args})
    apply_action(s2, {"type": "advance_step", "side": "russian", "args": {}})
    for _ in range(3):
        apply_action(s2, {"type": "advance_step", "side": "teutonic", "args": {}})
        apply_action(s2, {"type": "advance_step", "side": "russian", "args": {}})

    print("\n--- Russian CtA: try Veche options ---")
    apply_action(s2, {"type": "legate_skip", "side": "teutonic", "args": {}})
    apply_action(s2, {"type": "aow_discard_this_levy", "side": "teutonic", "args": {}})
    apply_action(s2, {"type": "advance_step", "side": "teutonic", "args": {}})
    # R Veche has VP markers? Check.
    print(f"  veche.vp_markers={s2.veche.vp_markers}, coin={s2.veche.coin}")
    # Pleskau starts with VP markers -- try Decline first.
    print(f"  aleksandr state={s2.lords['aleksandr'].state}, andrey state={s2.lords['andrey'].state}")
    # In Pleskau, aleksandr/andrey are removed. So Decline unavailable.
    # Try sea_trade (R8 not in play -> should fail).
    step(s2, {"type": "veche_action", "side": "russian",
              "args": {"option": "sea_trade", "card_id": "R8"}}, expect_illegal=True)
    step(s2, {"type": "veche_action", "side": "russian", "args": {"option": "skip"}})
    apply_action(s2, {"type": "aow_discard_this_levy", "side": "russian", "args": {}})
    apply_action(s2, {"type": "advance_step", "side": "russian", "args": {}})

    # Plan & Activation — set up a Storm scenario.
    # Pre-place hermann at izborsk; he'll march to pskov, gavrilo Withdraws inside.
    s2.lords["hermann"].location = "izborsk"
    # Add another Teu Lord co-located so siege capacity (=3 for pskov city) is met.
    s2.lords["yaroslav"].location = "izborsk"
    s2.lords["knud_and_abel"].location = "izborsk"

    from nevsky.campaign import _plan_target_size
    target = _plan_target_size(s2.meta.box)
    apply_action(s2, {"type": "plan_add_card", "side": "teutonic", "args": {"card": "hermann"}})
    apply_action(s2, {"type": "plan_add_card", "side": "teutonic", "args": {"card": "hermann"}})
    apply_action(s2, {"type": "plan_add_card", "side": "teutonic", "args": {"card": "hermann"}})
    for _ in range(target - 3):
        apply_action(s2, {"type": "plan_add_card", "side": "teutonic", "args": {"card": "pass"}})
    apply_action(s2, {"type": "finalize_plan", "side": "teutonic", "args": {}})
    apply_action(s2, {"type": "plan_add_card", "side": "russian", "args": {"card": "gavrilo"}})
    for _ in range(target - 1):
        apply_action(s2, {"type": "plan_add_card", "side": "russian", "args": {"card": "pass"}})
    apply_action(s2, {"type": "finalize_plan", "side": "russian", "args": {}})

    print("\n--- T card 1: hermann marches izborsk -> pskov; gavrilo Withdraws ---")
    step(s2, {"type": "command_reveal", "side": "teutonic", "args": {}})
    # Group march hermann + yaroslav + knud&abel.
    step(s2, {"type": "cmd_march", "side": "teutonic",
              "args": {"lord_id": "hermann", "to": "pskov",
                       "group": ["hermann", "yaroslav", "knud_and_abel"]}})
    if s2.combat_pending:
        # gavrilo Withdraws into pskov.
        step(s2, {"type": "withdraw", "side": "russian", "args": {}})
    print(f"  gavrilo in_stronghold={s2.lords['gavrilo'].in_stronghold}, pskov.siege_markers={s2.locales['pskov'].siege_markers}")

    # FPD T then R.
    step(s2, {"type": "fpd_resolve", "side": "teutonic", "args": {}})
    step(s2, {"type": "fpd_resolve", "side": "russian", "args": {}})

    # R card 1: gavrilo is Besieged; try Sally.
    print("\n--- R card 1: gavrilo Sally ---")
    step(s2, {"type": "command_reveal", "side": "russian", "args": {}})
    print(f"  gavrilo forces={dict(s2.lords['gavrilo'].forces)}")
    print(f"  besiegers at pskov: {[lid for lid, l in s2.lords.items() if l.location == 'pskov' and l.side == 'teutonic']}")
    try:
        sally_res = step(s2, {"type": "cmd_sally", "side": "russian", "args": {"lord_id": "gavrilo"}})
        print(f"  Sally outcome: {sally_res.get('sally_outcome')}")
        print(f"  After Sally: pskov.siege_markers={s2.locales['pskov'].siege_markers}")
    except Exception as e:
        print(f"  Sally EXCEPTION: {type(e).__name__}: {e}")

    step(s2, {"type": "fpd_resolve", "side": "teutonic", "args": {}})
    step(s2, {"type": "fpd_resolve", "side": "russian", "args": {}})

    # T card 2: hermann Siege.
    print("\n--- T card 2: hermann Siege pskov ---")
    if s2.locales["pskov"].siege_markers > 0 and s2.lords["hermann"].state == "mustered":
        step(s2, {"type": "command_reveal", "side": "teutonic", "args": {}})
        siege_res = step(s2, {"type": "cmd_siege", "side": "teutonic", "args": {"lord_id": "hermann"}})
        print(f"  Siege markers now: {s2.locales['pskov'].siege_markers}")
        print(f"  Surrender: {siege_res.get('surrender')}")
        print(f"  Siege added: {siege_res.get('siege_added')}")

    print("\n=== Final state ===")
    for lid, l in s2.lords.items():
        if l.state == "mustered":
            print(f"  {lid:14} loc={l.location:10} forces={dict(l.forces)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
