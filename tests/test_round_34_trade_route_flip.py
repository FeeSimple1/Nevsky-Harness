"""Round 34 — SMOKE-020: Trade Route conquest flip on Lord entry.

Per Strongholds reference: "Trade Routes are boxed Locales: they take
a Conquered marker for 1 VP but have no Walls, Capacity, or Garrison.
They flip simply by an enemy Lord's presence with no friendly Lord
contesting -- no Storm involved, hence no Spoils."

Two related bugs were present before Round 34:

  1. `_has_enemy_stronghold_at` listed "trade_route" as a Stronghold
     type. Marching into a Russian trade route placed a siege marker
     (impossible per rules: trade routes have no garrison/walls).
  2. No auto-flip of the Conquered marker on entry. A T Lord could
     park on a Russian trade route indefinitely without ever gaining
     its 1 VP.

Round 34 fixes both: removes trade_route from the stronghold list and
adds `_flip_trade_route_if_uncontested` called by `_h_cmd_march`.
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


def _t_at(s, locale):
    """Place first mustered T Lord at `locale` with active-Lord state."""
    teu = next(lid for lid, l in s.lords.items()
               if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].location = locale
    s.lords[teu].in_stronghold = False
    s.lords[teu].assets["boat"] = 4
    s.lords[teu].assets["cart"] = 4
    s.campaign_turn.active_lord = teu
    s.campaign_turn.actions_remaining = 3
    s.campaign_turn.in_feed_pay_disband = False
    return teu


def test_march_into_uncontested_russian_trade_route_flips_to_teutonic():
    s = _setup_campaign()
    # Clear ALL Russian Lords from luga's vicinity by parking them elsewhere.
    for lid, l in s.lords.items():
        if l.side == "russian" and l.state == "mustered":
            l.location = "novgorod"
    teu = _t_at(s, "kaibolovo")  # adjacent to luga
    pre_vp = s.calendar.teutonic_vp
    res = apply_action(s, {"type": "cmd_march", "side": "teutonic",
                            "args": {"lord_id": teu, "to": "luga"}})
    assert s.locales["luga"].teutonic_conquered == 1
    assert s.calendar.teutonic_vp == pre_vp + 1.0
    assert s.locales["luga"].siege_markers == 0  # NO siege placed
    assert res.get("trade_route_flip", {}).get("flip_to") == "teutonic"
    assert res["placed_siege"] is False


def test_march_into_contested_russian_trade_route_does_not_flip():
    """If a Russian Lord is at the trade route, the T Lord arrives but
    triggers Approach Battle (defended). No auto-flip."""
    s = _setup_campaign()
    russ = next(lid for lid, l in s.lords.items()
                if l.side == "russian" and l.state == "mustered")
    s.lords[russ].location = "luga"
    s.lords[russ].in_stronghold = False
    teu = _t_at(s, "kaibolovo")
    res = apply_action(s, {"type": "cmd_march", "side": "teutonic",
                            "args": {"lord_id": teu, "to": "luga"}})
    # Approach Battle triggered (defender_lords present); not an auto-flip.
    assert res.get("approach") is True
    assert s.locales["luga"].teutonic_conquered == 0


def test_march_into_teu_conquered_route_by_russian_clears_marker():
    """R retakes a T-conquered trade route by marching in uncontested.
    The teutonic_conquered marker clears and T's VP decreases."""
    s = _setup_campaign()
    # Pre-flip the trade route to teutonic_conquered.
    s.locales["luga"].teutonic_conquered = 1
    s.calendar.teutonic_vp = 1.0
    # Move all T Lords away from luga.
    for lid, l in s.lords.items():
        if l.side == "teutonic" and l.state == "mustered":
            l.location = "dorpat"
    # Set up Russian active Lord adjacent.
    s.meta.active_player = "russian"
    rus = next(lid for lid, l in s.lords.items()
               if l.side == "russian" and l.state == "mustered")
    s.lords[rus].location = "kaibolovo"
    s.lords[rus].in_stronghold = False
    s.lords[rus].assets["boat"] = 4
    s.lords[rus].assets["cart"] = 4
    s.campaign_turn.active_lord = rus
    s.campaign_turn.actions_remaining = 3
    s.campaign_turn.in_feed_pay_disband = False
    res = apply_action(s, {"type": "cmd_march", "side": "russian",
                            "args": {"lord_id": rus, "to": "luga"}})
    assert s.locales["luga"].teutonic_conquered == 0
    assert s.calendar.teutonic_vp == 0.0
    assert res.get("trade_route_flip", {}).get("flip_to") == "neutral"


def test_march_into_trade_route_does_not_place_siege_marker():
    """Regression for the first half of SMOKE-020: trade routes are
    no longer treated as Strongholds, so marching in must not place
    siege markers on them."""
    s = _setup_campaign()
    for lid, l in s.lords.items():
        if l.side == "russian" and l.state == "mustered":
            l.location = "novgorod"
    teu = _t_at(s, "kaibolovo")
    res = apply_action(s, {"type": "cmd_march", "side": "teutonic",
                            "args": {"lord_id": teu, "to": "luga"}})
    assert res["placed_siege"] is False
    assert s.locales["luga"].siege_markers == 0
