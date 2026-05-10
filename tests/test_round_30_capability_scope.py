"""Round 30: capability scope enforcement (defensive hardening).

`has_side_capability` and `has_lord_capability` previously did not
validate `capability_scope` from cards.json. A `this_lord`-scoped card
accidentally placed in `deck.capabilities_in_play` (e.g., by a test
fixture or a future state-mutation bug) would erroneously fire
side-wide.

These tests pin the new behavior:

  - this_lord cap in capabilities_in_play  -> does NOT fire side-wide
  - side_wide cap in lord.this_lord_capabilities  -> does NOT fire as a
    this-lord capability
  - Normal placements still fire correctly.
"""
from __future__ import annotations

from nevsky.capabilities import (
    has_lord_capability,
    has_side_capability,
    any_capability,
)
from nevsky.scenarios import load_scenario


def _setup():
    s = load_scenario("watland", seed=1)
    teu = next(
        lid for lid, l in s.lords.items()
        if l.side == "teutonic" and l.state == "mustered"
    )
    return s, teu


def test_this_lord_cap_misplaced_in_capabilities_in_play_does_not_fire_side_wide():
    """T9 (Halbbrueder, this_lord) shoved into capabilities_in_play
    must NOT be reported as a side-wide capability."""
    s, teu = _setup()
    s.decks.teutonic.capabilities_in_play.append("T9")  # T9 = this_lord
    # Side-wide query must reject the misplaced card.
    assert not has_side_capability(s, "teutonic", "Halbbrueder")
    # any_capability falls back to side-wide check; should also be False
    # because the Lord doesn't have it tucked either.
    assert not any_capability(s, teu, "Halbbrueder")


def test_this_lord_cap_correctly_tucked_fires_for_owner_lord_only():
    s, teu = _setup()
    # Other own-side mustered Lord (if any).
    other = next(
        (lid for lid, l in s.lords.items()
         if l.side == "teutonic" and l.state == "mustered" and lid != teu),
        None,
    )
    s.lords[teu].this_lord_capabilities.append("T9")
    assert has_lord_capability(s, teu, "Halbbrueder")
    assert any_capability(s, teu, "Halbbrueder")
    # Side-wide query is False (T9 is this_lord; no T9 in
    # capabilities_in_play).
    assert not has_side_capability(s, "teutonic", "Halbbrueder")
    if other is not None:
        # The other own-side Lord doesn't share a this_lord cap.
        assert not has_lord_capability(s, other, "Halbbrueder")
        assert not any_capability(s, other, "Halbbrueder")


def test_side_wide_cap_misplaced_in_this_lord_capabilities_does_not_fire_as_this_lord():
    """T11 (Crusade, side_wide) shoved into a Lord's this_lord pile
    must NOT be reported as a per-Lord capability."""
    s, teu = _setup()
    s.lords[teu].this_lord_capabilities.append("T11")  # T11 = side_wide
    assert not has_lord_capability(s, teu, "Crusade")
    # Falls back to side_wide; T11 isn't in capabilities_in_play either.
    assert not any_capability(s, teu, "Crusade")


def test_side_wide_cap_correctly_in_capabilities_in_play_fires():
    s, teu = _setup()
    s.decks.teutonic.capabilities_in_play.append("T11")
    assert has_side_capability(s, "teutonic", "Crusade")
    assert any_capability(s, teu, "Crusade")
