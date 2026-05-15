"""SMOKE-067 (Round 72): March must respect agent-specified args.way_type
when src<->dest has parallel Ways (e.g., dorpat<->odenpah has both
trackway and waterway).

Previously _h_cmd_march took the first matching Way in load_ways()
order, which prevented the agent from using the alternate Way. A Lord
with Boats (Waterway-only transport) trying to March a parallel
Trackway/Waterway pair was forced into the Trackway path and rejected
for missing usable Transport.
"""
from __future__ import annotations

import pytest

import nevsky.actions  # noqa: F401
from nevsky.actions import IllegalAction, apply_action
from nevsky.scenarios import load_scenario


def _setup(state, lord_id, src):
    lord = state.lords[lord_id]
    lord.state = "mustered"
    lord.location = src
    state.meta.phase = "campaign"
    state.meta.campaign_step = "command"
    state.meta.box = 9  # Summer
    state.meta.active_player = lord.side
    state.campaign_turn.in_feed_pay_disband = False
    state.campaign_turn.next_to_reveal = lord.side
    state.campaign_turn.active_lord = lord_id
    state.campaign_turn.active_card = lord_id
    state.campaign_turn.actions_remaining = 3


def test_march_default_way_type_when_unspecified():
    """No args.way_type: legacy behavior picks first matching Way
    (trackway for dorpat<->odenpah per ways.json order)."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    h = s.lords["hermann"]
    h.forces = {"knights": 1}
    h.assets = {"cart": 1}  # trackway-compatible
    _setup(s, "hermann", "dorpat")
    r = apply_action(s, {"type": "cmd_march", "side": "teutonic",
                          "args": {"lord_id": "hermann", "to": "odenpah"}})
    assert r["lord_id"] == "hermann"
    assert s.lords["hermann"].location == "odenpah"


def test_march_with_explicit_waterway():
    """Agent picks waterway: Lord with Boats but no Carts can March
    dorpat<->odenpah via the waterway."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    h = s.lords["hermann"]
    h.forces = {"knights": 1}
    h.assets = {"boat": 1}  # waterway-compatible only
    _setup(s, "hermann", "dorpat")
    r = apply_action(s, {"type": "cmd_march", "side": "teutonic",
                          "args": {"lord_id": "hermann", "to": "odenpah",
                                    "way_type": "waterway"}})
    assert s.lords["hermann"].location == "odenpah"


def test_march_with_explicit_trackway():
    s = load_scenario("crusade_on_novgorod", seed=1)
    h = s.lords["hermann"]
    h.forces = {"knights": 1}
    h.assets = {"cart": 1}
    _setup(s, "hermann", "dorpat")
    r = apply_action(s, {"type": "cmd_march", "side": "teutonic",
                          "args": {"lord_id": "hermann", "to": "odenpah",
                                    "way_type": "trackway"}})
    assert s.lords["hermann"].location == "odenpah"


def test_march_rejects_invalid_way_type():
    """way_type that doesn't match any Way between src/dest is rejected."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    h = s.lords["hermann"]
    h.forces = {"knights": 1}
    h.assets = {}
    _setup(s, "hermann", "dorpat")
    with pytest.raises(IllegalAction) as e:
        apply_action(s, {"type": "cmd_march", "side": "teutonic",
                          "args": {"lord_id": "hermann", "to": "odenpah",
                                    "way_type": "sea"}})
    assert e.value.code == "bad_way_type"
