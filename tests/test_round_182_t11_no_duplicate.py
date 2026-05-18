"""SMOKE-117 (Round 182): T11 Pope Gregory Event-resolution added T11
to capabilities_in_play, but the aow_implement_card immediate-event
flow also appended the card to discard — the SAME card ended up in
both lists, violating deck-uniqueness.

Found via Hypothesis property-based testing on crusade_on_novgorod
seed=52: after ~400 steps, T11 appeared twice across deck.
capabilities_in_play and deck.discard.

Per AoW Reference T11 card text: "On Calendar, shift 1 Teuton
cylinder 1 box left; add Crusade (this card) to Levied
Capabilities". The card BECOMES the Crusade Capability — it doesn't
also discard.

Reachable when T11 had previously been added to capabilities_in_play
(via 4.9.5 Crusade auto-discard then shuffled back into deck) and
was drawn again as Event.

Fix:
  - _ev_pope_gregory returns `places_in_capabilities=True`.
  - aow_implement_card checks the flag and SKIPS the discard
    append, returning outcome="immediate_event_to_capability".

Same audit pattern as SMOKE-103 (card lifecycle leak).
"""
from __future__ import annotations

import inspect

import nevsky.actions  # noqa: F401
import nevsky.events as events
from nevsky.events import resolve_immediate_event
from nevsky.scenarios import load_scenario


def test_smoke_117_marker_in_pope_gregory():
    src = inspect.getsource(events._ev_pope_gregory)
    assert "SMOKE-117" in src
    assert "places_in_capabilities" in src


def test_smoke_117_t11_first_event_resolution_adds_to_capabilities():
    """First T11 event: T11 not in capabilities_in_play; resolver
    adds it AND returns places_in_capabilities=True."""
    s = load_scenario("watland", seed=1)
    if "T11" in s.decks.teutonic.capabilities_in_play:
        s.decks.teutonic.capabilities_in_play.remove("T11")
    teu = next(lid for lid, l in s.lords.items()
               if l.side == "teutonic" and l.state in ("ready", "mustered"))
    # Place teu's cylinder somewhere shiftable
    for cb in s.calendar.boxes:
        if teu in cb.cylinders:
            cb.cylinders.remove(teu)
    s.calendar.boxes[5].cylinders.append(teu)
    res = resolve_immediate_event(s, "T11", {"target": teu})
    assert res.get("places_in_capabilities") is True
    assert res.get("crusade_added") is True
    assert "T11" in s.decks.teutonic.capabilities_in_play


def test_smoke_117_t11_second_event_resolution_no_op_on_capability_add():
    """If T11 is already in capabilities_in_play and the Event is
    drawn again, places_in_capabilities=True (still skip discard)
    but crusade_added=False (no double-add)."""
    s = load_scenario("watland", seed=1)
    if "T11" not in s.decks.teutonic.capabilities_in_play:
        s.decks.teutonic.capabilities_in_play.append("T11")
    teu = next(lid for lid, l in s.lords.items()
               if l.side == "teutonic" and l.state in ("ready", "mustered"))
    for cb in s.calendar.boxes:
        if teu in cb.cylinders:
            cb.cylinders.remove(teu)
    s.calendar.boxes[5].cylinders.append(teu)
    res = resolve_immediate_event(s, "T11", {"target": teu})
    # Still flags places_in_capabilities so aow_implement_card skips
    # discard append; but crusade_added=False signals the no-op.
    assert res.get("places_in_capabilities") is True
    assert res.get("crusade_added") is False
    # Capabilities list still contains exactly one T11
    assert s.decks.teutonic.capabilities_in_play.count("T11") == 1


def test_smoke_117_aow_implement_skips_discard_on_t11():
    """Integration: aow_implement_card on T11 doesn't add to discard."""
    import nevsky.actions as actions
    src = inspect.getsource(actions._h_aow_implement_card)
    # Verify the SMOKE-117 conditional skip is present
    assert "SMOKE-117" in src
    assert "places_in_capabilities" in src
    assert "immediate_event_to_capability" in src


def test_smoke_117_no_duplicate_after_immediate_event():
    """Behavioral: after aow_implement_card on T11, the card appears
    in capabilities_in_play but NOT in discard."""
    from nevsky.actions import apply_action
    s = load_scenario("watland", seed=1)
    # Setup so T11 is in pending_draw, side is teutonic, post first-Levy
    s.meta.phase = "levy"
    s.meta.levy_step = "arts_of_war"
    s.meta.active_player = "teutonic"
    s.meta.first_levy_done = True  # so events resolve, not capabilities
    if "T11" in s.decks.teutonic.capabilities_in_play:
        s.decks.teutonic.capabilities_in_play.remove("T11")
    if "T11" in s.decks.teutonic.deck:
        s.decks.teutonic.deck.remove("T11")
    if "T11" in s.decks.teutonic.discard:
        s.decks.teutonic.discard.remove("T11")
    s.decks.teutonic.pending_draw = ["T11"]
    teu = next(lid for lid, l in s.lords.items()
               if l.side == "teutonic" and l.state in ("ready", "mustered"))
    for cb in s.calendar.boxes:
        if teu in cb.cylinders:
            cb.cylinders.remove(teu)
    s.calendar.boxes[5].cylinders.append(teu)
    res = apply_action(s, {"type": "aow_implement_card", "side": "teutonic",
                            "args": {"card_id": "T11", "target": teu}})
    # T11 is in capabilities_in_play
    assert s.decks.teutonic.capabilities_in_play.count("T11") == 1
    # T11 is NOT in discard
    assert s.decks.teutonic.discard.count("T11") == 0
    assert res.get("outcome") == "immediate_event_to_capability"
