"""Tests for 4.1 Plan and 4.2 Activation."""

from __future__ import annotations

import pytest

from nevsky.actions import IllegalAction, apply_action
from nevsky.campaign import _plan_target_size
from nevsky.scenarios import load_scenario
from nevsky.state import GameState


def _enter_campaign(s: GameState) -> None:
    """Skip Levy and place state at start of Campaign / Plan step."""
    s.meta.phase = "campaign"
    s.meta.campaign_step = "plan"
    s.meta.plan_complete_t = False
    s.meta.plan_complete_r = False
    s.meta.active_player = "teutonic"


def test_plan_target_size_by_season() -> None:
    """SoP 4.1: 4 in Early/Late Winter, 5 in Rasputitsa, 6 in Summer."""
    assert _plan_target_size(1) == 6   # box 1 summer
    assert _plan_target_size(3) == 4   # early winter
    assert _plan_target_size(5) == 4   # late winter
    assert _plan_target_size(7) == 5   # rasputitsa
    assert _plan_target_size(9) == 6   # summer year 2


def test_plan_add_card_appends_lord_or_pass() -> None:
    s = load_scenario("watland", seed=1)
    _enter_campaign(s)
    teu_mustered = [lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered"][0]
    apply_action(s, {"type": "plan_add_card", "side": "teutonic", "args": {"card": teu_mustered}})
    apply_action(s, {"type": "plan_add_card", "side": "teutonic", "args": {"card": "pass"}})
    assert s.decks.teutonic.plan == [teu_mustered, "pass"]


def test_plan_add_card_max_three_per_lord() -> None:
    """4.1: each Lord has 3 Command cards; same Lord max 3 entries."""
    s = load_scenario("watland", seed=1)
    _enter_campaign(s)
    lid = [l for l, lord in s.lords.items() if lord.side == "teutonic" and lord.state == "mustered"][0]
    for _ in range(3):
        apply_action(s, {"type": "plan_add_card", "side": "teutonic", "args": {"card": lid}})
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "plan_add_card", "side": "teutonic", "args": {"card": lid}})
    assert exc.value.code == "card_limit"


def test_plan_add_card_unmustered_rejected() -> None:
    s = load_scenario("watland", seed=1)
    _enter_campaign(s)
    not_mustered = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state != "mustered")
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "plan_add_card", "side": "teutonic", "args": {"card": not_mustered}})
    assert exc.value.code == "bad_card"


def test_finalize_plan_requires_target_size() -> None:
    s = load_scenario("watland", seed=1)
    _enter_campaign(s)
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "finalize_plan", "side": "teutonic", "args": {}})
    assert exc.value.code == "plan_size_mismatch"


def _fill_plan(s: GameState, side: str) -> None:
    target = _plan_target_size(s.meta.box)
    deck = s.decks.teutonic if side == "teutonic" else s.decks.russian
    while len(deck.plan) < target:
        deck.plan.append("pass")


def test_both_finalize_advances_to_command_step() -> None:
    s = load_scenario("watland", seed=1)
    _enter_campaign(s)
    _fill_plan(s, "teutonic")
    _fill_plan(s, "russian")
    apply_action(s, {"type": "finalize_plan", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "finalize_plan", "side": "russian", "args": {}})
    assert s.meta.campaign_step == "command"
    assert s.campaign_turn.next_to_reveal == "teutonic"


def test_command_reveal_pass_card_enters_fpd() -> None:
    s = load_scenario("watland", seed=1)
    _enter_campaign(s)
    s.decks.teutonic.plan = ["pass"] * _plan_target_size(s.meta.box)
    s.decks.russian.plan = ["pass"] * _plan_target_size(s.meta.box)
    apply_action(s, {"type": "finalize_plan", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "finalize_plan", "side": "russian", "args": {}})
    apply_action(s, {"type": "command_reveal", "side": "teutonic", "args": {}})
    assert s.campaign_turn.in_feed_pay_disband is True
    assert s.campaign_turn.active_card == "pass"
    assert s.campaign_turn.actions_remaining == 0


def test_command_reveal_lord_card_sets_actions_to_command_rating() -> None:
    s = load_scenario("watland", seed=1)
    _enter_campaign(s)
    teu_mustered = [lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered"][0]
    target = _plan_target_size(s.meta.box)
    s.decks.teutonic.plan = [teu_mustered] + ["pass"] * (target - 1)
    s.decks.russian.plan = ["pass"] * target
    apply_action(s, {"type": "finalize_plan", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "finalize_plan", "side": "russian", "args": {}})
    apply_action(s, {"type": "command_reveal", "side": "teutonic", "args": {}})
    from nevsky.static_data import load_lords
    expected = int(load_lords()[teu_mustered]["ratings"]["command"])
    assert s.campaign_turn.actions_remaining == expected
    assert s.campaign_turn.active_lord == teu_mustered
