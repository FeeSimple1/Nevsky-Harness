"""Tests for 3.2 Pay handlers."""

from __future__ import annotations

import pytest

from nevsky.actions import IllegalAction, apply_action
from nevsky.scenarios import load_scenario
from nevsky.state import GameState


def _to_pay_step(s: GameState) -> None:
    """Advance state from arts_of_war to pay (test helper)."""
    s.meta.levy_step = "pay"
    s.meta.active_player = "teutonic"
    s.meta.levy_step_completed_t = False
    s.meta.levy_step_completed_r = False


def _give_lord_coin(s: GameState, lid: str, n: int = 3) -> None:
    s.lords[lid].assets["coin"] = n


def _give_lord_loot(s: GameState, lid: str, n: int = 3) -> None:
    s.lords[lid].assets["loot"] = n


def _service_box(s: GameState, lid: str) -> int | None:
    if lid in s.calendar.off_right:
        return 17
    for cb in s.calendar.boxes:
        if lid in cb.service_markers:
            return cb.box
    return None


def test_pay_with_coin_own_service_shifts_one_box(tmp_path) -> None:
    """3.2.1: Lord pays own Coin to shift own Service marker right."""
    s = load_scenario("watland", seed=42)
    _to_pay_step(s)
    teu_mustered = [lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered"]
    payer = teu_mustered[0]
    pre = _service_box(s, payer)
    assert pre is not None
    _give_lord_coin(s, payer, 2)
    apply_action(s, {
        "type": "pay_with_coin", "side": "teutonic",
        "args": {"from": f"lord:{payer}", "target_lord": payer, "units": 1},
    })
    assert _service_box(s, payer) == min(pre + 1, 17)
    assert s.lords[payer].assets.get("coin", 0) == 1


def test_pay_with_coin_insufficient_funds_raises() -> None:
    s = load_scenario("watland", seed=42)
    _to_pay_step(s)
    payer = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[payer].assets.pop("coin", None)
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {
            "type": "pay_with_coin", "side": "teutonic",
            "args": {"from": f"lord:{payer}", "target_lord": payer, "units": 1},
        })
    assert exc.value.code == "insufficient_funds"


def test_pay_with_veche_coin_blocked_for_besieged_lord() -> None:
    """3.2.1: Veche Coin cannot reach a Besieged Russian Lord."""
    s = load_scenario("watland", seed=42)
    _to_pay_step(s)
    s.meta.active_player = "russian"
    s.meta.levy_step_completed_t = True
    s.veche.coin = 4
    target = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    # Besiege the target Lord inside his Stronghold.
    s.locales[s.lords[target].location].siege_markers = 1
    s.lords[target].in_stronghold = True
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {
            "type": "pay_with_coin", "side": "russian",
            "args": {"from": "veche", "target_lord": target, "units": 1},
        })
    assert exc.value.code == "veche_cannot_reach_besieged"


def test_pay_with_veche_coin_consumes_and_shifts() -> None:
    s = load_scenario("watland", seed=42)
    _to_pay_step(s)
    s.meta.active_player = "russian"
    s.meta.levy_step_completed_t = True
    s.veche.coin = 4
    target = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    pre = _service_box(s, target)
    apply_action(s, {
        "type": "pay_with_coin", "side": "russian",
        "args": {"from": "veche", "target_lord": target, "units": 2},
    })
    assert s.veche.coin == 2
    assert _service_box(s, target) == min(pre + 2, 17)


def test_pay_with_loot_requires_friendly_locale() -> None:
    """3.2.2: Loot may only be spent at a Friendly Locale."""
    s = load_scenario("watland", seed=42)
    _to_pay_step(s)
    payer = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    _give_lord_loot(s, payer, 3)
    # Place a Russian Lord at the same locale to make the locale unfriendly.
    rus_lord = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    s.lords[rus_lord].location = s.lords[payer].location
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {
            "type": "pay_with_loot", "side": "teutonic",
            "args": {"from_lord": payer, "target_lord": payer, "units": 1},
        })
    assert exc.value.code == "loot_locale_constraint"


def test_pay_co_located_other_lord_allowed() -> None:
    """3.2.1: Lord-Coin can pay co-located own-side Lord's Service."""
    s = load_scenario("watland", seed=42)
    _to_pay_step(s)
    teu = [lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered"]
    payer, target = teu[0], teu[1]
    _give_lord_coin(s, payer, 3)
    s.lords[target].location = s.lords[payer].location  # co-locate
    pre = _service_box(s, target)
    apply_action(s, {
        "type": "pay_with_coin", "side": "teutonic",
        "args": {"from": f"lord:{payer}", "target_lord": target, "units": 1},
    })
    assert _service_box(s, target) == min(pre + 1, 17)


def test_pay_lord_coin_different_locale_rejected() -> None:
    """3.2.1: cannot Pay another Lord's Service from a different Locale."""
    s = load_scenario("watland", seed=42)
    _to_pay_step(s)
    teu = [lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered"]
    if len(teu) < 2:
        pytest.skip("watland mustered Teuton lord count < 2")
    payer, target = teu[0], teu[1]
    _give_lord_coin(s, payer, 3)
    # Ensure they are at different locations.
    if s.lords[payer].location == s.lords[target].location:
        # Put target somewhere else; pick any locale id.
        s.lords[target].location = "novgorod"
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {
            "type": "pay_with_coin", "side": "teutonic",
            "args": {"from": f"lord:{payer}", "target_lord": target, "units": 1},
        })
    assert exc.value.code == "pay_target_not_collocated"
