"""Round 39 — SMOKE-027: VP must never be negative.

Liberation (R35 fix) subtracts the enemy's VP when their Conquered
marker is cleared. If the calendar.<side>_vp float is somehow lower
than the cleared marker value (e.g., from a test fixture or a future
mutation bug), the raw subtraction goes below 0. Per the Calendar
reference there's no negative-VP face on the Victory marker; VP is
in [0, 17.5].

Round 39 adds a >= 0 floor at the same canonical chokepoint that
already enforces the 17.5 cap (refresh_victory_markers), plus a
defense-in-depth max(0, ...) in determine_scenario_winner.
"""
from __future__ import annotations

from nevsky.actions import apply_action
from nevsky.scenarios import (
    load_scenario, refresh_victory_markers, determine_scenario_winner,
)


def test_refresh_clamps_negative_to_zero():
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.calendar.teutonic_vp = -5.0
    refresh_victory_markers(s)
    assert s.calendar.teutonic_vp == 0.0


def test_refresh_handles_negative_for_both_sides():
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.calendar.teutonic_vp = -3.0
    s.calendar.russian_vp = -7.0
    refresh_victory_markers(s)
    assert s.calendar.teutonic_vp == 0.0
    assert s.calendar.russian_vp == 0.0


def test_liberation_does_not_produce_negative_vp():
    """When R liberates a teu_conq=2 City but calendar.teutonic_vp
    is artificially low (0), the post-liberation VP must clamp at 0
    instead of going negative."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.box = 1
    s.meta.active_player = "russian"
    city = "pskov"
    s.locales[city].teutonic_conquered = 2
    s.calendar.teutonic_vp = 0.0  # artificially low
    rus = next(lid for lid, l in s.lords.items()
                if l.side == "russian" and l.state == "mustered")
    s.lords[rus].location = city
    s.lords[rus].in_stronghold = False
    s.lords[rus].forces = {"knights": 5, "men_at_arms": 5}
    s.locales[city].siege_markers = 1
    s.campaign_turn.active_lord = rus
    s.campaign_turn.actions_remaining = 3
    s.campaign_turn.in_feed_pay_disband = False
    # Move T Lords away.
    for lid, l in s.lords.items():
        if l.side == "teutonic" and l.state == "mustered":
            l.location = "dorpat"
    apply_action(s, {"type": "cmd_storm", "side": "russian", "args": {"lord_id": rus}})
    assert s.calendar.teutonic_vp >= 0.0
    assert s.calendar.teutonic_vp == 0.0


def test_determine_winner_clamps_negative_input():
    """Defense-in-depth: even if calendar.teutonic_vp is below 0
    somehow, determine_scenario_winner reports clamped 0."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.calendar.teutonic_vp = -3.0
    w = determine_scenario_winner(s)
    assert w["t_vp"] == 0.0


def test_normal_vp_unchanged_by_floor():
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.calendar.teutonic_vp = 4.5
    s.calendar.russian_vp = 2.0
    refresh_victory_markers(s)
    assert s.calendar.teutonic_vp == 4.5
    assert s.calendar.russian_vp == 2.0
