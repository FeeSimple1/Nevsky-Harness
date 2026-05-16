"""SMOKE-078 (Round 80): Supply accepts Sled in Rasputitsa, contradicting
rulebook 1.7.4 / Calendar reference.

Per rulebook 1.7.4: "Only Sleds are usable in Winter, and Sleds are
usable only in Winter. They can be used on all Ways."
Per Calendar reference: "Sleds: Early Winter, Late Winter (any Way)."

Rasputitsa is NOT a Sled season — the harness previously accepted
sleds in Rasputitsa for Supply, contradicting the rule. The
`_usable_transport_count_for_way` no-way-type branch also incorrectly
counted sleds in Rasputitsa for general Laden-status queries.
"""
from __future__ import annotations

import pytest

import nevsky.actions  # noqa: F401 — register handlers
from nevsky.actions import IllegalAction
from nevsky.campaign import _h_cmd_supply, _usable_transport_count_for_lord
from nevsky.scenarios import load_scenario


def _hermann_supply_setup(s):
    hermann = s.lords["hermann"]
    hermann.location = "dorpat"  # his Seat
    hermann.state = "mustered"
    hermann.in_stronghold = False
    hermann.moved_fought = False
    hermann.assets = {"sled": 4}
    s.campaign_turn.active_lord = "hermann"
    s.campaign_turn.actions_remaining = 5
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.campaign_turn.in_feed_pay_disband = False


def test_supply_rejects_sled_in_rasputitsa():
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.box = 7  # Rasputitsa
    _hermann_supply_setup(s)
    with pytest.raises(IllegalAction) as e:
        _h_cmd_supply(s, "teutonic", {"lord_id": "hermann",
            "sources": [{"locale_id": "dorpat", "route": ["dorpat"], "transport": "sled"}]})
    assert e.value.code == "sled_non_winter"


def test_supply_accepts_sled_in_early_winter():
    """Regression: sleds remain valid in Early Winter."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.box = 3  # Early Winter
    _hermann_supply_setup(s)
    # Supply succeeds from own-seat 0-hop route with sled.
    result, _ = _h_cmd_supply(s, "teutonic", {"lord_id": "hermann",
        "sources": [{"locale_id": "dorpat", "route": ["dorpat"], "transport": "sled"}]})
    assert result["added"] >= 1


def test_supply_accepts_sled_in_late_winter():
    """Regression: sleds remain valid in Late Winter."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.box = 5  # Late Winter
    _hermann_supply_setup(s)
    result, _ = _h_cmd_supply(s, "teutonic", {"lord_id": "hermann",
        "sources": [{"locale_id": "dorpat", "route": ["dorpat"], "transport": "sled"}]})
    assert result["added"] >= 1


def test_supply_rejects_sled_in_summer():
    """Regression: sleds still rejected in Summer."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.box = 1  # Summer
    _hermann_supply_setup(s)
    with pytest.raises(IllegalAction) as e:
        _h_cmd_supply(s, "teutonic", {"lord_id": "hermann",
            "sources": [{"locale_id": "dorpat", "route": ["dorpat"], "transport": "sled"}]})
    assert e.value.code == "sled_non_winter"


def test_usable_transport_count_no_way_type_excludes_sled_in_rasputitsa():
    """The general Laden-status query (way_type=None) must NOT count
    sleds in Rasputitsa."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.box = 7  # Rasputitsa
    hermann = s.lords["hermann"]
    hermann.location = "dorpat"
    hermann.state = "mustered"
    hermann.assets = {"sled": 4}
    n = _usable_transport_count_for_lord(s, "hermann", None)
    # No boats/carts/ships, sleds shouldn't count in Rasputitsa.
    assert n == 0, f"expected 0 usable transport in Rasputitsa with only sleds, got {n}"


def test_usable_transport_count_no_way_type_includes_sled_in_winter():
    """Regression: sleds still counted in Winter for general Laden query."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.box = 3  # Early Winter
    hermann = s.lords["hermann"]
    hermann.location = "dorpat"
    hermann.state = "mustered"
    hermann.assets = {"sled": 4}
    n = _usable_transport_count_for_lord(s, "hermann", None)
    assert n == 4, f"expected 4 usable transports (sleds) in Winter, got {n}"
