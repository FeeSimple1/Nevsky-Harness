"""Tests for 3.1 Arts of War handlers."""

from __future__ import annotations

from nevsky.actions import IllegalAction, apply_action
from nevsky.scenarios import load_scenario


def test_aow_shuffle_collapses_deck_and_discard() -> None:
    """3.1.1: shuffle pools deck + discard into a single shuffled deck."""
    s = load_scenario("pleskau", seed=42)
    s.decks.teutonic.discard.append("T1")
    if "T1" in s.decks.teutonic.deck:
        s.decks.teutonic.deck.remove("T1")
    pre_total = len(s.decks.teutonic.deck) + len(s.decks.teutonic.discard)
    apply_action(s, {"type": "aow_shuffle", "side": "teutonic", "args": {}})
    assert len(s.decks.teutonic.discard) == 0
    assert len(s.decks.teutonic.deck) == pre_total
    assert "T1" in s.decks.teutonic.deck


def test_aow_shuffle_excludes_held_and_in_play() -> None:
    """3.1.1: holds, capabilities_in_play, removed, this_levy_events,
    this_campaign_events, pending_draw all stay where they are."""
    s = load_scenario("pleskau", seed=42)
    s.decks.teutonic.holds.append("T2")
    s.decks.teutonic.deck.remove("T2") if "T2" in s.decks.teutonic.deck else None
    s.decks.teutonic.capabilities_in_play.append("T3")
    if "T3" in s.decks.teutonic.deck:
        s.decks.teutonic.deck.remove("T3")
    apply_action(s, {"type": "aow_shuffle", "side": "teutonic", "args": {}})
    assert "T2" in s.decks.teutonic.holds
    assert "T3" in s.decks.teutonic.capabilities_in_play
    assert "T2" not in s.decks.teutonic.deck
    assert "T3" not in s.decks.teutonic.deck


def test_aow_draw_two_cards() -> None:
    """3.1: draw 2 cards into pending_draw."""
    s = load_scenario("pleskau", seed=42)
    apply_action(s, {"type": "aow_shuffle", "side": "teutonic", "args": {}})
    pre = len(s.decks.teutonic.deck)
    apply_action(s, {"type": "aow_draw", "side": "teutonic", "args": {}})
    assert len(s.decks.teutonic.pending_draw) == 2
    assert len(s.decks.teutonic.deck) == pre - 2


def test_aow_draw_blocked_when_pending_nonempty() -> None:
    """Cannot redraw before implementing existing pending cards."""
    s = load_scenario("pleskau", seed=42)
    apply_action(s, {"type": "aow_shuffle", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "aow_draw", "side": "teutonic", "args": {}})
    try:
        apply_action(s, {"type": "aow_draw", "side": "teutonic", "args": {}})
        assert False, "expected IllegalAction"
    except IllegalAction as e:
        assert e.code == "pending_draw_nonempty"


def test_aow_implement_first_levy_capability_side_wide() -> None:
    """3.1.2: first Levy implements bottom-half (capability)."""
    s = load_scenario("pleskau", seed=42)
    s.decks.teutonic.deck = []
    s.decks.teutonic.pending_draw = ["T11"]  # T11 Crusade is side-wide capability
    apply_action(s, {"type": "aow_implement_card", "side": "teutonic", "args": {}})
    assert "T11" in s.decks.teutonic.capabilities_in_play
    assert s.decks.teutonic.pending_draw == []


def test_aow_implement_no_event_card_removes_permanently() -> None:
    """3.1.3 (2E): drawn No-Event/No-Capability cards are removed from play."""
    s = load_scenario("watland", seed=42)
    s.decks.teutonic.deck = []
    s.decks.teutonic.pending_draw = ["T_no_event_1"]
    apply_action(s, {"type": "aow_implement_card", "side": "teutonic", "args": {}})
    assert "T_no_event_1" in s.decks.teutonic.removed


def test_aow_crusade_on_novgorod_retains_no_event() -> None:
    """6.0 Crusade on Novgorod special: No-Event card returns to discard, not removed."""
    s = load_scenario("crusade_on_novgorod", seed=42)
    assert s.meta.special_rules.get("keep_no_event_cards") is True
    s.decks.teutonic.deck = []
    s.decks.teutonic.pending_draw = ["T_no_event_1"]
    apply_action(s, {"type": "aow_implement_card", "side": "teutonic", "args": {}})
    assert "T_no_event_1" in s.decks.teutonic.discard
    assert "T_no_event_1" not in s.decks.teutonic.removed


def test_aow_implement_first_levy_this_lord_capability_tucks_under_lord() -> None:
    """3.4.4: this-lord capability tucks under the chosen Lord's mat."""
    s = load_scenario("watland", seed=42)
    s.decks.teutonic.deck = []
    s.decks.teutonic.pending_draw = ["T2"]  # T2 Crossbowmen, this_lord scope
    target = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    apply_action(
        s,
        {"type": "aow_implement_card", "side": "teutonic", "args": {"lord_id": target}},
    )
    assert "T2" in s.lords[target].this_lord_capabilities


def test_aow_subsequent_levy_event_immediate_goes_to_discard() -> None:
    """3.1.3: immediate Event reveals and discards."""
    s = load_scenario("pleskau", seed=42)
    s.meta.first_levy_done = True
    s.decks.teutonic.deck = []
    # T2 Torzhok -- immediate event per cards.json (event_persistence=immediate)
    s.decks.teutonic.pending_draw = ["T2"]
    apply_action(s, {"type": "aow_implement_card", "side": "teutonic", "args": {}})
    assert "T2" in s.decks.teutonic.discard


def test_aow_subsequent_levy_hold_event_goes_to_holds() -> None:
    """3.1.3: hold-persistence Event goes to holds for later play."""
    s = load_scenario("pleskau", seed=42)
    s.meta.first_levy_done = True
    s.decks.teutonic.deck = []
    s.decks.teutonic.pending_draw = ["T7"]  # T7 Tverdilo, hold
    apply_action(s, {"type": "aow_implement_card", "side": "teutonic", "args": {}})
    assert "T7" in s.decks.teutonic.holds


def test_aow_discard_this_levy_clears_those_events() -> None:
    """3.5.3: both sides discard This-Levy events."""
    s = load_scenario("pleskau", seed=42)
    s.meta.levy_step = "call_to_arms"
    s.meta.active_player = "teutonic"
    s.decks.teutonic.this_levy_events = ["T7"]
    apply_action(s, {"type": "aow_discard_this_levy", "side": "teutonic", "args": {}})
    assert "T7" in s.decks.teutonic.discard
    assert s.decks.teutonic.this_levy_events == []
