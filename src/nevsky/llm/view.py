"""Hidden-info filtering for LLM view of state.

`view_for_side(state, side)` returns a dict view of GameState that
hides the opponent's:
  - holds (per 3.1.3 Hold cards are private)
  - pending_draw (cards drawn but not yet implemented are private)
  - plan stack (per 4.1 the plan is private until cards are
    revealed during Activation)

Both draw piles and RNG inputs are hidden. Own held cards and command
plans remain visible. History follows the same visibility rules as the
current card zones; it must not disclose a private draw or plan.

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


def _mask_cards(cards: list) -> list[str]:
    return ["<hidden>"] * len(cards)


def _filter_history(entry: dict[str, Any], side: str) -> None:
    """Redact private opponent actions in an already detached history copy."""
    if entry["actor"] == side or entry["actor"] == "system":
        return
    action = entry["action"]
    result = entry["result"]
    kind = action.get("type")
    if kind == "aow_draw":
        action["args"] = {}
        entry["result"] = {
            "drawn": _mask_cards(result.get("drawn", [])),
            "deck_remaining": result.get("deck_remaining"),
        }
    elif kind == "plan_add_card":
        action["args"] = {"card": "<hidden>"}
        entry["result"] = {
            "appended": "<hidden>", "plan_size": result.get("plan_size"),
        }
    elif kind == "aow_implement_card" and result.get("outcome") == "held":
        action["args"] = {"card_id": "<hidden>"}
        entry["result"] = {"card": "<hidden>", "outcome": "held"}


def view_for_side(state, side: str) -> dict[str, Any]:
    """Return a dict view of state with opponent's hidden info masked."""
    if side not in ("teutonic", "russian"):
        raise ValueError("side must be 'teutonic' or 'russian'")
    other = "russian" if side == "teutonic" else "teutonic"
    d = state.model_dump()
    # The portable save retains the RNG state; a player's view must not
    # provide the inputs needed to predict future dice or shuffled cards.
    d["meta"].pop("seed", None)
    d["meta"].pop("rng_state", None)
    for deck in d["decks"].values():
        deck["deck"] = _mask_cards(deck["deck"])
    # Mask opponent deck's hidden lists.
    other_deck = d["decks"][other]
    other_deck["holds"] = _mask_cards(other_deck["holds"])
    other_deck["pending_draw"] = _mask_cards(other_deck["pending_draw"])
    # Plan stack: card identities hidden until revealed.
    # Per 4.2.3 the active card BEING revealed is public; the rest of
    # the plan stack is private.
    other_deck["plan"] = _mask_cards(other_deck["plan"])
    # this_levy_events / this_campaign_events: cards are public once
    # placed (events are publicly announced and resolved). Keep as-is.
    for entry in d["history"]:
        _filter_history(entry, side)
    return d


def own_decks(state, side: str) -> dict[str, Any]:
    """Own held/drawn cards and plan, without revealing future draw order."""
    if side not in ("teutonic", "russian"):
        raise ValueError("side must be 'teutonic' or 'russian'")
    deck = getattr(state.decks, side).model_dump()
    deck["deck"] = _mask_cards(deck["deck"])
    return deck
