"""Tests for 3.5 Call to Arms."""

from __future__ import annotations

import pytest

from nevsky.actions import IllegalAction, apply_action
from nevsky.scenarios import load_scenario
from nevsky.state import GameState


def _to_call_to_arms_step(s: GameState, side: str = "teutonic") -> None:
    s.meta.levy_step = "call_to_arms"
    s.meta.active_player = side
    s.meta.levy_step_completed_t = side == "russian"
    s.meta.levy_step_completed_r = False
    s.legate.acted_this_call_to_arms = False
    s.veche.acted_this_call_to_arms = False


def test_legate_arrives_requires_william_of_modena() -> None:
    """3.5.1: without William of Modena (T13), Teutons skip Call to Arms."""
    s = load_scenario("watland", seed=42)
    _to_call_to_arms_step(s, "teutonic")
    s.legate.william_of_modena_in_play = False
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {
            "type": "legate_arrives", "side": "teutonic",
            "args": {"bishopric": "riga"},
        })
    assert exc.value.code == "no_william"


def test_legate_arrives_must_use_bishopric() -> None:
    """3.5.1: ARRIVES placement is at one of Riga, Dorpat, Leal, Reval."""
    s = load_scenario("watland", seed=42)
    _to_call_to_arms_step(s, "teutonic")
    s.legate.william_of_modena_in_play = True
    s.legate.location = "card"
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {
            "type": "legate_arrives", "side": "teutonic",
            "args": {"bishopric": "novgorod"},
        })
    assert exc.value.code == "bad_bishopric"


def test_legate_arrives_places_at_bishopric() -> None:
    s = load_scenario("watland", seed=42)
    _to_call_to_arms_step(s, "teutonic")
    s.legate.william_of_modena_in_play = True
    s.legate.location = "card"
    apply_action(s, {
        "type": "legate_arrives", "side": "teutonic",
        "args": {"bishopric": "dorpat"},
    })
    assert s.legate.location == "locale"
    assert s.legate.locale_id == "dorpat"


def test_veche_option_d_decline_only_when_aleksandr_or_andrey_ready() -> None:
    """3.5.2 Option D: requires Aleksandr or Andrey to be Ready."""
    s = load_scenario("watland", seed=42)
    _to_call_to_arms_step(s, "russian")
    # Move both princes off-Ready: place cylinders right of Levy box.
    levy_box = next(cb.box for cb in s.calendar.boxes if cb.has_levy_campaign_marker)
    target_box = min(levy_box + 2, 16)
    for prince in ("aleksandr", "andrey"):
        if prince in s.lords:
            for cb in s.calendar.boxes:
                if prince in cb.cylinders:
                    cb.cylinders.remove(prince)
            s.calendar.boxes[target_box - 1].cylinders.append(prince)
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {
            "type": "veche_action", "side": "russian",
            "args": {"option": "D"},
        })
    assert exc.value.code == "decline_unavailable"


def test_veche_option_d_adds_one_vp_marker() -> None:
    """3.5.2 Option D: gain one (and only one) VP marker even when both princes slid."""
    s = load_scenario("return_of_the_prince", seed=42)
    _to_call_to_arms_step(s, "russian")
    pre = s.veche.vp_markers
    # Force at least Andrey to be Ready.
    levy_box = next(cb.box for cb in s.calendar.boxes if cb.has_levy_campaign_marker)
    if "andrey" in s.lords:
        for cb in s.calendar.boxes:
            if "andrey" in cb.cylinders:
                cb.cylinders.remove("andrey")
        s.calendar.boxes[levy_box - 1].cylinders.append("andrey")
        if s.lords["andrey"].state != "ready":
            s.lords["andrey"].state = "ready"
    apply_action(s, {"type": "veche_action", "side": "russian", "args": {"option": "D"}})
    assert s.veche.vp_markers == min(pre + 1, 8)


def test_veche_option_b_consumes_vp_marker() -> None:
    """3.5.2 Option B: auto-Muster spends 1 VP marker."""
    s = load_scenario("watland", seed=42)
    _to_call_to_arms_step(s, "russian")
    s.veche.vp_markers = 3
    s.calendar.russian_vp = 3.0
    # Find a Ready Russian Lord with a Free Seat.
    levy_box = next(cb.box for cb in s.calendar.boxes if cb.has_levy_campaign_marker)
    target = None
    for lid, l in s.lords.items():
        if l.side != "russian" or l.state != "ready":
            continue
        for cb in s.calendar.boxes:
            if lid in cb.cylinders and cb.box <= levy_box:
                target = lid
                break
        if target:
            break
    if target is None:
        pytest.skip("no Ready Russian Lord in watland")
    from nevsky.actions import _free_seats_for
    free = _free_seats_for(s, target)
    if not free:
        pytest.skip("no free seat")
    apply_action(s, {
        "type": "veche_action", "side": "russian",
        "args": {"option": "B", "target_lord": target, "seat": free[0]},
    })
    assert s.veche.vp_markers == 2
    assert s.lords[target].state == "mustered"
    assert s.lords[target].location == free[0]


def test_veche_option_a_slides_two_boxes_left() -> None:
    """3.5.2 Option A (2E): slide one Lord cylinder 2 boxes LEFT (PAC's '1 box' is obsolete)."""
    s = load_scenario("watland", seed=42)
    _to_call_to_arms_step(s, "russian")
    s.veche.vp_markers = 1
    s.calendar.russian_vp = 1.0
    target = None
    pre_box = None
    for lid, l in s.lords.items():
        if l.side != "russian":
            continue
        for cb in s.calendar.boxes:
            if lid in cb.cylinders and cb.box >= 4:
                target = lid
                pre_box = cb.box
                break
        if target:
            break
    if target is None:
        # move some Russian cylinder to box 4
        any_ru = next(lid for lid, l in s.lords.items() if l.side == "russian")
        for cb in s.calendar.boxes:
            if any_ru in cb.cylinders:
                cb.cylinders.remove(any_ru)
        s.calendar.boxes[3].cylinders.append(any_ru)
        target = any_ru
        pre_box = 4
    apply_action(s, {
        "type": "veche_action", "side": "russian",
        "args": {"option": "A", "target_lord": target},
    })
    assert s.veche.vp_markers == 0
    new_box = pre_box - 2
    assert target in s.calendar.boxes[new_box - 1].cylinders


def test_sea_trade_R8_blocked_when_lovat_conquered() -> None:
    """3.5.2 sea_trade R8: blocked while Novgorod or Lovat Conquered by Teutons."""
    s = load_scenario("watland", seed=42)
    _to_call_to_arms_step(s, "russian")
    s.decks.russian.capabilities_in_play = ["R8"]
    s.locales["lovat"].teutonic_conquered = 1
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {
            "type": "veche_action", "side": "russian",
            "args": {"option": "sea_trade", "card_id": "R8"},
        })
    assert exc.value.code == "sea_trade_blocked"


def test_sea_trade_R9_blocked_in_winter() -> None:
    """R9 Baltic Sea Trade: no Coin in Early/Late Winter."""
    s = load_scenario("watland", seed=42)
    _to_call_to_arms_step(s, "russian")
    s.meta.box = 3  # early_winter per season table
    s.decks.russian.capabilities_in_play = ["R9"]
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {
            "type": "veche_action", "side": "russian",
            "args": {"option": "sea_trade", "card_id": "R9"},
        })
    assert exc.value.code == "sea_trade_winter"


def test_sea_trade_does_not_consume_once_per_segment_slot() -> None:
    """3.5.2 sea_trade can occur any time and does not block A/B/C/D this segment."""
    s = load_scenario("watland", seed=42)
    _to_call_to_arms_step(s, "russian")
    s.decks.russian.capabilities_in_play = ["R8"]
    s.veche.coin = 0
    pre_acted = s.veche.acted_this_call_to_arms
    apply_action(s, {
        "type": "veche_action", "side": "russian",
        "args": {"option": "sea_trade", "card_id": "R8"},
    })
    assert s.veche.acted_this_call_to_arms == pre_acted  # unchanged
    assert s.veche.coin == 1
