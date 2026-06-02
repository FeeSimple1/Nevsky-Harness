"""Rules-accuracy fixes from the full audit (batch 3).

- Teuton Ship-Supply: a Teuton may draw up to 2 Provender from one
  Seaport via 2 Ships (4.6 / Commands ref), not just Russian Novgorod.
- Advanced Vassal Service (3.4.2): Vassal Service markers at/over their
  limit are removed/downgraded during the Campaign Feed/Pay/Disband too,
  not only the Levy Disband.
"""
from __future__ import annotations

import pytest

from nevsky.actions import IllegalAction, _find_levy_marker_box
from nevsky.campaign import _fpd_finalize, _h_cmd_supply
from nevsky.scenarios import load_scenario


def _teuton_at_seaport(s):
    h = s.lords["heinrich"]  # ships_authorized
    h.location = "reval"; h.state = "mustered"
    h.in_stronghold = False; h.moved_fought = False
    h.assets = {"ship": 8}
    s.campaign_turn.active_lord = "heinrich"
    s.campaign_turn.actions_remaining = 5
    s.meta.phase = "campaign"; s.meta.campaign_step = "command"
    s.campaign_turn.in_feed_pay_disband = False


def test_teuton_seaport_two_provender_via_two_ships():
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.box = 1
    _teuton_at_seaport(s)
    res, _ = _h_cmd_supply(s, "teutonic", {"lord_id": "heinrich", "sources": [
        {"locale_id": "reval", "route": ["reval"], "transport": "ship"},
        {"locale_id": "reval", "route": ["reval"], "transport": "ship"},
    ]})
    assert res["added"] == 2


def test_teuton_seaport_third_ship_listing_rejected():
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.box = 1
    _teuton_at_seaport(s)
    with pytest.raises(IllegalAction) as e:
        _h_cmd_supply(s, "teutonic", {"lord_id": "heinrich", "sources": [
            {"locale_id": "reval", "route": ["reval"], "transport": "ship"},
            {"locale_id": "reval", "route": ["reval"], "transport": "ship"},
            {"locale_id": "reval", "route": ["reval"], "transport": "ship"},
        ]})
    assert e.value.code in ("duplicate_source", "too_many_ship_sources")


def test_advanced_vassal_disbanded_during_campaign_fpd():
    s = load_scenario("peipus", seed=1)
    s.meta.optional_rules["advanced_vassal_service"] = True
    lord_id = next(lid for lid, l in s.lords.items()
                   if l.side == "teutonic" and l.state == "mustered" and l.vassals)
    vid = next(iter(s.lords[lord_id].vassals))
    levy_box = _find_levy_marker_box(s)
    target = max(1, levy_box - 1)  # LEFT of Levy -> permanent removal at Disband
    v = s.lords[lord_id].vassals[vid]
    v.on_calendar = True; v.mustered = True; v.calendar_box = target
    s.calendar.boxes[target - 1].vassal_service_markers.append(vid)
    assert s.lords[lord_id].state == "mustered"
    _fpd_finalize(s, "teutonic", [])
    # Vassal marker cleared from the Calendar (removed per 3.4.2 in Campaign).
    assert v.on_calendar is False
    assert vid not in s.calendar.boxes[target - 1].vassal_service_markers
