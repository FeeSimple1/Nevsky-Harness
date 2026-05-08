"""Active-play smoke test: drive Pleskau scenario through real moves
that actually engage the rules engine (March, Approach, Battle, Siege).

Run:  PYTHONPATH=src python3 tests/_playthrough_pleskau.py

Not a pytest test (filename starts with _) so pytest collection skips
it; can be run directly to see what breaks.
"""

from __future__ import annotations

import json
import sys
import traceback

from nevsky.actions import IllegalAction, apply_action
from nevsky.scenarios import load_scenario


def step(s, action: dict) -> dict:
    """Apply an action; return the result. Print a one-line summary."""
    try:
        res = apply_action(s, action)
        print(f"  OK {action['type']:30} -> {json.dumps(res, default=str)[:140]}")
        return res
    except IllegalAction as e:
        print(f"  IL {action['type']:30} -> {e.code}: {e}")
        raise
    except Exception as e:
        print(f"  EX {action['type']:30} -> {type(e).__name__}: {e}")
        traceback.print_exc()
        raise


def show(s, label: str) -> None:
    print(f"--- {label} ---")
    print(f"  phase={s.meta.phase} levy_step={s.meta.levy_step} "
          f"campaign_step={s.meta.campaign_step} active={s.meta.active_player}")
    print(f"  box={s.meta.box} (sequence={s.meta.sequence})")
    for lid, l in s.lords.items():
        if l.state == "mustered":
            forces = ",".join(f"{k}{v}" for k, v in l.forces.items() if v)
            assets = ",".join(f"{k}{v}" for k, v in l.assets.items() if v)
            print(f"    {lid:14} @ {l.location:10} {forces:30} | {assets}")


def main() -> int:
    print("=" * 60)
    print("Pleskau active-play smoke test")
    print("=" * 60)
    s = load_scenario("pleskau", seed=7)
    show(s, "After load")

    # === LEVY 1 ===
    print("\n[Levy 1] Arts of War")
    # Confirm-all setup transports for both sides.
    step(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    step(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})

    # T draws first.
    step(s, {"type": "aow_shuffle", "side": "teutonic", "args": {}})
    step(s, {"type": "aow_draw", "side": "teutonic", "args": {}})
    # Implement both drawn cards. First Levy = capabilities.
    for _ in range(2):
        deck = s.decks.teutonic
        if not deck.pending_draw:
            break
        from nevsky.static_data import load_cards
        cid = deck.pending_draw[0]
        c = load_cards()[cid]
        args = {}
        if not c["no_event"] and c["capability_scope"] == "this_lord":
            args["lord_id"] = next(
                lid for lid, l in s.lords.items()
                if l.side == "teutonic" and l.state == "mustered"
            )
        step(s, {"type": "aow_implement_card", "side": "teutonic", "args": args})
    step(s, {"type": "advance_step", "side": "teutonic", "args": {}})

    step(s, {"type": "aow_shuffle", "side": "russian", "args": {}})
    step(s, {"type": "aow_draw", "side": "russian", "args": {}})
    for _ in range(2):
        deck = s.decks.russian
        if not deck.pending_draw:
            break
        from nevsky.static_data import load_cards
        cid = deck.pending_draw[0]
        c = load_cards()[cid]
        args = {}
        if not c["no_event"] and c["capability_scope"] == "this_lord":
            args["lord_id"] = next(
                lid for lid, l in s.lords.items()
                if l.side == "russian" and l.state == "mustered"
            )
        step(s, {"type": "aow_implement_card", "side": "russian", "args": args})
    step(s, {"type": "advance_step", "side": "russian", "args": {}})

    print("\n[Levy 1] Pay (skip)")
    step(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    step(s, {"type": "advance_step", "side": "russian", "args": {}})

    print("\n[Levy 1] Disband")
    step(s, {"type": "disband_resolve", "side": "teutonic", "args": {}})
    step(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    step(s, {"type": "disband_resolve", "side": "russian", "args": {}})
    step(s, {"type": "advance_step", "side": "russian", "args": {}})

    print("\n[Levy 1] Muster (skip)")
    step(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    step(s, {"type": "advance_step", "side": "russian", "args": {}})

    print("\n[Levy 1] Call to Arms (skip)")
    step(s, {"type": "legate_skip", "side": "teutonic", "args": {}})
    step(s, {"type": "aow_discard_this_levy", "side": "teutonic", "args": {}})
    step(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    step(s, {"type": "veche_action", "side": "russian", "args": {"option": "skip"}})
    step(s, {"type": "aow_discard_this_levy", "side": "russian", "args": {}})
    step(s, {"type": "advance_step", "side": "russian", "args": {}})

    show(s, "Entering Campaign 1")

    # === CAMPAIGN 1 ===
    # Plan: each side stacks REAL cards (not all Pass). Find any
    # mustered Lord and put their card in the plan.
    from nevsky.campaign import _plan_target_size
    target = _plan_target_size(s.meta.box)
    print(f"\n[Campaign 1] Plan target = {target}")

    teu_mustered = [lid for lid, l in s.lords.items()
                    if l.side == "teutonic" and l.state == "mustered"]
    rus_mustered = [lid for lid, l in s.lords.items()
                    if l.side == "russian" and l.state == "mustered"]
    # Stack: first card is the active Lord we want to try maneuvers with.
    teu_active = teu_mustered[0]
    rus_active = rus_mustered[0]
    step(s, {"type": "plan_add_card", "side": "teutonic", "args": {"card": teu_active}})
    for _ in range(target - 1):
        step(s, {"type": "plan_add_card", "side": "teutonic", "args": {"card": "pass"}})
    step(s, {"type": "finalize_plan", "side": "teutonic", "args": {}})

    step(s, {"type": "plan_add_card", "side": "russian", "args": {"card": rus_active}})
    for _ in range(target - 1):
        step(s, {"type": "plan_add_card", "side": "russian", "args": {"card": "pass"}})
    step(s, {"type": "finalize_plan", "side": "russian", "args": {}})

    show(s, "Plans finalized; Activation begins")

    # T reveals first.
    print(f"\n[Campaign 1] T reveals card 1 -- expect {teu_active}")
    step(s, {"type": "command_reveal", "side": "teutonic", "args": {}})
    print(f"  active_lord={s.campaign_turn.active_lord} actions_remaining={s.campaign_turn.actions_remaining}")

    # Try a March: pick any adjacent locale.
    from nevsky.static_data import load_ways
    ways = load_ways()
    t_loc = s.lords[teu_active].location
    march_target = None
    for w in ways:
        cand = w["b"] if w["a"] == t_loc else (w["a"] if w["b"] == t_loc else None)
        if cand:
            march_target = cand
            break
    print(f"  Trying March: {teu_active} from {t_loc} -> {march_target}")
    if march_target:
        try:
            step(s, {"type": "cmd_march", "side": "teutonic",
                     "args": {"lord_id": teu_active, "to": march_target}})
        except IllegalAction as e:
            print(f"  March failed: {e}")
        # If a Battle was triggered, defender chooses Stand.
        if s.combat_pending is not None:
            print(f"  Combat pending: {s.combat_pending.attacker_side} vs {s.combat_pending.defender_side}")
            try:
                step(s, {"type": "stand_battle", "side": s.combat_pending.pending_response_by, "args": {}})
            except IllegalAction as e:
                print(f"  stand_battle failed: {e}")
            except Exception as e:
                print(f"  stand_battle EXCEPTION: {type(e).__name__}: {e}")
                traceback.print_exc()

    show(s, "After T's first card")

    # FPD T then R.
    if s.campaign_turn.in_feed_pay_disband:
        try:
            step(s, {"type": "fpd_resolve", "side": "teutonic", "args": {}})
        except Exception as e:
            print(f"  fpd_resolve T EXCEPTION: {type(e).__name__}: {e}")
        try:
            step(s, {"type": "fpd_resolve", "side": "russian", "args": {}})
        except Exception as e:
            print(f"  fpd_resolve R EXCEPTION: {type(e).__name__}: {e}")

    # Continue activation loop: pass + fpd until plans drain.
    safety = 30
    while s.meta.campaign_step == "command" and safety > 0:
        side = s.campaign_turn.next_to_reveal
        if not s.campaign_turn.in_feed_pay_disband:
            try:
                step(s, {"type": "command_reveal", "side": side, "args": {}})
            except IllegalAction as e:
                print(f"  command_reveal {side} failed: {e}")
                break
            # If lord-card revealed and is the active side's, just pass.
            if s.campaign_turn.active_lord and s.lords[s.campaign_turn.active_lord].side == side and s.campaign_turn.actions_remaining > 0:
                try:
                    step(s, {"type": "cmd_pass", "side": side,
                              "args": {"lord_id": s.campaign_turn.active_lord}})
                except Exception as e:
                    print(f"  cmd_pass EXCEPTION: {type(e).__name__}: {e}")
        try:
            step(s, {"type": "fpd_resolve", "side": "teutonic", "args": {}})
            step(s, {"type": "fpd_resolve", "side": "russian", "args": {}})
        except IllegalAction as e:
            print(f"  fpd_resolve failed: {e}")
            break
        safety -= 1

    show(s, "Activation done; entering End Campaign")

    if s.meta.campaign_step == "end_campaign":
        try:
            step(s, {"type": "end_campaign_resolve", "side": "teutonic", "args": {}})
            step(s, {"type": "end_campaign_resolve", "side": "russian", "args": {}})
        except Exception as e:
            print(f"  end_campaign_resolve EXCEPTION: {type(e).__name__}: {e}")

    show(s, "Final state")
    print(f"\nDONE. Sequence={s.meta.sequence}, history entries={len(s.history)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
