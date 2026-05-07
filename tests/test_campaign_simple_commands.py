"""Tests for 4.7 simple Commands (Tax/Forage/Ravage/Pass/Sail) and 4.6 Supply."""

from __future__ import annotations

import pytest

from nevsky.actions import IllegalAction, apply_action
from nevsky.campaign import _plan_target_size
from nevsky.scenarios import load_scenario
from nevsky.state import GameState


def _start_command_with(s: GameState, lord_id: str) -> None:
    """Test helper: enter Campaign / Command step with `lord_id` active."""
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = s.lords[lord_id].side
    s.campaign_turn.next_to_reveal = s.lords[lord_id].side
    s.campaign_turn.active_card = lord_id
    s.campaign_turn.active_lord = lord_id
    from nevsky.static_data import load_lords
    s.campaign_turn.actions_remaining = int(load_lords()[lord_id]["ratings"]["command"])
    s.campaign_turn.in_feed_pay_disband = False
    s.lords[lord_id].moved_fought = False


def test_cmd_tax_at_seat_adds_coin_and_ends_card() -> None:
    """4.7.4: Tax at own Seat adds 1 Coin; consumes entire card."""
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    from nevsky.static_data import load_lords
    seat = load_lords()[teu]["primary_seats"][0]
    s.lords[teu].location = seat
    _start_command_with(s, teu)
    pre = s.lords[teu].assets.get("coin", 0)
    apply_action(s, {"type": "cmd_tax", "side": "teutonic", "args": {"lord_id": teu}})
    assert s.lords[teu].assets["coin"] == pre + 1
    assert s.campaign_turn.in_feed_pay_disband is True


def test_cmd_tax_off_seat_rejected() -> None:
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].location = "novgorod"  # not a Teutonic Seat
    _start_command_with(s, teu)
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "cmd_tax", "side": "teutonic", "args": {"lord_id": teu}})
    assert exc.value.code == "not_at_seat"


def test_cmd_forage_summer_anywhere_unravaged() -> None:
    """4.7.1: in Summer, Forage allowed anywhere unravaged."""
    s = load_scenario("watland", seed=1)  # box 4 = early winter? actually depends
    # Force summer.
    s.meta.box = 1
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    _start_command_with(s, teu)
    pre = s.lords[teu].assets.get("provender", 0)
    apply_action(s, {"type": "cmd_forage", "side": "teutonic", "args": {"lord_id": teu}})
    assert s.lords[teu].assets["provender"] == pre + 1


def test_cmd_forage_winter_outside_friendly_stronghold_rejected() -> None:
    """4.7.1: in Winter, Forage requires Friendly Stronghold."""
    s = load_scenario("watland", seed=1)
    s.meta.box = 3  # early winter
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    # Move to a non-stronghold (region) locale.
    s.lords[teu].location = "harrien"
    _start_command_with(s, teu)
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "cmd_forage", "side": "teutonic", "args": {"lord_id": teu}})
    assert exc.value.code == "forage_seasonal"


def test_cmd_forage_ravaged_locale_rejected() -> None:
    s = load_scenario("watland", seed=1)
    s.meta.box = 1  # summer
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.locales[s.lords[teu].location].russian_ravaged = True
    _start_command_with(s, teu)
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "cmd_forage", "side": "teutonic", "args": {"lord_id": teu}})
    assert exc.value.code == "ravaged"


def test_cmd_ravage_requires_enemy_territory() -> None:
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    # Lord on own territory.
    _start_command_with(s, teu)
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "cmd_ravage", "side": "teutonic", "args": {"lord_id": teu}})
    assert exc.value.code in ("own_territory", "friendly")


def test_cmd_ravage_places_marker_and_loots_when_non_region() -> None:
    """4.7.2: ravaging a Town adds Provender + Loot; +0.5 VP."""
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    # Move to an enemy (Russian) town that's not Conquered/Ravaged.
    s.lords[teu].location = "tesovo"  # Town in Rus territory
    s.locales["tesovo"].russian_conquered = 0
    s.locales["tesovo"].russian_ravaged = False
    s.locales["tesovo"].teutonic_ravaged = False
    _start_command_with(s, teu)
    pre_prov = s.lords[teu].assets.get("provender", 0)
    pre_loot = s.lords[teu].assets.get("loot", 0)
    pre_vp = s.calendar.teutonic_vp
    apply_action(s, {"type": "cmd_ravage", "side": "teutonic", "args": {"lord_id": teu}})
    assert s.locales["tesovo"].teutonic_ravaged is True
    assert s.lords[teu].assets["provender"] == pre_prov + 1
    assert s.lords[teu].assets.get("loot", 0) == pre_loot + 1
    assert s.calendar.teutonic_vp == pre_vp + 0.5


def test_cmd_pass_forfeits_remaining_actions() -> None:
    """4.7.5: Pass forfeits unused actions; ends card."""
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    _start_command_with(s, teu)
    apply_action(s, {"type": "cmd_pass", "side": "teutonic", "args": {"lord_id": teu}})
    assert s.campaign_turn.actions_remaining == 0
    assert s.campaign_turn.in_feed_pay_disband is True


def test_cmd_sail_winter_rejected() -> None:
    """4.7.3: Sail forbidden in Winter."""
    s = load_scenario("watland", seed=1)
    s.meta.box = 3  # early winter
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].location = "riga"  # seaport
    _start_command_with(s, teu)
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "cmd_sail", "side": "teutonic",
                          "args": {"lord_id": teu, "destination": "reval"}})
    assert exc.value.code == "winter"


def test_cmd_sail_summer_to_seaport() -> None:
    """4.7.3: Sail Seaport->Seaport in Summer."""
    s = load_scenario("watland", seed=1)
    s.meta.box = 1  # summer
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].location = "riga"
    _start_command_with(s, teu)
    apply_action(s, {"type": "cmd_sail", "side": "teutonic",
                     "args": {"lord_id": teu, "destination": "reval"}})
    assert s.lords[teu].location == "reval"
    assert s.campaign_turn.in_feed_pay_disband is True


def test_cmd_supply_seat_source_simple_route() -> None:
    """4.6: Supply with one Seat Source via single Way adds 1 Provender."""
    s = load_scenario("watland", seed=1)
    s.meta.box = 1  # summer (to allow Carts)
    from nevsky.static_data import load_lords, load_ways
    static = load_lords()
    ways = load_ways()
    pick = None
    for lid, lord in s.lords.items():
        if lord.side != "teutonic" or lord.state != "mustered":
            continue
        for seat in static[lid].get("primary_seats", []):
            for w in ways:
                if w["type"] != "trackway":
                    continue
                if w["a"] == seat:
                    pick = (lid, seat, w["b"]); break
                if w["b"] == seat:
                    pick = (lid, seat, w["a"]); break
            if pick:
                break
        if pick:
            break
    if pick is None:
        pytest.skip("no Teutonic lord with a trackway from his Seat in watland")
    teu, seat, adj = pick
    s.lords[teu].location = adj
    s.lords[teu].assets["cart"] = 1
    _start_command_with(s, teu)
    pre = s.lords[teu].assets.get("provender", 0)
    apply_action(s, {
        "type": "cmd_supply", "side": "teutonic",
        "args": {"lord_id": teu, "sources": [{"locale_id": seat, "route": [seat, adj], "transport": "cart"}]},
    })
    assert s.lords[teu].assets["provender"] == pre + 1
