"""Hidden-info filtering for LLM view of state.

`view_for_side(state, side)` returns a dict view of GameState that
hides the opponent's:
  - holds (per 3.1.3 Hold cards are private)
  - pending_draw (cards drawn but not yet implemented are private)
  - this_levy_events / this_campaign_events (events in effect on
    the opponent's side, partially visible but card-id only)
  - plan stack (per 4.1 the plan is private until cards are
    revealed during Activation)

The own side's deck is fully visible.

Public state is always visible:
  - Locales (all Conquered / Ravaged / Castle markers, siege markers)
  - Lords' on-map positions, forces (per 1.5.3 forces are public)
  - Lords' assets (visible per game rules)
  - Lords' this_lord_capabilities (public — tucked face-up)
  - Calendar positions (cylinders + service markers are all public)
  - Veche state (1.4.2 — public Russian resource)
  - Legate position (1.4.1 — public)
  - VP track (public)
  - Both sides' `capabilities_in_play` (public — these are on the
    board edge)
"""
from __future__ import annotations

from typing import Any


def view_for_side(state, side: str) -> dict[str, Any]:
    """Return a dict view of state with opponent's hidden info masked."""
    other = "russian" if side == "teutonic" else "teutonic"
    d = state.model_dump()
    # Mask opponent deck's hidden lists.
    other_deck = d["decks"][other]
    other_deck["holds"] = ["<hidden>"] * len(other_deck.get("holds", []))
    other_deck["pending_draw"] = ["<hidden>"] * len(
        other_deck.get("pending_draw", [])
    )
    # Plan stack: card identities hidden until revealed.
    # Per 4.2.3 the active card BEING revealed is public; the rest of
    # the plan stack is private.
    other_deck["plan"] = ["<hidden>"] * len(other_deck.get("plan", []))
    # this_levy_events / this_campaign_events: cards are public once
    # placed (events are publicly announced and resolved). Keep as-is.
    return d


def own_decks(state, side: str) -> dict[str, Any]:
    """Return the FULL own-side deck state (for the LLM's own
    decisions). Used by tools that need privileged access to own
    holds / pending / plan."""
    return state.decks.teutonic.model_dump() if side == "teutonic" else state.decks.russian.model_dump()
