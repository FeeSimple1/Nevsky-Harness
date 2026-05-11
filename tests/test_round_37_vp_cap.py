"""Round 37 — SMOKE-025: VP cap at 17.5 must be enforced.

Per Calendar reference: "CAP: A side may never exceed 17½ VP — any
excess is forfeit." Pre-fix the harness never clamped — T's VP could
balloon to 20+ after Storming Novgorod near the cap.

The fix clamps at two points:
  1. refresh_victory_markers (called after every VP mutation) — the
     "soft" cap-at-source enforcement.
  2. determine_scenario_winner — defense-in-depth for any direct
     mutation that bypassed refresh_victory_markers.
"""
from __future__ import annotations

from nevsky.actions import apply_action
from nevsky.scenarios import (
    load_scenario, refresh_victory_markers, determine_scenario_winner, VP_CAP,
)


def _setup_campaign():
    s = load_scenario("crusade_on_novgorod", seed=1)
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.box = 1
    s.meta.active_player = "teutonic"
    return s


def test_vp_cap_value_is_17_5():
    assert VP_CAP == 17.5


def test_vp_cap_enforced_via_refresh():
    """refresh_victory_markers clamps T VP at 17.5."""
    s = _setup_campaign()
    s.calendar.teutonic_vp = 20.0
    refresh_victory_markers(s)
    assert s.calendar.teutonic_vp == 17.5


def test_vp_cap_enforced_via_storm_at_near_cap():
    """T at 17 VP storming Novgorod (+3) ends at 17.5, not 20."""
    s = _setup_campaign()
    s.calendar.teutonic_vp = 17.0
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].location = "novgorod"
    s.lords[teu].in_stronghold = False
    s.lords[teu].forces = {"knights": 8, "men_at_arms": 8}
    s.locales["novgorod"].siege_markers = 1
    # Clear R defenders.
    for lid, l in s.lords.items():
        if l.side == "russian" and l.state == "mustered":
            l.location = "ladoga"
    s.campaign_turn.active_lord = teu
    s.campaign_turn.actions_remaining = 3
    s.campaign_turn.in_feed_pay_disband = False
    res = apply_action(s, {"type": "cmd_storm", "side": "teutonic", "args": {"lord_id": teu}})
    assert res.get("battle", {}).get("winner") == "attacker"
    assert s.calendar.teutonic_vp == 17.5, f"got {s.calendar.teutonic_vp}"


def test_vp_cap_enforced_in_determine_scenario_winner():
    """Defense-in-depth: if calendar.teutonic_vp is somehow > 17.5
    (e.g., a future code path that bypasses refresh), the winner
    determination still reports the clamped value."""
    s = _setup_campaign()
    s.calendar.teutonic_vp = 25.0  # direct mutation, no refresh
    w = determine_scenario_winner(s)
    assert w["t_vp"] == 17.5


def test_vp_cap_symmetric_for_russian():
    s = _setup_campaign()
    s.calendar.russian_vp = 19.0
    refresh_victory_markers(s)
    assert s.calendar.russian_vp == 17.5


def test_vp_below_cap_unchanged():
    s = _setup_campaign()
    s.calendar.teutonic_vp = 12.0
    s.calendar.russian_vp = 8.5
    refresh_victory_markers(s)
    assert s.calendar.teutonic_vp == 12.0
    assert s.calendar.russian_vp == 8.5
