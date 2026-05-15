"""SMOKE-061 (Round 68): R15 Death of the Pope blocks T13 re-Levy this Levy.

R15 sets state.meta.special_rules.block_william_of_modena_this_levy = True
when the event fires. _h_levy_capability must reject any Levy of T13
(William of Modena) for the remainder of that Levy. The flag clears on
Levy → Campaign transition (covered elsewhere).
"""
from __future__ import annotations

import pytest

from nevsky.actions import IllegalAction, apply_action
from nevsky.events import _ev_death_of_pope
from nevsky.scenarios import load_scenario


def _to_muster_step(s):
    for _ in range(3):
        apply_action(s, {"type": "advance_step", "side": "teutonic"})
        apply_action(s, {"type": "advance_step", "side": "russian"})


def test_r15_blocks_t13_relevy_in_same_levy():
    """After R15 discards T13, Teutons cannot re-Levy T13 same Levy."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.decks.teutonic.capabilities_in_play.append("T13")
    _ev_death_of_pope(s, {})
    assert s.meta.special_rules.get("block_william_of_modena_this_levy") is True
    assert "T13" not in s.decks.teutonic.capabilities_in_play
    # Set up Heinrich as eligible Levyer (T13 elig = ALL Teuton)
    heinrich = s.lords["heinrich"]
    heinrich.state = "mustered"
    heinrich.location = "fellin"
    _to_muster_step(s)
    with pytest.raises(IllegalAction) as e:
        apply_action(s, {"type": "levy_capability", "side": "teutonic",
                          "args": {"by_lord": "heinrich", "card_id": "T13"}})
    assert e.value.code == "capability_blocked"
    assert "T13" not in s.decks.teutonic.capabilities_in_play


def test_r15_flag_clears_on_levy_to_campaign_transition():
    """Once the Levy ends, T13 may be Levied again (the block is per-Levy)."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.decks.teutonic.capabilities_in_play.append("T13")
    _ev_death_of_pope(s, {})
    assert s.meta.special_rules.get("block_william_of_modena_this_levy") is True
    # Advance Levy through to Campaign (full 5 step transitions)
    for _ in range(5):
        apply_action(s, {"type": "advance_step", "side": "teutonic"})
        apply_action(s, {"type": "advance_step", "side": "russian"})
    # After Levy -> Campaign, flag must be cleared
    assert s.meta.phase == "campaign"
    assert s.meta.special_rules.get("block_william_of_modena_this_levy") is None


def test_other_t_capabilities_unaffected_by_r15_flag():
    """R15 only blocks T13; other Teuton capabilities (T1..T18 except T13) Levy normally."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.decks.teutonic.capabilities_in_play.append("T13")
    _ev_death_of_pope(s, {})
    # Pick T8 Hillforts (eligibility "ALL Teuton" per data; should not be blocked)
    heinrich = s.lords["heinrich"]
    heinrich.state = "mustered"
    heinrich.location = "fellin"
    _to_muster_step(s)
    # T8 is in deck initially
    if "T8" not in s.decks.teutonic.deck and "T8" not in s.decks.teutonic.discard:
        # Put it there for the test
        s.decks.teutonic.deck.append("T8")
    r = apply_action(s, {"type": "levy_capability", "side": "teutonic",
                          "args": {"by_lord": "heinrich", "card_id": "T8"}})
    assert r["card_id"] == "T8"
