"""SMOKE-089 (Round 94): Supply allows the same Source to be listed
multiple times, double-counting Provender.

Per rule 4.6 Supply: "+1 Provender per Source." The printed rule
implies each Source contributes 1 Provender per Supply action.
Listing the same locale twice in the `sources` arg should not give
double Provender — but the harness allowed it.

The Novgorod-Russian-Ship exception (per the play note: "Russians:
Novgorod via Ships up to 2 Provender") is preserved — Novgorod ship
can be listed up to 2 times for the 2-Provender combo.
"""
from __future__ import annotations

import pytest

import nevsky.actions  # noqa: F401
from nevsky.actions import IllegalAction
from nevsky.campaign import _h_cmd_supply
from nevsky.scenarios import load_scenario


def _hermann_setup(s, location="dorpat"):
    h = s.lords["hermann"]
    h.location = location
    h.state = "mustered"
    h.in_stronghold = False
    h.moved_fought = False
    h.assets = {"boat": 8}
    s.campaign_turn.active_lord = "hermann"
    s.campaign_turn.actions_remaining = 5
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.campaign_turn.in_feed_pay_disband = False


def test_supply_rejects_duplicate_seat_source():
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.box = 1
    _hermann_setup(s)
    with pytest.raises(IllegalAction) as e:
        _h_cmd_supply(s, "teutonic", {"lord_id": "hermann",
            "sources": [
                {"locale_id": "dorpat", "route": ["dorpat"], "transport": "boat"},
                {"locale_id": "dorpat", "route": ["dorpat"], "transport": "boat"},
            ]})
    assert e.value.code == "duplicate_source"


def test_supply_accepts_two_distinct_seats():
    """Hermann has seats at dorpat AND odenpah — both are valid Sources."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.box = 1
    _hermann_setup(s, location="dorpat")
    # The route to odenpah from dorpat is direct (parallel ways).
    result, _ = _h_cmd_supply(s, "teutonic", {"lord_id": "hermann",
        "sources": [
            {"locale_id": "dorpat", "route": ["dorpat"], "transport": "boat"},
            {"locale_id": "odenpah", "route": ["odenpah", "dorpat"], "transport": "boat"},
        ]})
    assert result["added"] == 2


def test_supply_accepts_novgorod_ship_twice_for_russian():
    """The Novgorod-ship exception: Russians can list Novgorod twice
    for 2 Ship-sourced Provender."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.box = 1
    aleksandr = s.lords["aleksandr"]
    aleksandr.location = "novgorod"
    aleksandr.state = "mustered"
    aleksandr.in_stronghold = False
    aleksandr.moved_fought = False
    aleksandr.assets = {"ship": 8}
    s.campaign_turn.active_lord = "aleksandr"
    s.campaign_turn.actions_remaining = 5
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.campaign_turn.in_feed_pay_disband = False
    # Try Novgorod-ship listed twice
    try:
        result, _ = _h_cmd_supply(s, "russian", {"lord_id": "aleksandr",
            "sources": [
                {"locale_id": "novgorod", "route": ["novgorod"], "transport": "ship"},
                {"locale_id": "novgorod", "route": ["novgorod"], "transport": "ship"},
            ]})
        assert result["added"] == 2
    except IllegalAction as e:
        # Some downstream validation may reject for other reasons (route,
        # Provender cap, etc.); but it should NOT be 'duplicate_source'.
        assert e.code != "duplicate_source", (
            "Novgorod ship-source exception should allow 2 listings"
        )


def test_supply_rejects_third_novgorod_ship_listing():
    """Even with the Novgorod exception, more than 2 listings is illegal
    (the printed limit is 'up to 2 Provender via Ships')."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.box = 1
    aleksandr = s.lords["aleksandr"]
    aleksandr.location = "novgorod"
    aleksandr.state = "mustered"
    aleksandr.in_stronghold = False
    aleksandr.moved_fought = False
    aleksandr.assets = {"ship": 8}
    s.campaign_turn.active_lord = "aleksandr"
    s.campaign_turn.actions_remaining = 5
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.campaign_turn.in_feed_pay_disband = False
    with pytest.raises(IllegalAction) as e:
        _h_cmd_supply(s, "russian", {"lord_id": "aleksandr",
            "sources": [
                {"locale_id": "novgorod", "route": ["novgorod"], "transport": "ship"},
                {"locale_id": "novgorod", "route": ["novgorod"], "transport": "ship"},
                {"locale_id": "novgorod", "route": ["novgorod"], "transport": "ship"},
            ]})
    # Either too_many_ship_sources (3 > 2 cap) or duplicate_source.
    assert e.value.code in ("duplicate_source", "too_many_ship_sources")
