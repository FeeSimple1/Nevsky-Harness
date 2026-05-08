"""Tests for Phase 4c event resolvers."""

from __future__ import annotations

import pytest

from nevsky.actions import IllegalAction, apply_action
from nevsky.events import (
    apply_calendar_shift_hold,
    apply_lordship_plus_2,
    resolve_hold_event,
    resolve_immediate_event,
)
from nevsky.scenarios import load_scenario
from nevsky.state import GameState


def _put_cylinder_at(s: GameState, lord_id: str, box: int) -> None:
    for cb in s.calendar.boxes:
        if lord_id in cb.cylinders:
            cb.cylinders.remove(lord_id)
    if lord_id in s.calendar.off_left:
        s.calendar.off_left.remove(lord_id)
    if lord_id in s.calendar.off_right:
        s.calendar.off_right.remove(lord_id)
    s.calendar.boxes[box - 1].cylinders.append(lord_id)


def _put_service_at(s: GameState, lord_id: str, box: int) -> None:
    for cb in s.calendar.boxes:
        if lord_id in cb.service_markers:
            cb.service_markers.remove(lord_id)
    if lord_id in s.calendar.off_right:
        s.calendar.off_right.remove(lord_id)
    s.calendar.boxes[box - 1].service_markers.append(lord_id)


# --- T1 Grand Prince favors a son -------------------------------------------


def test_t1_grand_prince_shifts_aleksandr_left() -> None:
    """T1: shift Aleksandr 2 boxes left."""
    s = load_scenario("return_of_the_prince", seed=1)
    _put_cylinder_at(s, "aleksandr", 5)
    res = resolve_immediate_event(s, "T1", {"target": "aleksandr", "direction": "left"})
    assert res["new_box"] == 3
    assert "aleksandr" in s.calendar.boxes[2].cylinders


def test_t1_can_shift_service_marker() -> None:
    s = load_scenario("return_of_the_prince", seed=1)
    _put_service_at(s, "aleksandr", 5)
    res = resolve_immediate_event(s, "T1", {"target": "service:aleksandr", "direction": "right"})
    assert res["new_box"] == 7


# --- T2 Torzhok -------------------------------------------------------------


def test_t2_removes_3_coin_from_veche() -> None:
    """T2 Torzhok: remove 3 Coin from Veche."""
    s = load_scenario("watland", seed=1)
    s.veche.coin = 5
    res = resolve_immediate_event(s, "T2", {"target": "veche"})
    assert s.veche.coin == 2
    assert res["coin_removed"] == 3


def test_t2_removes_3_assets_from_domash() -> None:
    s = load_scenario("watland", seed=1)
    s.lords["domash"].assets = {"coin": 2, "loot": 1, "provender": 4}
    res = resolve_immediate_event(s, "T2", {"target": "domash"})
    total_removed = sum(res["removed"].values())
    assert total_removed == 3


# --- T11 Pope Gregory -------------------------------------------------------


def test_t11_shifts_teuton_and_adds_crusade() -> None:
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "ready")
    _put_cylinder_at(s, teu, 5)
    if "T11" in s.decks.teutonic.capabilities_in_play:
        s.decks.teutonic.capabilities_in_play.remove("T11")
    res = resolve_immediate_event(s, "T11", {"target": teu})
    assert res["new_box"] == 4
    assert "T11" in s.decks.teutonic.capabilities_in_play


# --- R10 Batu Khan ----------------------------------------------------------


def test_r10_shifts_andreas_cylinder() -> None:
    s = load_scenario("watland", seed=1)
    _put_cylinder_at(s, "andreas", 5)
    res = resolve_immediate_event(s, "R10", {"target": "andreas", "direction": "left", "boxes": 2})
    assert res["new_box"] == 3


# --- R11 Valdemar (this-levy block) -----------------------------------------


def test_r11_blocks_knud_and_abel_this_levy() -> None:
    """R11: shift Knud&Abel 1 box and block Muster of/by them this Levy."""
    s = load_scenario("watland", seed=1)
    _put_cylinder_at(s, "knud_and_abel", 4)
    res = resolve_immediate_event(s, "R11", {"target": "knud_and_abel", "direction": "left", "boxes": 1})
    assert "knud_and_abel" in s.meta.block_lords_this_levy_t
    assert res["shift"] == 3


def test_r11_block_actually_prevents_muster() -> None:
    """R11 + muster_lord: blocked Lord cannot be Mustered."""
    s = load_scenario("watland", seed=1)
    s.meta.levy_step = "muster"
    s.meta.active_player = "teutonic"
    s.meta.block_lords_this_levy_t = ["knud_and_abel"]
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {
            "type": "muster_lord", "side": "teutonic",
            "args": {"by_lord": teu, "target_lord": "knud_and_abel", "seat": "reval"},
        })
    assert exc.value.code == "blocked_this_levy"


# --- R15 Death of the Pope --------------------------------------------------


def test_r15_discards_william_of_modena() -> None:
    s = load_scenario("watland", seed=1)
    s.decks.teutonic.capabilities_in_play.append("T13")
    s.legate.william_of_modena_in_play = True
    s.legate.location = "locale"
    s.legate.locale_id = "riga"
    res = resolve_immediate_event(s, "R15", {})
    assert res["modena_discarded"] is True
    assert "T13" not in s.decks.teutonic.capabilities_in_play
    assert "T13" in s.decks.teutonic.discard
    assert s.legate.william_of_modena_in_play is False
    assert s.legate.location == "card"


# --- R16 Tempest ------------------------------------------------------------


def test_r16_removes_all_ships_no_cogs() -> None:
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].assets["ship"] = 4
    res = resolve_immediate_event(s, "R16", {"target": teu})
    assert res["ships_removed"] == 4
    assert s.lords[teu].assets.get("ship", 0) == 0


def test_r16_with_cogs_removes_half_round_up() -> None:
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].assets["ship"] = 5
    s.lords[teu].this_lord_capabilities = ["T18"]  # Cogs
    res = resolve_immediate_event(s, "R16", {"target": teu})
    # Half rounded up of 5 kept = 3; removed = 2.
    assert res["ships_removed"] == 2
    assert s.lords[teu].assets["ship"] == 3


# --- T14 / R18 Bountiful Harvest --------------------------------------------


def test_t14_removes_russian_ravaged_in_livonia() -> None:
    s = load_scenario("watland", seed=1)
    s.locales["harrien"].russian_ravaged = True
    s.calendar.russian_vp += 0.5
    pre = s.calendar.russian_vp
    res = resolve_immediate_event(s, "T14", {"locale": "harrien"})
    assert s.locales["harrien"].russian_ravaged is False
    assert s.calendar.russian_vp == pre - 0.5


def test_r18_removes_teutonic_ravaged_in_rus() -> None:
    s = load_scenario("watland", seed=1)
    s.locales["tesovo"].teutonic_ravaged = True
    s.calendar.teutonic_vp += 0.5
    pre = s.calendar.teutonic_vp
    res = resolve_immediate_event(s, "R18", {"locale": "tesovo"})
    assert s.locales["tesovo"].teutonic_ravaged is False
    assert s.calendar.teutonic_vp == pre - 0.5


# --- Lordship +2 holds ------------------------------------------------------


def test_lordship_plus_2_increases_budget() -> None:
    """T7 Tverdilo: +2 Lordship to Hermann or Yaroslav."""
    s = load_scenario("watland", seed=1)
    res = apply_lordship_plus_2(s, "T7", "hermann")
    assert s.meta.lordship_bonus["hermann"] == 2
    assert res["bonus"] == 2


def test_lordship_plus_2_rejects_wrong_target() -> None:
    s = load_scenario("watland", seed=1)
    with pytest.raises(IllegalAction):
        apply_lordship_plus_2(s, "T7", "andreas")  # T7 only Hermann/Yaroslav


def test_aow_lordship_plus_2_action_consumes_card() -> None:
    """The CLI action removes the card from holds and adds +2 Lordship."""
    s = load_scenario("watland", seed=1)
    s.meta.levy_step = "muster"
    s.meta.active_player = "teutonic"
    s.decks.teutonic.holds = ["T7"]
    apply_action(s, {
        "type": "aow_lordship_plus_2", "side": "teutonic",
        "args": {"card_id": "T7", "lord_id": "hermann", "mode": "lordship"},
    })
    assert "T7" not in s.decks.teutonic.holds
    assert "T7" in s.decks.teutonic.discard
    assert s.meta.lordship_bonus["hermann"] == 2


def test_lordship_bonus_extends_muster_budget() -> None:
    """Spending Lordship beyond base requires the +2 bonus."""
    s = load_scenario("watland", seed=1)
    s.meta.levy_step = "muster"
    s.meta.active_player = "teutonic"
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    from nevsky.static_data import load_lords as _ll
    base = int(_ll()[teu]["ratings"]["lordship"])
    s.lords[teu].lordship_used = base  # at base budget
    # Without bonus: spend rejected.
    from nevsky.actions import _spend_lordship
    with pytest.raises(IllegalAction):
        _spend_lordship(s, teu)
    # With bonus +2: 2 more allowed.
    s.lords[teu].lordship_used = base
    s.meta.lordship_bonus[teu] = 2
    _spend_lordship(s, teu)
    assert s.lords[teu].lordship_used == base + 1


# --- R3 Pogost (hold) -------------------------------------------------------


def test_pogost_adds_4_provender_to_lord_in_rus() -> None:
    s = load_scenario("watland", seed=1)
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered" and l.location == "novgorod")
    pre = s.lords[rus].assets.get("provender", 0)
    res = resolve_hold_event(s, "R3", {"target": rus})
    new = s.lords[rus].assets["provender"]
    assert new == min(8, pre + 4)


# --- aow_play_hold action ---------------------------------------------------


def test_aow_play_hold_consumes_card_and_resolves() -> None:
    s = load_scenario("watland", seed=1)
    s.decks.russian.holds = ["R3"]
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered" and l.location == "novgorod")
    apply_action(s, {
        "type": "aow_play_hold", "side": "russian",
        "args": {"card_id": "R3", "target": rus},
    })
    assert "R3" not in s.decks.russian.holds
    assert "R3" in s.decks.russian.discard
