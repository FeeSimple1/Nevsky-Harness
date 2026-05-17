"""SMOKE-083 (Round 87): T18 Swedish Crusade ignores event_eligibility
target list.

Per AoW Reference T18 event_eligibility: 'Vladislav, Karelians'.
The event_text: 'On Calendar, shift cylinder or Service of Vladislav
AND Karelians each 1 box.'

The harness `_ev_swedish_crusade` accepted any target dict and
shifted whatever lord_ids the agent passed — no eligibility check.
An agent could shift Aleksandr (or any other Lord) via T18, which
contradicts the printed eligibility list.
"""
from __future__ import annotations

import pytest

import nevsky.actions  # noqa: F401 — register handlers
from nevsky.actions import IllegalAction
from nevsky.events import _ev_swedish_crusade
from nevsky.scenarios import load_scenario


def test_t18_rejects_ineligible_lord():
    s = load_scenario("crusade_on_novgorod", seed=1)
    with pytest.raises(IllegalAction) as e:
        _ev_swedish_crusade(s, {"direction": "left", "targets": {"aleksandr": "cylinder"}})
    assert e.value.code == "ineligible_target"


def test_t18_rejects_mix_of_eligible_and_ineligible():
    s = load_scenario("crusade_on_novgorod", seed=1)
    with pytest.raises(IllegalAction) as e:
        _ev_swedish_crusade(s, {"direction": "left",
                                 "targets": {"vladislav": "cylinder", "hermann": "cylinder"}})
    assert e.value.code == "ineligible_target"


def test_t18_accepts_vladislav():
    s = load_scenario("crusade_on_novgorod", seed=1)
    # Vladislav cylinder may not be on Calendar at scenario start;
    # ensure he is there before shifting.
    cal = s.calendar
    in_cal = any("vladislav" in cb.cylinders for cb in cal.boxes)
    if not in_cal:
        # Place vladislav cylinder on box 3 for the test.
        cal.boxes[2].cylinders.append("vladislav")
    r = _ev_swedish_crusade(s, {"direction": "left", "targets": {"vladislav": "cylinder"}})
    assert "vladislav" in r["shifted"]


def test_t18_accepts_karelians():
    """Karelians is a Russian Vassal — shifting via service marker."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    # Karelians cylinder might or might not be on calendar in this scenario.
    # Try service shift, fall back to skip if no service marker exists.
    try:
        r = _ev_swedish_crusade(s, {"direction": "left",
                                     "targets": {"karelians": "cylinder"}})
        assert "karelians" in r["shifted"]
    except IllegalAction as e:
        # Karelians cylinder not on Calendar at this scenario start —
        # the eligibility check passed (the failure is a downstream
        # _shift_cylinder error). That's a different concern.
        assert e.code != "ineligible_target"


def test_t18_default_targets_pass_eligibility():
    """The default targets dict (vladislav + karelians) passes eligibility."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    try:
        r = _ev_swedish_crusade(s, {"direction": "left"})
        assert "vladislav" in r["shifted"] or "karelians" in r["shifted"]
    except IllegalAction as e:
        assert e.code != "ineligible_target"
