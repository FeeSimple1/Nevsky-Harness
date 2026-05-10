"""Round 33 — SMOKE-019: Unbesieged-enemy checks must use Lord-level
`_is_besieged`, not locale-level `siege_markers`.

The locale's `siege_markers` only indicates that SOMEONE is besieged
there; it does NOT mean every Lord at that locale is besieged. The
besieger sits at the same locale OUTSIDE the stronghold (Unbesieged)
while the defender sits INSIDE (Besieged).

Three sites had the wrong pattern (`state.locales[X].siege_markers == 0`)
when they should have been (`not _is_besieged(state, lord_id)`):

  1. `_h_cmd_ravage` — "+1 action if Unbesieged enemy adjacent". Pre-fix
     missed the besieger case (siege_markers > 0 falsely skipped).
  2. `_h_cmd_sail` — destination must be free of Unbesieged enemy.
     Pre-fix would let a Sail land at a sieged locale even when the
     besieger Lord (Unbesieged) was sitting there.
  3. `_h_cmd_sail` route path — enemy Lord at intermediate locale
     blocks. Same bug.
"""
from __future__ import annotations

from copy import deepcopy

from nevsky.actions import apply_action, IllegalAction
from nevsky.scenarios import load_scenario


def _setup_campaign():
    s = load_scenario("crusade_on_novgorod", seed=1)
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "teutonic"
    s.meta.box = 1  # summer
    return s


def test_ravage_unbesieged_enemy_at_sieged_adjacent_triggers_extra_action():
    """Adjacent R Lord OUTSIDE stronghold but at sieged locale must
    still trigger Ravage's +1-action cost (he is Unbesieged)."""
    s = _setup_campaign()
    teus = [lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered"]
    russ = [lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered"]

    T = teus[0]; R = russ[0]
    # gdov is Russian non-region; plyussa_river is adjacent.
    s.lords[T].location = "gdov"
    s.lords[T].in_stronghold = False
    s.lords[R].location = "plyussa_river"
    s.lords[R].in_stronghold = False  # Unbesieged
    s.locales["plyussa_river"].siege_markers = 3  # sieged Locale

    s.campaign_turn.active_lord = T
    s.campaign_turn.actions_remaining = 3
    s.campaign_turn.in_feed_pay_disband = False

    res = apply_action(s, {"type": "cmd_ravage", "side": "teutonic", "args": {"lord_id": T}})
    assert res["actions_used"] == 2, (
        f"Ravage should cost 2 actions with Unbesieged enemy adjacent; got "
        f"{res['actions_used']}"
    )


def test_ravage_besieged_enemy_at_sieged_adjacent_does_not_trigger_extra():
    """Adjacent R Lord INSIDE stronghold at sieged locale: Besieged,
    should NOT trigger extra cost. (Pre-fix this was also incorrectly
    handled but in the other direction — the test exists to pin the
    intended behavior.)"""
    s = _setup_campaign()
    teus = [lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered"]
    russ = [lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered"]

    T = teus[0]; R = russ[0]
    s.lords[T].location = "gdov"
    s.lords[T].in_stronghold = False
    # Find a stronghold adjacent to gdov. plyussa_river is trade_route, no
    # stronghold. Use a different fixture — put R at gdov (same locale as
    # T) in_stronghold; but Ravage adjacency is about a DIFFERENT locale.
    # Use narwia (adjacent to gdov). narwia is a fort.
    s.lords[R].location = "narwia"
    s.lords[R].in_stronghold = True  # Besieged
    s.locales["narwia"].siege_markers = 3

    s.campaign_turn.active_lord = T
    s.campaign_turn.actions_remaining = 3
    s.campaign_turn.in_feed_pay_disband = False

    res = apply_action(s, {"type": "cmd_ravage", "side": "teutonic", "args": {"lord_id": T}})
    assert res["actions_used"] == 1, (
        f"Ravage should cost 1 action with only Besieged enemies adjacent; "
        f"got {res['actions_used']}"
    )


def test_sail_blocked_by_unbesieged_enemy_at_sieged_dest():
    """Sail to a seaport with an Unbesieged enemy Lord must be blocked
    even if the locale has siege markers (e.g., enemy is besieging
    own-side Lord there)."""
    s = _setup_campaign()
    teus = [lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered"]
    russ = [lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered"]

    T = teus[0]; R = russ[0]
    s.lords[T].location = "reval"
    s.lords[T].in_stronghold = False
    s.lords[T].assets["ship"] = 2
    s.lords[R].location = "narwia"
    s.lords[R].in_stronghold = False  # Unbesieged
    s.locales["narwia"].siege_markers = 3

    s.campaign_turn.active_lord = T
    s.campaign_turn.actions_remaining = 3
    s.campaign_turn.in_feed_pay_disband = False

    try:
        apply_action(s, {"type": "cmd_sail", "side": "teutonic",
                          "args": {"lord_id": T, "destination": "narwia"}})
        raise AssertionError("Sail should have been blocked")
    except IllegalAction as e:
        assert "dest_blocked" in str(e) or "Unbesieged" in str(e), (
            f"Expected dest_blocked; got {e}"
        )


def test_sail_allowed_when_only_besieged_enemy_at_dest():
    """Sail to a seaport where the only enemy Lord is Besieged
    (in_stronghold + siege markers > 0): should be allowed (besieged
    Lord doesn't block movement on the map)."""
    s = _setup_campaign()
    teus = [lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered"]
    russ = [lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered"]

    T = teus[0]; R = russ[0]
    s.lords[T].location = "reval"
    s.lords[T].in_stronghold = False
    s.lords[T].assets["ship"] = 2
    s.lords[R].location = "narwia"
    s.lords[R].in_stronghold = True  # Besieged
    s.locales["narwia"].siege_markers = 3

    s.campaign_turn.active_lord = T
    s.campaign_turn.actions_remaining = 3
    s.campaign_turn.in_feed_pay_disband = False

    res = apply_action(s, {"type": "cmd_sail", "side": "teutonic",
                            "args": {"lord_id": T, "destination": "narwia"}})
    # Sail succeeds; Lord ends up at destination.
    assert s.lords[T].location == "narwia"
