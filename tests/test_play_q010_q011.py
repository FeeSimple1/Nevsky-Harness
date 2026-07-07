"""Regression tests for Q-010 and Q-011 (adjudicated 2026-07-06).

Q-010: Storm (4.5.2) and Sally (4.5.3) cost ONE Command action, not the
entire card. D-R203's pristine gate is narrowed to Siege/Sail/Tax.

Q-011: the resolve_battle max_rounds=10 rule-cap is lifted (4.4.2 Battles
continue until a side Concedes or all its Lords Rout). A no-progress guard
plus a far safety bound guarantee termination for degenerate arrays.
"""

from __future__ import annotations

import inspect

import pytest

from nevsky.actions import IllegalAction, apply_action
from nevsky.scenarios import load_scenario
from nevsky.state import GameState


def _start_command_with(s: GameState, lord_id: str) -> None:
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = s.lords[lord_id].side
    s.campaign_turn.next_to_reveal = s.lords[lord_id].side
    s.campaign_turn.active_card = lord_id
    s.campaign_turn.active_lord = lord_id
    from nevsky.static_data import load_lords
    s.campaign_turn.actions_remaining = int(
        load_lords()[lord_id]["ratings"]["command"]
    )
    s.campaign_turn.in_feed_pay_disband = False
    s.lords[lord_id].moved_fought = False


def _side_types(s: GameState, side: str) -> set:
    from nevsky.legal_moves import legal_moves
    return {m["type"] for m in legal_moves(s, with_previews=False)
            if m.get("side") == side}


# --- Q-010: Storm / Sally are one-action, not entire-card ------------------


def test_q010_storm_enumerated_on_non_pristine_card() -> None:
    s = load_scenario("pleskau", seed=1)
    teu = next(lid for lid, l in s.lords.items()
               if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].location = "pskov"
    rus = next(lid for lid, l in s.lords.items()
               if l.side == "russian" and l.state == "mustered")
    s.lords[rus].location = "pskov"
    s.locales["pskov"].siege_markers = 2
    _start_command_with(s, teu)
    s.campaign_turn.actions_remaining -= 1  # non-pristine
    assert "cmd_storm" in _side_types(s, "teutonic")


def test_q010_storm_handler_accepts_non_pristine_card() -> None:
    s = load_scenario("pleskau", seed=1)
    teu = next(lid for lid, l in s.lords.items()
               if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].location = "pskov"
    rus = next(lid for lid, l in s.lords.items()
               if l.side == "russian" and l.state == "mustered")
    s.lords[rus].location = "pskov"
    s.locales["pskov"].siege_markers = 2
    _start_command_with(s, teu)
    s.campaign_turn.actions_remaining -= 1  # non-pristine
    res = apply_action(
        s, {"type": "cmd_storm", "side": "teutonic", "args": {"lord_id": teu}}
    )
    assert "battle" in res  # resolved rather than raising must_be_full_card


def test_q010_sally_enumerated_on_non_pristine_card() -> None:
    s = load_scenario("pleskau", seed=1)
    teu = next(lid for lid, l in s.lords.items()
               if l.side == "teutonic" and l.state == "mustered")
    rus = next(lid for lid, l in s.lords.items()
               if l.side == "russian" and l.state == "mustered")
    s.lords[rus].location = "pskov"
    s.lords[rus].in_stronghold = True
    s.lords[teu].location = "pskov"
    s.lords[teu].in_stronghold = False
    s.locales["pskov"].siege_markers = 2
    _start_command_with(s, rus)
    from nevsky.campaign import _is_besieged
    assert _is_besieged(s, rus)
    s.campaign_turn.actions_remaining -= 1  # non-pristine
    assert "cmd_sally" in _side_types(s, "russian")


def test_q010_siege_still_requires_pristine_card() -> None:
    """Regression: Siege (4.5.1) stays entire-card."""
    s = load_scenario("pleskau", seed=1)
    teu = next(lid for lid, l in s.lords.items()
               if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].location = "pskov"
    s.locales["pskov"].siege_markers = 1
    _start_command_with(s, teu)
    s.campaign_turn.actions_remaining -= 1  # non-pristine
    assert "cmd_siege" not in _side_types(s, "teutonic")
    with pytest.raises(IllegalAction) as exc:
        apply_action(
            s, {"type": "cmd_siege", "side": "teutonic", "args": {"lord_id": teu}}
        )
    assert exc.value.code == "must_be_full_card"


# --- Q-011: the 10-round rule cap is lifted --------------------------------


def test_q011_resolve_battle_default_max_rounds_is_none() -> None:
    from nevsky import battle
    sig = inspect.signature(battle.resolve_battle)
    assert sig.parameters["max_rounds"].default is None
    assert battle._BATTLE_ROUND_SAFETY_CAP >= 100


def test_q011_degenerate_array_terminates_early_without_safety_bound() -> None:
    from nevsky import battle
    from nevsky.battle import BattleDecisionContext, resolve_battle
    s = load_scenario("watland", seed=1)
    teu = [lid for lid, l in s.lords.items() if l.side == "teutonic"][0]
    rus = [lid for lid, l in s.lords.items() if l.side == "russian"][0]
    for lid in (teu, rus):
        s.lords[lid].state = "mustered"
        s.lords[lid].location = "pskov"
    s.lords[teu].forces = {"knights": 5, "sergeants": 5}
    s.lords[rus].forces = {"militia": 2}
    res = resolve_battle(
        s, attacker_side="russian", attacker_lords=[rus],
        defender_lords=[teu], decision_ctx=BattleDecisionContext(),
    )
    if res.get("stalemate"):
        assert res.get("safety_cap_hit") is False
        assert res["rounds"] < battle._BATTLE_ROUND_SAFETY_CAP
        assert res["winner"] == "teutonic"  # defender holds the field
