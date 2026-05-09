"""TEST FIXTURE / engine-soundness smoke driver — NOT part of the shipped harness.

Round 5 smoke: Mongol/Kipchaq Vassal Muster + re-Muster after Disband.

Targets the still-untested paths from SMOKE_TEST_FINDINGS:
  - R10 Steppe Warriors gating Mongols/Kipchaqs.
  - A Lord Disband -> later re-Muster via 3.4.1.
"""

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
    except Exception as e:
        print(f"  EX {action['type']:30} -> {type(e).__name__}: {e}")
        traceback.print_exc()
        raise


def main() -> int:
    print("=" * 60)
    print("Round 5: Mongol Vassal Muster (R10 Steppe Warriors)")
    print("=" * 60)
    s = load_scenario("return_of_the_prince", seed=17)
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})

    # Find aleksandr (has Mongols/Kipchaqs vassals).
    print(f"\naleksandr: state={s.lords['aleksandr'].state}")
    print(f"  vassals: {list(s.lords['aleksandr'].vassals.keys())}")
    for vid, vstate in s.lords['aleksandr'].vassals.items():
        print(f"    {vid}: ready={vstate.ready}, mustered={vstate.mustered}")

    # In RotP, aleksandr starts mustered at novgorod. R10 not in play yet -> Mongol vassals not ready.
    # Set R10 in play and trigger ready-flip on Muster (via _place_lord_on_map).
    # Easier: directly test muster_vassal action.

    # Force aleksandr to be in Muster step.
    s.meta.phase = "levy"
    s.meta.levy_step = "muster"
    s.meta.active_player = "russian"

    # Try mustering Mongol vassal WITHOUT R10 -> should fail.
    print(f"\nWithout R10 in play:")
    step(s, {"type": "muster_vassal", "side": "russian",
              "args": {"by_lord": "aleksandr", "vassal_id": "aleksandr_mongols_1"}}, expect_illegal=True)

    # Add R10 to capabilities_in_play and flip vassal to ready.
    if "R10" not in s.decks.russian.capabilities_in_play:
        s.decks.russian.capabilities_in_play.append("R10")
    if "aleksandr_mongols_1" in s.lords['aleksandr'].vassals:
        s.lords['aleksandr'].vassals['aleksandr_mongols_1'].ready = True
    print(f"\nWith R10 in play, vassal ready=True:")
    step(s, {"type": "muster_vassal", "side": "russian",
              "args": {"by_lord": "aleksandr", "vassal_id": "aleksandr_mongols_1"}})
    print(f"  aleksandr forces after: {dict(s.lords['aleksandr'].forces)}")
    print(f"  mongols.mustered: {s.lords['aleksandr'].vassals['aleksandr_mongols_1'].mustered}")

    print("\n" + "=" * 60)
    print("Round 5b: Lord Disband -> re-Muster cycle")
    print("=" * 60)
    s2 = load_scenario("watland", seed=23)
    apply_action(s2, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    apply_action(s2, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})

    # Manually disband yaroslav so we can re-muster him.
    yaroslav = s2.lords["yaroslav"]
    print(f"\nyaroslav: state={yaroslav.state}, location={yaroslav.location}")
    yaroslav.state = "disbanded"
    yaroslav.location = None
    yaroslav.forces = {}
    yaroslav.assets = {}
    # Place his cylinder back on Calendar at box 4 (current Levy box).
    levy_box = next(cb.box for cb in s2.calendar.boxes if cb.has_levy_campaign_marker)
    print(f"  Putting yaroslav cylinder at box {levy_box} (Ready)")
    s2.calendar.boxes[levy_box - 1].cylinders.append("yaroslav")
    yaroslav.state = "ready"

    # Use Aleksandr's slot? No, this is Watland (Teu). Use Knud&Abel as muster-er.
    from nevsky.actions import _find_levy_marker_box
    s2.meta.phase = "levy"
    s2.meta.levy_step = "muster"
    s2.meta.active_player = "teutonic"
    by_lord = "knud_and_abel"
    print(f"\n{by_lord} musters yaroslav at odenpah (yaroslav's seat):")
    pre_forces = dict(s2.lords["yaroslav"].forces)
    res = step(s2, {"type": "muster_lord", "side": "teutonic",
                     "args": {"by_lord": by_lord, "target_lord": "yaroslav", "seat": "odenpah"}})
    print(f"  outcome: {res.get('outcome')}, roll={res.get('roll')}, fealty={res.get('fealty')}")
    if res.get("outcome") == "mustered":
        print(f"  yaroslav state now: {s2.lords['yaroslav'].state}")
        print(f"  yaroslav location: {s2.lords['yaroslav'].location}")
        print(f"  yaroslav forces: {dict(s2.lords['yaroslav'].forces)}")
        print(f"  yaroslav assets: {dict(s2.lords['yaroslav'].assets)}")
        # Setup_transport_choice PD emitted?
        pds = [pd for pd in s2.pending_decisions
               if pd.kind == "setup_transport_choice"
               and pd.context.get("lord_id") == "yaroslav"]
        print(f"  PendingDecisions for yaroslav: {len(pds)} ({[pd.context.get('emitted_at_muster') for pd in pds]})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
