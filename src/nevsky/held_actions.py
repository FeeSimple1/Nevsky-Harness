"""Optional non-combat Holds, enumerated without advancing the live game.

Battle Holds stay in their existing Battle/Storm response channels. These
are the independent, deterministic Hold actions that the old menu omitted.
"""
from __future__ import annotations

from copy import deepcopy
from itertools import combinations
from typing import Any

from nevsky.actions import (
    IllegalAction,
    _find_cylinder_box,
    _is_besieged,
    _is_extra_muster_actor,
    _is_friendly_locale,
    _may_continue_muster,
    apply_action,
)
from nevsky.state import GameState, Side


def _accepts(state: GameState, action: dict[str, Any]) -> bool:
    # History is append-only and irrelevant to these deterministic effects.
    # Give the probe its own empty history, avoiding an ever-growing copy
    # cost late in the campaign. No result or random outcome informs a choice.
    probe = deepcopy(state, {id(state.history): []})
    try:
        apply_action(probe, action)
    except IllegalAction:
        return False
    # Do not suppress unexpected errors: they are defects, not illegal moves.
    return True


def held_actions_for_side(
    state: GameState, side: Side, *, interrupts_only: bool = False,
) -> list[dict[str, Any]]:
    """Return optional Holds belonging ONLY to the requested side.

    Any-time Holds can interrupt the other side without changing
    meta.active_player. Lordship/shift Holds retain the existing handler's
    Muster/Call-to-Arms timing and are offered on their owner's segment.
    Custom T13 Asset distributions remain available via explicit JSON.
    """
    if side not in ("teutonic", "russian") or state.meta.game_over:
        return []
    deck = getattr(state.decks, side)
    out: list[dict[str, Any]] = []

    def offer(kind: str, args: dict[str, Any], note: str,
              candidates: dict[str, Any] | None = None) -> None:
        action: dict[str, Any] = {"type": kind, "side": side, "args": args}
        if _accepts(state, action):
            action.update(optional=True, note=note)
            if candidates is not None:
                action["candidates"] = candidates
            out.append(action)

    if "R3" in deck.holds:
        for lid, lord in state.lords.items():
            if lord.side == side and lord.state == "mustered" and lord.location is not None:
                offer("aow_play_hold", {"card_id": "R3", "target": lid},
                      "Pogost: add up to 4 Provender in Rus; optional, including during Feed")
    if "T3" in deck.holds:
        for target in ("kaibolovo", "koporye"):
            offer("aow_play_hold", {"card_id": "T3", "target": target},
                  f"Vodian Treachery: Conquer {target} without Spoils (optional)")
    if "T13" in deck.holds:
        recipients = [
            lid for lid, lord in state.lords.items()
            if lid != "heinrich" and lord.side == side
            and lord.state == "mustered" and lord.location is not None
        ]
        for pair in combinations(recipients, 2):
            offer("aow_play_hold", {"card_id": "T13", "recipients": list(pair)},
                  "Heinrich Sees the Curia: Disband Heinrich; default 4 Coin each. "
                  "Alternatively set args.assets={lord_id:{asset_type:count}}; "
                  "exactly 4 non-Loot Assets per recipient.",
                  {"assets": {lid: {"total": 4, "allowed_types": [
                      "coin", "provender", "boat", "cart", "sled", "ship",
                  ]} for lid in pair}})

    if (interrupts_only or state.meta.active_player != side
            or state.meta.phase != "levy"
            or state.meta.levy_step not in ("muster", "call_to_arms")):
        return out

    from nevsky.events import _LORDSHIP_PLUS_2_TARGETS

    blocked = (state.meta.block_lords_this_levy_t if side == "teutonic"
               else state.meta.block_lords_this_levy_r)
    for cid in deck.holds:
        spec = _LORDSHIP_PLUS_2_TARGETS.get(cid)
        if spec is None or spec["side"] != side:
            continue
        for lid, lord in state.lords.items():
            if lord.side != side:
                continue
            allowed = spec["lords"]
            if allowed != "any_russian" and lid not in allowed:
                continue
            args = {"card_id": cid, "lord_id": lid}
            # Exhausting the printed rating must NOT hide the bonus itself.
            # During CtA the extra Muster must first be granted to this Lord.
            extra = _is_extra_muster_actor(state, lid)
            if (lord.state == "mustered" and lord.location is not None
                    and _may_continue_muster(state, lid)
                    and lid not in blocked and not _is_besieged(state, lid)
                    and _is_friendly_locale(state, lord.location, side)
                    and (not lord.just_arrived_this_levy or extra)
                    and (state.meta.levy_step == "muster" or extra)):
                offer("aow_lordship_plus_2", {**args, "mode": "lordship"},
                      f"{cid}: +2 Lordship for {lid} (optional)")
            if _find_cylinder_box(state, lid) is not None:
                # The rules permit selecting an off-edge direction even if
                # the shift is ignored. The Hold is still consumed, not looped.
                for direction in ("left", "right"):
                    offer("aow_lordship_plus_2",
                          {**args, "mode": "shift", "direction": direction},
                          f"{cid}: shift {lid} {direction} (optional)")
    return out
