"""Capability lookup helpers for Phase 4a combat/economy hooks.

Each capability is identified by a canonical name (matching cards.json
`capability_name`). A given AoW card may be tucked under a Lord's mat
(this_lord scope) or under the side board edge (side_wide scope). This
module provides:

  has_lord_capability(state, lord_id, name)     -> bool
  has_side_capability(state, side, name)        -> bool
  any_capability(state, lord_id, name)          -> bool
                                                   (this-lord OR side-wide)

Capability names used by Phase 4a:
  - "Halbbrueder"           T9 / T10
  - "Warrior Monks"         T7 / T15
  - "Luchniki"              R1 / R2
  - "Streltsy"              R3 / R13
  - "Balistarii"            T4 / T5 / T6
  - "Druzhina"              R5 / R6
  - "House of Suzdal"       R11
  - "Treaty of Stensby"     T1
  - "Ordensburgen"          T12
  - "Archbishopric of Novgorod"  R15
  - "Stone Kremlin"         R18
  - "Stonemasons"           T17
  - "Trebuchets"            T14
  - "Smerdi"                R4
  - "Crusade"               T11    (already wired in Phase 2)
  - "Steppe Warriors"       R10    (already wired in Phase 2)
  - "William of Modena"     T13    (already wired in Phase 2)
  - "Black Sea Trade"       R8     (already wired in Phase 2)
  - "Baltic Sea Trade"      R9     (already wired in Phase 2)
"""

from __future__ import annotations

from nevsky.state import GameState, Side
from nevsky.static_data import load_cards


def _name_of(card_id: str) -> str:
    return load_cards()[card_id]["capability_name"]


def _scope_of(card_id: str) -> str | None:
    return load_cards()[card_id].get("capability_scope")


def has_lord_capability(state: GameState, lord_id: str, name: str) -> bool:
    """True if the Lord has a this-lord-tucked capability with `name`.

    Round 30 hardening: a side-wide-scoped card erroneously placed in
    ``lord.this_lord_capabilities`` is ignored here -- such a card
    should only fire via ``has_side_capability``.
    """
    if lord_id not in state.lords:
        return False
    for cid in state.lords[lord_id].this_lord_capabilities:
        if _scope_of(cid) != "this_lord":
            continue
        if _name_of(cid) == name:
            return True
    return False


def has_side_capability(state: GameState, side: Side, name: str) -> bool:
    """True if the side has a side-wide capability with `name` in play.

    Round 30 hardening: only cards with ``capability_scope == "side_wide"``
    (per cards.json) fire via this path. A ``this_lord``-scoped card
    accidentally placed in ``deck.capabilities_in_play`` -- e.g., by a
    test fixture, an out-of-band state edit, or a future regression --
    will NOT fire side-wide. Without this guard, such a state would
    erroneously apply the capability to every Lord on that side.
    """
    deck = state.decks.teutonic if side == "teutonic" else state.decks.russian
    for cid in deck.capabilities_in_play:
        if _scope_of(cid) != "side_wide":
            continue
        if _name_of(cid) == name:
            return True
    return False


def any_capability(state: GameState, lord_id: str, name: str) -> bool:
    """True if the Lord has the capability via this-lord OR side-wide."""
    if has_lord_capability(state, lord_id, name):
        return True
    side: Side = state.lords[lord_id].side
    return has_side_capability(state, side, name)
