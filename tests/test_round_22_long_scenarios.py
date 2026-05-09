"""Round 22 regression tests for long-scenario smoke fixes:
- Pleskau Lord-removed VP bonus.
- determine_scenario_winner with Watland override + Campaign Victory."""
from __future__ import annotations

import pytest

from nevsky.actions import _remove_lord_permanently, apply_action
from nevsky.scenarios import (
    determine_scenario_winner,
    load_scenario,
    _compute_vp,
)
from nevsky.static_data import load_lords as _static_lords


def test_pleskau_lord_removed_increments_counter():
    s = load_scenario("pleskau", seed=1)
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})
    pre_t = s.calendar.pleskau_lords_removed_teutonic
    pre_r = s.calendar.pleskau_lords_removed_russian
    static = _static_lords()
    # Force-remove a Russian Lord. Counter naming: the field tracks the
    # SIDE of the removed Lord. So removing vladislav (Russian) bumps
    # pleskau_lords_removed_russian.
    _remove_lord_permanently(s, "vladislav", static["vladislav"])
    assert s.calendar.pleskau_lords_removed_russian == pre_r + 1
    assert s.calendar.pleskau_lords_removed_teutonic == pre_t


def test_pleskau_compute_vp_includes_lord_removed_bonus():
    s = load_scenario("pleskau", seed=1)
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})
    static = _static_lords()
    pre_t_vp = _compute_vp("teutonic", s.locales, s.veche, s.calendar)
    _remove_lord_permanently(s, "vladislav", static["vladislav"])
    post_t_vp = _compute_vp("teutonic", s.locales, s.veche, s.calendar)
    assert post_t_vp == pre_t_vp + 1.0


def test_non_pleskau_lord_removed_does_not_increment_counters():
    s = load_scenario("watland", seed=1)
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})
    static = _static_lords()
    # Watland doesn't have victory_lord_removed_bonus.
    pre = (s.calendar.pleskau_lords_removed_teutonic,
           s.calendar.pleskau_lords_removed_russian)
    _remove_lord_permanently(s, "vladislav", static["vladislav"])
    post = (s.calendar.pleskau_lords_removed_teutonic,
            s.calendar.pleskau_lords_removed_russian)
    assert pre == post


def test_determine_winner_standard_higher_vp():
    s = load_scenario("pleskau", seed=1)
    s.calendar.teutonic_vp = 3.0
    s.calendar.russian_vp = 1.0
    result = determine_scenario_winner(s)
    assert result["winner"] == "teutonic"
    assert result["applied_override"] is None


def test_determine_winner_standard_tie_is_draw():
    s = load_scenario("pleskau", seed=1)
    s.calendar.teutonic_vp = 1.0
    s.calendar.russian_vp = 1.0
    result = determine_scenario_winner(s)
    assert result["winner"] == "draw"


def test_determine_winner_watland_t_below_7_loses():
    s = load_scenario("watland", seed=1)
    s.calendar.teutonic_vp = 4.5
    s.calendar.russian_vp = 0.0
    result = determine_scenario_winner(s)
    assert result["winner"] == "russian"
    assert result["applied_override"] == "watland"


def test_determine_winner_watland_t_at_7_with_low_r_wins():
    s = load_scenario("watland", seed=1)
    s.calendar.teutonic_vp = 7.0
    s.calendar.russian_vp = 3.0
    result = determine_scenario_winner(s)
    assert result["winner"] == "teutonic"


def test_determine_winner_watland_t_below_double_r_loses():
    s = load_scenario("watland", seed=1)
    s.calendar.teutonic_vp = 7.0
    s.calendar.russian_vp = 4.0  # T < 2*R
    result = determine_scenario_winner(s)
    assert result["winner"] == "russian"


def test_determine_winner_campaign_victory_zero_mustered_other_side_wins():
    s = load_scenario("pleskau", seed=1)
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})
    s.meta.phase = "campaign"
    # Force all Russian Lords to removed/disbanded state.
    for lord in s.lords.values():
        if lord.side == "russian" and lord.state == "mustered":
            lord.state = "removed"
    s.calendar.teutonic_vp = 0.0
    s.calendar.russian_vp = 0.0
    result = determine_scenario_winner(s)
    assert result["winner"] == "teutonic"
    assert result["applied_override"] == "campaign_victory"


def test_determine_winner_campaign_victory_skipped_during_levy():
    """5.2 only applies during Campaign phase. During Levy the standard
    end-of-scenario rule applies (or hasn't been reached yet)."""
    s = load_scenario("pleskau", seed=1)
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})
    # phase = levy, even with no Russian Lords mustered, no Campaign Victory.
    for lord in s.lords.values():
        if lord.side == "russian":
            lord.state = "removed"
    s.calendar.teutonic_vp = 1.0
    s.calendar.russian_vp = 0.0
    result = determine_scenario_winner(s)
    # Falls through to 5.3 standard.
    assert result["winner"] == "teutonic"
    assert result["applied_override"] is None
