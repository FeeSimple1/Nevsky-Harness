"""Round 38 — SMOKE-026: Laden / can't-move gates must respect the
WAY TYPE being marched.

Per 1.7.4 Transport compatibility:
  - Boats are usable on Waterways only.
  - Carts are usable on Trackways only.
  - Sleds work on any overland Way (Trackway / Waterway in Winter).
  - Ships are for sea Ways only.

Pre-fix the `_is_laden` and `_must_discard_to_move_excess` checks
counted any season-valid Transport, ignoring the Way being marched.
So a Lord with Boats marching a Trackway treated the Boats as if
they helped. Repro: 5 Provender + 4 Boats marching a Trackway in
summer should require discarding all 5 Provender (boats don't help
on a trackway, so usable = 0, prov 5 > 2*0). Pre-fix, the march
succeeded as Laden cost-2 without any discard.
"""
from __future__ import annotations

from nevsky.actions import apply_action, IllegalAction
from nevsky.scenarios import load_scenario
from nevsky.static_data import load_ways


def _setup():
    s = load_scenario("crusade_on_novgorod", seed=1)
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.box = 1  # summer
    s.meta.active_player = "teutonic"
    return s


def _trackway_pair():
    for w in load_ways():
        if w["type"] == "trackway":
            return w["a"], w["b"]
    raise RuntimeError("no trackway found")


def _waterway_pair():
    for w in load_ways():
        if w["type"] == "waterway":
            return w["a"], w["b"]
    raise RuntimeError("no waterway found")


def test_boat_only_lord_with_excess_provender_cannot_march_trackway():
    """5 Prov + 4 Boats + 0 Carts on Trackway: usable = 0, prov > 2*0.
    Must discard or be rejected."""
    src, dest = _trackway_pair()
    s = _setup()
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].location = src
    s.lords[teu].in_stronghold = False
    s.lords[teu].forces = {"knights": 3}
    s.lords[teu].assets = {"provender": 5, "boat": 4}
    s.campaign_turn.active_lord = teu
    s.campaign_turn.actions_remaining = 3
    s.campaign_turn.in_feed_pay_disband = False

    try:
        apply_action(s, {"type": "cmd_march", "side": "teutonic",
                          "args": {"lord_id": teu, "to": dest}})
        raise AssertionError("march should have been blocked or required discard")
    except IllegalAction as e:
        assert "provender" in str(e).lower() or "transport" in str(e).lower(), e


def test_cart_lord_marches_trackway_normally():
    """5 Prov + 4 Carts on Trackway: usable = 4, prov > 4 → Laden but
    not over the can't-move gate. Should succeed at cost 2."""
    src, dest = _trackway_pair()
    s = _setup()
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].location = src
    s.lords[teu].in_stronghold = False
    s.lords[teu].forces = {"knights": 3}
    s.lords[teu].assets = {"provender": 5, "cart": 4}
    s.campaign_turn.active_lord = teu
    s.campaign_turn.actions_remaining = 3
    s.campaign_turn.in_feed_pay_disband = False
    res = apply_action(s, {"type": "cmd_march", "side": "teutonic",
                            "args": {"lord_id": teu, "to": dest}})
    assert res["laden"] is True
    assert res["cost"] == 2


def test_cart_only_lord_with_excess_provender_cannot_march_waterway():
    """Mirror: 5 Prov + 4 Carts on Waterway → carts don't help → must
    discard or be rejected."""
    src, dest = _waterway_pair()
    s = _setup()
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].location = src
    s.lords[teu].in_stronghold = False
    s.lords[teu].forces = {"knights": 3}
    s.lords[teu].assets = {"provender": 5, "cart": 4}
    s.campaign_turn.active_lord = teu
    s.campaign_turn.actions_remaining = 3
    s.campaign_turn.in_feed_pay_disband = False

    try:
        apply_action(s, {"type": "cmd_march", "side": "teutonic",
                          "args": {"lord_id": teu, "to": dest}})
        raise AssertionError("march should have been blocked")
    except IllegalAction as e:
        assert "provender" in str(e).lower() or "transport" in str(e).lower(), e


def test_boat_lord_marches_waterway_normally():
    """5 Prov + 4 Boats on Waterway: usable = 4, prov > 4 → Laden at
    cost 2."""
    src, dest = _waterway_pair()
    s = _setup()
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].location = src
    s.lords[teu].in_stronghold = False
    s.lords[teu].forces = {"knights": 3}
    s.lords[teu].assets = {"provender": 5, "boat": 4}
    s.campaign_turn.active_lord = teu
    s.campaign_turn.actions_remaining = 3
    s.campaign_turn.in_feed_pay_disband = False
    res = apply_action(s, {"type": "cmd_march", "side": "teutonic",
                            "args": {"lord_id": teu, "to": dest}})
    assert res["laden"] is True
    assert res["cost"] == 2


def test_no_provender_lord_marches_any_way():
    """Lord with 0 Provender + 4 Boats can march a Trackway as Unladen
    (no carried load → no transport check matters)."""
    src, dest = _trackway_pair()
    s = _setup()
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].location = src
    s.lords[teu].in_stronghold = False
    s.lords[teu].forces = {"knights": 3}
    s.lords[teu].assets = {"boat": 4}  # no Prov, no Loot
    s.campaign_turn.active_lord = teu
    s.campaign_turn.actions_remaining = 3
    s.campaign_turn.in_feed_pay_disband = False
    res = apply_action(s, {"type": "cmd_march", "side": "teutonic",
                            "args": {"lord_id": teu, "to": dest}})
    assert res["laden"] is False
    assert res["cost"] == 1


def test_discard_excess_provender_allows_march():
    """When the caller passes discard_excess_provender=True, the
    excess Provender is dropped and the march proceeds."""
    src, dest = _trackway_pair()
    s = _setup()
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].location = src
    s.lords[teu].in_stronghold = False
    s.lords[teu].forces = {"knights": 3}
    s.lords[teu].assets = {"provender": 5, "boat": 4}
    s.campaign_turn.active_lord = teu
    s.campaign_turn.actions_remaining = 3
    s.campaign_turn.in_feed_pay_disband = False
    res = apply_action(s, {"type": "cmd_march", "side": "teutonic",
                            "args": {"lord_id": teu, "to": dest,
                                      "discard_excess_provender": True}})
    # All 5 prov discarded; Lord now Unladen.
    assert s.lords[teu].assets.get("provender", 0) == 0
