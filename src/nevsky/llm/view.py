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

Optional Hidden Mats conceals opposing Mustered Lord mats, including Vassal
status. It also screens This-Lord Capability identities and Vassal and
Transport details in opposing Levy history, including setup Transport choices.
Feed history keeps food costs and consequences visible and screens exact
opposing force totals.
Public Calendar markers remain visible with Advanced Vassal Service.
"""
from __future__ import annotations

from typing import Any

from nevsky.state import STORM_FRONT_ACTION


def _mask_cards(cards: list) -> list[str]:
    return ["<hidden>"] * len(cards)


def _filter_history(entry: dict[str, Any], side: str, *, hidden_mats: bool,
                    owned_lords: set[str]) -> None:
    """Redact private details in an already detached history copy."""
    action = entry["action"]
    result = entry["result"]
    kind = action.get("type")
    if hidden_mats and kind == "fpd_resolve":
        for row in result.get("feed", []):
            if row.get("lord_id") not in owned_lords:
                row.pop("units", None)
    if entry["actor"] == side or entry["actor"] == "system":
        return
    if hidden_mats:
        result.pop("_auto_confirmed_setup_transports", None)
    if kind in ("cmd_march", "stand_battle", "cmd_sally"):
        action.get("args", {}).pop("strike_order", None)
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
    elif kind == "aow_implement_card":
        outcome = result.get("outcome")
        if outcome == "held" or (hidden_mats and outcome == "tucked_under_lord"):
            action["args"] = {"card_id": "<hidden>"}
            entry["result"] = {"card": "<hidden>", "outcome": outcome}
    elif hidden_mats and kind == "levy_capability" and result.get("scope") == "this_lord":
        # Keep the public Lordship expenditure, without revealing the incoming
        # or swapped Capability, its source, or other screened mat details.
        by_lord = result.get("by_lord")
        action["args"] = {"by_lord": by_lord, "card_id": "<hidden>"}
        entry["result"] = {"by_lord": by_lord, "card_id": "<hidden>", "scope": "this_lord"}
    elif hidden_mats and kind in {"muster_vassal", "levy_transport"}:
        # Lordship expenditure is public. Any public Vassal Service marker
        # is visible separately on the Calendar.
        private_key = "vassal_id" if kind == "muster_vassal" else "transport_type"
        by_lord = result.get("by_lord") or action.get("args", {}).get("by_lord")
        action["args"] = {"by_lord": by_lord, private_key: "<hidden>"}
        entry["result"] = action["args"].copy()
    elif kind == "cmd_storm" and result.get("awaiting_storm_front"):
        # The attacker has declared the Storm. The committed Hold and other
        # tactical inputs are still private at the defender's Array choice.
        args = action["args"]
        action["args"] = {k: args[k] for k in ("lord_id",) if k in args}


def view_for_side(state, side: str) -> dict[str, Any]:
    """Return a dict view of state with opponent's hidden info masked."""
    if side not in ("teutonic", "russian"):
        raise ValueError("side must be 'teutonic' or 'russian'")
    hidden_mats = bool(state.meta.optional_rules.get("hidden_mats"))
    if hidden_mats:
        from nevsky.render import state_view_for_side
        state = state_view_for_side(state, side)
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
    if hidden_mats:
        # A confirmation would disclose that the opponent accepted the default.
        d["history"] = [
            entry for entry in d["history"]
            if entry["actor"] in (side, "system") or entry["action"].get("type") not in (
                "set_setup_transport", "confirm_setup_transport", "confirm_all_setup_transports",
            )
        ]
    owned_lords = {lid for lid, lord in d["lords"].items() if lord["side"] == side}
    for entry in d["history"]:
        _filter_history(entry, side, hidden_mats=hidden_mats, owned_lords=owned_lords)
    combat = d["combat_pending"]
    if combat is not None and combat["attacker_side"] != side:
        combat.pop("attacker_strike_order", None)
    for pending in d["pending_decisions"]:
        if pending["kind"] == STORM_FRONT_ACTION:
            pending["context"].pop("attack_args", None)
    return d


def own_decks(state, side: str) -> dict[str, Any]:
    """Own held/drawn cards and plan, without revealing future draw order."""
    if side not in ("teutonic", "russian"):
        raise ValueError("side must be 'teutonic' or 'russian'")
    deck = getattr(state.decks, side).model_dump()
    deck["deck"] = _mask_cards(deck["deck"])
    return deck
