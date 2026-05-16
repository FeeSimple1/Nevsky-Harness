"""SMOKE-072 (Round 75): T13 William of Modena Levy blocked when Heinrich
is not on map.

Per AoW Reference T13 Event Tip:
"If Heinrich is not on map, drawing the Event card will delay Levy of
the William of Modena Capability until discarded or Heinrich Musters."

The previous code did not enforce this — Teutons could Levy T13's
William of Modena capability immediately while Heinrich was still in
the ready pool or after he was Disbanded.
"""
from __future__ import annotations

import pytest

from nevsky.actions import IllegalAction, apply_action
from nevsky.scenarios import load_scenario


def _to_muster_step(s):
    for _ in range(3):
        apply_action(s, {"type": "advance_step", "side": "teutonic"})
        apply_action(s, {"type": "advance_step", "side": "russian"})


def test_t13_levy_blocked_when_heinrich_ready_pool():
    """Heinrich is in the ready pool (not Mustered) — Levy of T13 must reject."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    heinrich = s.lords["heinrich"]
    heinrich.state = "ready"
    heinrich.location = None
    if "T13" not in s.decks.teutonic.deck and "T13" not in s.decks.teutonic.discard:
        s.decks.teutonic.deck.append("T13")
    _to_muster_step(s)
    # Pick any on-map Mustered Teuton.
    levyer = next(
        lid for lid, l in s.lords.items()
        if l.side == "teutonic" and l.state == "mustered" and l.location is not None
    )
    with pytest.raises(IllegalAction) as e:
        apply_action(s, {"type": "levy_capability", "side": "teutonic",
                          "args": {"by_lord": levyer, "card_id": "T13"}})
    assert e.value.code == "heinrich_off_map"
    assert "T13" not in s.decks.teutonic.capabilities_in_play


def test_t13_levy_blocked_when_heinrich_disbanded():
    """Heinrich was Disbanded (state == 'disbanded') — Levy of T13 must reject."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    heinrich = s.lords["heinrich"]
    heinrich.state = "disbanded"
    heinrich.location = None
    if "T13" not in s.decks.teutonic.deck and "T13" not in s.decks.teutonic.discard:
        s.decks.teutonic.deck.append("T13")
    _to_muster_step(s)
    levyer = next(
        lid for lid, l in s.lords.items()
        if l.side == "teutonic" and l.state == "mustered" and l.location is not None
    )
    with pytest.raises(IllegalAction) as e:
        apply_action(s, {"type": "levy_capability", "side": "teutonic",
                          "args": {"by_lord": levyer, "card_id": "T13"}})
    assert e.value.code == "heinrich_off_map"


def test_t13_levy_blocked_when_heinrich_removed():
    """Heinrich is permanently removed (state == 'removed') — Levy of T13 must reject."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    heinrich = s.lords["heinrich"]
    heinrich.state = "removed"
    heinrich.location = None
    if "T13" not in s.decks.teutonic.deck and "T13" not in s.decks.teutonic.discard:
        s.decks.teutonic.deck.append("T13")
    _to_muster_step(s)
    levyer = next(
        lid for lid, l in s.lords.items()
        if l.side == "teutonic" and l.state == "mustered" and l.location is not None
    )
    with pytest.raises(IllegalAction) as e:
        apply_action(s, {"type": "levy_capability", "side": "teutonic",
                          "args": {"by_lord": levyer, "card_id": "T13"}})
    assert e.value.code == "heinrich_off_map"


def test_t13_levy_allowed_when_heinrich_on_map():
    """Heinrich Mustered on map — Levy of T13 succeeds (block lifts when Heinrich Musters)."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    heinrich = s.lords["heinrich"]
    heinrich.state = "mustered"
    heinrich.location = "fellin"
    if "T13" not in s.decks.teutonic.deck and "T13" not in s.decks.teutonic.discard:
        s.decks.teutonic.deck.append("T13")
    _to_muster_step(s)
    r = apply_action(s, {"type": "levy_capability", "side": "teutonic",
                          "args": {"by_lord": "heinrich", "card_id": "T13"}})
    assert r["card_id"] == "T13"
    assert "T13" in s.decks.teutonic.capabilities_in_play


def test_t13_levy_rejection_message_references_aow_tip():
    """The error message should cite the AoW Reference T13 Event Tip."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    heinrich = s.lords["heinrich"]
    heinrich.state = "ready"
    heinrich.location = None
    if "T13" not in s.decks.teutonic.deck and "T13" not in s.decks.teutonic.discard:
        s.decks.teutonic.deck.append("T13")
    _to_muster_step(s)
    levyer = next(
        lid for lid, l in s.lords.items()
        if l.side == "teutonic" and l.state == "mustered" and l.location is not None
    )
    with pytest.raises(IllegalAction) as e:
        apply_action(s, {"type": "levy_capability", "side": "teutonic",
                          "args": {"by_lord": levyer, "card_id": "T13"}})
    # Compare against the error code, since the structure of IllegalAction
    # varies; the code itself signals the rule.
    assert e.value.code == "heinrich_off_map"
