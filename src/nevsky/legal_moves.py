"""Enumerate legal moves for the active player.

Phase 2 covers the Levy phase. Each entry is a partial action dict
(missing only player-chosen targets where multiple are equally legal).
The intent is for an LLM agent to receive a structured list of currently
legal action *types* with the parameter slots they require, so it can
plan without trial-and-error.

We deliberately do not enumerate the full Cartesian product (e.g., we
do NOT list every (Lord, Seat) tuple for muster_lord). Instead, we
return one entry per action type with `targets` populated for the small
sets (Lords, free Seats per Lord, etc.).
"""

from __future__ import annotations

from typing import Any

from nevsky.actions import (
    _BISHOPRICS,
    _find_cylinder_box,
    _find_levy_marker_box,
    _free_seats_for,
    _is_besieged,
    _is_friendly_locale,
    _is_ready,
    _season_of_box,
)
from nevsky.state import GameState, Side
from nevsky.static_data import load_cards, load_lords


def legal_moves(state: GameState) -> list[dict[str, Any]]:
    """Return a list of currently-legal action stubs."""
    side = state.meta.active_player
    if side is None:
        return []

    moves: list[dict[str, Any]] = []
    if state.meta.phase == "levy":
        step = state.meta.levy_step
        if step == "arts_of_war":
            moves.extend(_aow_moves(state, side))
        elif step == "pay":
            moves.extend(_pay_moves(state, side))
        elif step == "disband":
            moves.extend(_disband_moves(state, side))
        elif step == "muster":
            moves.extend(_muster_moves(state, side))
        elif step == "call_to_arms":
            moves.extend(_call_to_arms_moves(state, side))
        moves.append({"type": "advance_step", "side": side, "args": {}})
    elif state.meta.phase == "campaign":
        moves.extend(_campaign_moves(state, side))
    return moves


def _aow_moves(state: GameState, side: Side) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    sd = state.decks.teutonic if side == "teutonic" else state.decks.russian
    if sd.pending_draw:
        # Must implement before drawing more.
        out.append({
            "type": "aow_implement_card",
            "side": side,
            "args": {"card_id": sd.pending_draw[0]},
            "note": "implements next pending_draw card per 3.1.2 / 3.1.3",
        })
    else:
        # Allow shuffle + draw in same Levy.
        if sd.deck or sd.discard:
            out.append({"type": "aow_shuffle", "side": side, "args": {}})
        if sd.deck:
            out.append({"type": "aow_draw", "side": side, "args": {}})
    return out


def _pay_moves(state: GameState, side: Side) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    own_lords = [
        lid for lid, lord in state.lords.items()
        if lord.side == side and lord.state == "mustered"
    ]
    coin_payers = [lid for lid in own_lords if state.lords[lid].assets.get("coin", 0) > 0]
    loot_payers = [
        lid for lid in own_lords
        if state.lords[lid].assets.get("loot", 0) > 0
        and state.lords[lid].location is not None
        and _is_friendly_locale(state, state.lords[lid].location, side)  # type: ignore[arg-type]
    ]
    if coin_payers:
        out.append({
            "type": "pay_with_coin",
            "side": side,
            "args_template": {
                "from": "lord:<id>",
                "target_lord": "<id>",
                "units": "<int>=1",
            },
            "candidates": {
                "payers": coin_payers,
                "targets": own_lords,
            },
        })
    if side == "russian" and state.veche.coin > 0:
        out.append({
            "type": "pay_with_coin",
            "side": side,
            "args_template": {"from": "veche", "target_lord": "<id>", "units": "<int>=1"},
            "candidates": {
                "payers": ["veche"],
                "targets": [
                    lid for lid in own_lords if not _is_besieged(state, lid)
                ],
            },
        })
    if loot_payers:
        out.append({
            "type": "pay_with_loot",
            "side": side,
            "args_template": {
                "from_lord": "<id>",
                "target_lord": "<id>",
                "units": "<int>=1",
            },
            "candidates": {
                "payers": loot_payers,
                "targets": own_lords,
            },
        })
    return out


def _disband_moves(state: GameState, side: Side) -> list[dict[str, Any]]:
    return [{
        "type": "disband_resolve",
        "side": side,
        "args": {},
        "note": "auto-resolves Lords whose Service marker is at-or-left-of Levy (3.3)",
    }]


def _muster_moves(state: GameState, side: Side) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    levy_box = _find_levy_marker_box(state)
    own_mustered = [
        lid for lid, lord in state.lords.items()
        if lord.side == side and lord.state == "mustered"
        and not lord.just_arrived_this_levy
        and not _is_besieged(state, lid)
        and lord.location is not None
        and _is_friendly_locale(state, lord.location, side)
    ]
    static = load_lords()
    cards = load_cards()
    by_with_budget = [
        lid for lid in own_mustered
        if state.lords[lid].lordship_used < int(static[lid]["ratings"]["lordship"])
    ]

    # Muster Lord: identify Ready own-side Lords with Free Seats (Aleksandr excluded).
    ready_targets: dict[str, list[str]] = {}
    for lid, sl in static.items():
        if sl["side"] != side or lid == "aleksandr":
            continue
        if state.lords[lid].state != "ready":
            continue
        cyl = _find_cylinder_box(state, lid)
        if cyl is None or cyl > levy_box:
            continue
        free = _free_seats_for(state, lid)
        if free:
            ready_targets[lid] = free
    if by_with_budget and ready_targets:
        out.append({
            "type": "muster_lord",
            "side": side,
            "args_template": {"by_lord": "<id>", "target_lord": "<id>", "seat": "<locale_id>"},
            "candidates": {"by_lords": by_with_budget, "targets": ready_targets},
        })

    # Muster Vassal.
    vassal_options: dict[str, list[str]] = {}
    for lid in by_with_budget:
        lord = state.lords[lid]
        opts = [vid for vid, vst in lord.vassals.items() if vst.ready and not vst.mustered]
        if opts:
            vassal_options[lid] = opts
    if vassal_options:
        out.append({
            "type": "muster_vassal",
            "side": side,
            "args_template": {"by_lord": "<id>", "vassal_id": "<id>"},
            "candidates": {"by_to_vassals": vassal_options},
        })

    # Levy Transport.
    transport_options: dict[str, list[str]] = {}
    for lid in by_with_budget:
        sl = static[lid]
        lord = state.lords[lid]
        opts: list[str] = []
        for t in ("boat", "cart", "sled", "ship"):
            if t == "ship" and not sl.get("ships_authorized", False):
                continue
            if lord.assets.get(t, 0) < 8:  # type: ignore[arg-type]
                opts.append(t)
        if opts:
            transport_options[lid] = opts
    if transport_options:
        out.append({
            "type": "levy_transport",
            "side": side,
            "args_template": {"by_lord": "<id>", "transport_type": "boat|cart|sled|ship"},
            "candidates": {"by_to_transports": transport_options},
        })

    # Levy Capability.
    sd = state.decks.teutonic if side == "teutonic" else state.decks.russian
    available_caps = [
        cid for cid in (sd.deck + sd.discard)
        if not cards[cid]["no_event"]
    ]
    if by_with_budget and available_caps:
        out.append({
            "type": "levy_capability",
            "side": side,
            "args_template": {"by_lord": "<id>", "card_id": "<card_id>", "lord_id": "<id?>"},
            "candidates": {"by_lords": by_with_budget, "cards": available_caps},
        })

    return out


def _call_to_arms_moves(state: GameState, side: Side) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if side == "teutonic":
        if state.legate.william_of_modena_in_play and not state.legate.acted_this_call_to_arms:
            if state.legate.location == "card":
                out.append({
                    "type": "legate_arrives",
                    "side": "teutonic",
                    "args_template": {"bishopric": "riga|dorpat|leal|reval"},
                    "candidates": {"bishoprics": sorted(_BISHOPRICS)},
                })
            else:
                # On map: Move (Option 1) or USE 2a/2b/2c
                friendly = [
                    lid for lid in state.locales
                    if _is_friendly_locale(state, lid, "teutonic")
                ]
                out.append({
                    "type": "legate_move",
                    "side": "teutonic",
                    "args_template": {"locale_id": "<id>"},
                    "candidates": {"locales": friendly},
                })
                out.append({
                    "type": "legate_use",
                    "side": "teutonic",
                    "args_template": {"sub_option": "2a|2b|2c", "target_lord": "<id>"},
                })
        out.append({"type": "legate_skip", "side": "teutonic", "args": {}})
        out.append({"type": "aow_discard_this_levy", "side": "teutonic", "args": {}})
    else:  # russian
        levy_box = _find_levy_marker_box(state)
        # Sea-trade
        for cid in ("R8", "R9"):
            if cid in state.decks.russian.capabilities_in_play and state.veche.coin < 8:
                if cid == "R9":
                    season = _season_of_box(state.meta.box)
                    if season in ("early_winter", "late_winter"):
                        continue
                out.append({
                    "type": "veche_action",
                    "side": "russian",
                    "args": {"option": "sea_trade", "card_id": cid},
                })
        if not state.veche.acted_this_call_to_arms:
            if state.veche.vp_markers > 0:
                ru_lords_on_calendar = [
                    lid for lid, lord in state.lords.items()
                    if lord.side == "russian" and _find_cylinder_box(state, lid) is not None
                ]
                out.append({
                    "type": "veche_action",
                    "side": "russian",
                    "args_template": {"option": "A", "target_lord": "<id>"},
                    "candidates": {"targets": ru_lords_on_calendar},
                })
                ready_ru = [
                    lid for lid, lord in state.lords.items()
                    if lord.side == "russian" and lord.state == "ready"
                    and _is_ready(state, lid, levy_box)
                    and _free_seats_for(state, lid)
                ]
                if ready_ru:
                    out.append({
                        "type": "veche_action",
                        "side": "russian",
                        "args_template": {"option": "B", "target_lord": "<id>", "seat": "<locale_id>"},
                        "candidates": {"targets": ready_ru},
                    })
                extra_targets = [
                    lid for lid, lord in state.lords.items()
                    if lord.side == "russian" and lord.state == "mustered"
                    and lord.location is not None
                    and _is_friendly_locale(state, lord.location, "russian")
                    and not _is_besieged(state, lid)
                    and not lord.just_arrived_this_levy
                ]
                if extra_targets:
                    out.append({
                        "type": "veche_action",
                        "side": "russian",
                        "args_template": {"option": "C", "target_lord": "<id>"},
                        "candidates": {"targets": extra_targets},
                    })
            decline_avail = (
                _is_ready(state, "aleksandr", levy_box)
                or _is_ready(state, "andrey", levy_box)
            )
            if decline_avail:
                out.append({
                    "type": "veche_action",
                    "side": "russian",
                    "args": {"option": "D"},
                })
            out.append({"type": "veche_action", "side": "russian", "args": {"option": "skip"}})
        out.append({"type": "aow_discard_this_levy", "side": "russian", "args": {}})
    return out


def _campaign_moves(state: GameState, side: Side) -> list[dict[str, Any]]:
    from nevsky.campaign import _plan_target_size

    out: list[dict[str, Any]] = []
    # Combat-pending response takes priority.
    if state.combat_pending is not None:
        cp = state.combat_pending
        if cp.pending_response_by == side:
            out.append({"type": "stand_battle", "side": side, "args": {}, "note": "engage in Battle"})
            if not cp.laden:
                out.append({"type": "avoid_battle", "side": side,
                            "args_template": {"to": "<adjacent locale_id>"},
                            "note": "Avoid Battle (Unladen, 4.3.4)"})
            out.append({"type": "withdraw", "side": side, "args": {},
                        "note": "Withdraw into Stronghold at Battle Locale"})
            return out
        return out
    cstep = state.meta.campaign_step
    if cstep == "plan":
        deck = state.decks.teutonic if side == "teutonic" else state.decks.russian
        target = _plan_target_size(state.meta.box)
        already = (state.meta.plan_complete_t if side == "teutonic" else state.meta.plan_complete_r)
        if not already:
            if len(deck.plan) < target:
                mustered = [lid for lid, l in state.lords.items()
                            if l.side == side and l.state == "mustered"]
                out.append({
                    "type": "plan_add_card",
                    "side": side,
                    "args_template": {"card": "<lord_id>|pass"},
                    "candidates": {"lords": mustered, "filler": "pass"},
                    "note": f"Plan {len(deck.plan)}/{target}",
                })
            else:
                out.append({"type": "finalize_plan", "side": side, "args": {}})
        return out
    if cstep == "command":
        if state.campaign_turn.in_feed_pay_disband:
            out.append({"type": "fpd_resolve", "side": side, "args": {}})
            return out
        if state.campaign_turn.actions_remaining == 0:
            # waiting to reveal
            if state.campaign_turn.next_to_reveal == side:
                out.append({"type": "command_reveal", "side": side, "args": {}})
            return out
        # active Lord performing actions
        active_lord = state.campaign_turn.active_lord
        if active_lord is None or state.lords[active_lord].side != side:
            return out
        out.append({"type": "cmd_march", "side": side,
                    "args_template": {"lord_id": "<id>", "to": "<locale_id>", "group": "[<id>]"},
                    "note": "March 1 Locale (1 Unladen / 2 Laden)"})
        out.append({"type": "cmd_pass", "side": side,
                    "args": {"lord_id": active_lord},
                    "note": "forfeit remaining actions"})
        out.append({"type": "cmd_tax", "side": side,
                    "args": {"lord_id": active_lord},
                    "note": "+1 Coin at own Seat (entire card)"})
        out.append({"type": "cmd_forage", "side": side,
                    "args": {"lord_id": active_lord},
                    "note": "+1 Provender (1 action)"})
        out.append({"type": "cmd_ravage", "side": side,
                    "args": {"lord_id": active_lord},
                    "note": "Ravage current Locale (1-2 actions)"})
        out.append({"type": "cmd_supply", "side": side,
                    "args_template": {"lord_id": "<id>", "sources": "[{locale_id, route, transport}]"},
                    "note": "Supply (1 action)"})
        out.append({"type": "cmd_sail", "side": side,
                    "args_template": {"lord_id": "<id>", "destination": "<seaport_id>", "group": "[<id>]"},
                    "note": "Sail Seaport->Seaport (entire card)"})
        out.append({"type": "end_card", "side": side, "args": {},
                    "note": "voluntarily end this Command card"})
        return out
    if cstep == "end_campaign":
        out.append({"type": "end_campaign_resolve", "side": side, "args": {}})
        return out
    return out
