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


def legal_moves(state: GameState, *, with_previews: bool = True) -> list[dict[str, Any]]:
    """Return a list of currently-legal action stubs.

    `with_previews=True` (default): cmd_storm / cmd_sally / stand_battle
    notes are augmented with vp_forecast outputs (winrate, expected
    losses). Each augmentation runs ~15 simulations per option, ~50ms
    each. Set False in hot loops where preview cost dominates."""
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
        moves.extend(_campaign_moves(state, side, with_previews=with_previews))
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
        for by_lid in by_with_budget:
            for tgt_lid, seats in ready_targets.items():
                for seat in seats:
                    out.append({
                        "type": "muster_lord", "side": side,
                        "args": {"by_lord": by_lid, "target_lord": tgt_lid, "seat": seat},
                        "note": f"{by_lid} (Lordship) Musters {tgt_lid} at {seat} (1d6<=Fealty success)",
                    })

    # Muster Vassal.
    vassal_options: dict[str, list[str]] = {}
    for lid in by_with_budget:
        lord = state.lords[lid]
        opts = [vid for vid, vst in lord.vassals.items() if vst.ready and not vst.mustered]
        if opts:
            vassal_options[lid] = opts
    for by_lid, vlist in vassal_options.items():
        for vid in vlist:
            out.append({
                "type": "muster_vassal", "side": side,
                "args": {"by_lord": by_lid, "vassal_id": vid},
                "note": f"{by_lid} Musters Vassal {vid}",
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
    for by_lid, tlist in transport_options.items():
        for tt in tlist:
            out.append({
                "type": "levy_transport", "side": side,
                "args": {"by_lord": by_lid, "transport_type": tt},
                "note": f"{by_lid} Levies +1 {tt}",
            })

    # Levy Capability.
    # SMOKE-118 (Round 186): pre-filter by capability_eligibility,
    # per-Lord capability-2 limit, and duplicate-capability-name.
    # Pre-fix legal_moves offered (by_lord, card_id) pairs the
    # harness would reject for ineligible_target / ineligible_levyer /
    # cap_limit / duplicate_capability. Agents and the LLM-play
    # interface (which uses legal_moves as the LLM's move palette)
    # could waste turns retrying impossible moves.
    from nevsky.actions import _check_capability_eligibility
    sd = state.decks.teutonic if side == "teutonic" else state.decks.russian
    available_caps = [
        cid for cid in (sd.deck + sd.discard)
        if not cards[cid]["no_event"]
    ]
    for by_lid in by_with_budget:
        by_lord = state.lords[by_lid]
        for cid in available_caps:
            card = cards[cid]
            cap_name = card.get("capability_name") or "?"
            scope = card.get("capability_scope") or "?"
            # Per-Lord cap-2 (3.4.4) only applies to this_lord scope.
            target_lord_id = by_lid if scope == "this_lord" else None
            if scope == "this_lord":
                if len(by_lord.this_lord_capabilities) >= 2:
                    continue  # cap_limit would fire
                if any(cards[ex].get("capability_name") == cap_name
                       for ex in by_lord.this_lord_capabilities):
                    continue  # duplicate_capability would fire
            # capability_eligibility on by_lord (levyer) and target.
            try:
                _check_capability_eligibility(card, by_lid, role="levyer")
                if target_lord_id is not None:
                    _check_capability_eligibility(card, target_lord_id, role="target")
            except Exception:
                continue
            # this-Levy block list check.
            block = (state.meta.block_lords_this_levy_t if side == "teutonic"
                     else state.meta.block_lords_this_levy_r)
            if by_lid in block:
                continue
            out.append({
                "type": "levy_capability", "side": side,
                "args": {"by_lord": by_lid, "card_id": cid},
                "note": f"{by_lid} Levies {cid} ({cap_name}) [{scope}]",
            })

    return out


def _call_to_arms_moves(state: GameState, side: Side) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if side == "teutonic":
        if state.legate.william_of_modena_in_play and not state.legate.acted_this_call_to_arms:
            if state.legate.location == "card":
                for bp in sorted(_BISHOPRICS):
                    out.append({
                        "type": "legate_arrives", "side": "teutonic",
                        "args": {"bishopric": bp},
                        "note": f"Place Legate at Bishopric {bp} (3.5.1 Option 1)",
                    })
            else:
                # On map: Move (Option 1) or USE 2a/2b/2c
                friendly = [
                    lid for lid in state.locales
                    if _is_friendly_locale(state, lid, "teutonic")
                ]
                for fl in friendly:
                    out.append({
                        "type": "legate_move", "side": "teutonic",
                        "args": {"locale_id": fl},
                        "note": f"Move Legate to {fl} (3.5.1 Option 1)",
                    })
                # 2a: auto-Muster a Ready Lord at his Seat (no Fealty), pawn at that Seat.
                # 2b: shift a Lord's Calendar marker 1 box LEFT, pawn at that Lord's Seat.
                # 2c: extra Muster at full Lordship for a Mustered Lord co-located with the Legate.
                pawn_loc = state.legate.locale_id
                # 2a candidates: Ready Teu Lords whose Seats include the pawn's Locale.
                from nevsky.actions import _seats_of as _seats
                cand_2a = [
                    lid for lid, l in state.lords.items()
                    if l.side == "teutonic" and l.state == "ready"
                    and pawn_loc in _seats(state, lid)
                ]
                for tgt in cand_2a:
                    out.append({
                        "type": "legate_use", "side": "teutonic",
                        "args": {"sub_option": "2a", "target_lord": tgt},
                        "note": f"Legate 2a: auto-Muster Ready {tgt} at his Seat {pawn_loc} (3.5.1)",
                    })
                # 2b candidates: Teu Lords whose Seat the pawn is at, on Calendar.
                cand_2b = [
                    lid for lid, l in state.lords.items()
                    if l.side == "teutonic" and pawn_loc in _seats(state, lid)
                    and _find_cylinder_box(state, lid) is not None
                ]
                for tgt in cand_2b:
                    out.append({
                        "type": "legate_use", "side": "teutonic",
                        "args": {"sub_option": "2b", "target_lord": tgt},
                        "note": f"Legate 2b: shift {tgt} 1 box LEFT on Calendar (3.5.1)",
                    })
                # 2c candidates: Mustered Teu Lords co-located with the pawn at a Friendly Locale.
                cand_2c = [
                    lid for lid, l in state.lords.items()
                    if l.side == "teutonic" and l.state == "mustered"
                    and l.location == pawn_loc
                    and _is_friendly_locale(state, l.location, "teutonic")
                ]
                for tgt in cand_2c:
                    out.append({
                        "type": "legate_use", "side": "teutonic",
                        "args": {"sub_option": "2c", "target_lord": tgt},
                        "note": f"Legate 2c: give {tgt} extra Muster at full Lordship (3.5.1)",
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
                # Option A: shift Aleksandr/Andrey cylinder LEFT 2 boxes (1 VP marker each).
                ru_lords_on_calendar = [
                    lid for lid, lord in state.lords.items()
                    if lord.side == "russian" and _find_cylinder_box(state, lid) is not None
                ]
                for tgt in ru_lords_on_calendar:
                    out.append({
                        "type": "veche_action", "side": "russian",
                        "args": {"option": "A", "target_lord": tgt},
                        "note": f"Veche A: spend 1 VP marker, shift {tgt} cylinder 2 boxes LEFT (3.5.2)",
                    })
                # Option B: auto-Muster a Ready Russian Lord at a Free Seat (no Fealty).
                ready_ru = [
                    lid for lid, lord in state.lords.items()
                    if lord.side == "russian" and lord.state == "ready"
                    and _is_ready(state, lid, levy_box)
                    and _free_seats_for(state, lid)
                ]
                for tgt in ready_ru:
                    for seat in _free_seats_for(state, tgt):
                        out.append({
                            "type": "veche_action", "side": "russian",
                            "args": {"option": "B", "target_lord": tgt, "seat": seat},
                            "note": f"Veche B: spend 1 VP marker, auto-Muster {tgt} at {seat} (3.5.2)",
                        })
                # Option C: extra Muster at full Lordship for a Mustered Lord.
                extra_targets = [
                    lid for lid, lord in state.lords.items()
                    if lord.side == "russian" and lord.state == "mustered"
                    and lord.location is not None
                    and _is_friendly_locale(state, lord.location, "russian")
                    and not _is_besieged(state, lid)
                    and not lord.just_arrived_this_levy
                ]
                for tgt in extra_targets:
                    out.append({
                        "type": "veche_action", "side": "russian",
                        "args": {"option": "C", "target_lord": tgt},
                        "note": f"Veche C: spend 1 VP marker, give {tgt} extra Muster at full Lordship (3.5.2)",
                    })
            # Option D: decline Aleksandr/Andrey for +1 VP marker.
            decline_avail = (
                _is_ready(state, "aleksandr", levy_box)
                or _is_ready(state, "andrey", levy_box)
            )
            if decline_avail:
                out.append({
                    "type": "veche_action", "side": "russian",
                    "args": {"option": "D"},
                    "note": "Veche D: decline Ready Aleksandr/Andrey for +1 VP marker (3.5.2)",
                })
            out.append({
                "type": "veche_action", "side": "russian",
                "args": {"option": "skip"},
                "note": "Veche skip: take no Veche action this Call to Arms",
            })
        out.append({"type": "aow_discard_this_levy", "side": "russian", "args": {}})
    return out



def _maybe_preview_note(state: GameState, action: dict[str, Any], with_previews: bool, base_note: str) -> str:
    """Append vp_forecast preview to base_note when with_previews is True."""
    if not with_previews:
        return base_note
    try:
        from nevsky.previews import vp_forecast
        fc = vp_forecast(state, action, preview_trials=15)
        n = fc.get("note") or ""
        if n:
            return f"{base_note} | {n}"
        return base_note
    except (ImportError, KeyError, ValueError, AttributeError) as e:
        return f"{base_note} | (preview unavailable: {type(e).__name__})"


def _campaign_moves(state: GameState, side: Side, *, with_previews: bool = True) -> list[dict[str, Any]]:
    from nevsky.campaign import _plan_target_size

    out: list[dict[str, Any]] = []
    # Combat-pending response takes priority.
    if state.combat_pending is not None:
        cp = state.combat_pending
        if cp.pending_response_by == side:
            stand_note = _maybe_preview_note(
                state,
                {"type": "stand_battle", "side": side, "args": {}},
                with_previews, "engage in Battle",
            )
            out.append({"type": "stand_battle", "side": side, "args": {}, "note": stand_note})
            # Concede pseudo-option: stand_battle with concede flag.
            # Note describes the mechanical effect only; the consumer
            # decides whether/when to use it.
            concede_note = (
                "Concede the Field (4.4.2 NEW ROUND): Conceder loses "
                "the Battle (other side wins). Conceder takes half Hits "
                "from the Pursuing side this Round (round up by step). "
                "Spoils transfer at end of Battle uses the loot_and_excess "
                "mode (transfer all Loot and any Provender beyond Unladen "
                "for the Retreat Way) per 4.4.3 2E."
            )
            # SMOKE-119 (Round 186): the concede arg expects a
            # battle role ("attacker" or "defender"), not a game
            # side ("teutonic" / "russian"). Translate via
            # cp.attacker_side. Pre-fix, the legal-moves enumerator
            # offered {"concede": side} which the harness rejected
            # with bad_concede when the LLM/agent tried to use it.
            concede_role = "attacker" if cp.attacker_side == side else "defender"
            out.append({
                "type": "stand_battle", "side": side,
                "args": {"concede": concede_role},
                "note": concede_note,
            })
            # Avoid Battle: per-destination forecast (just no battle).
            if not cp.laden:
                from nevsky.static_data import load_ways, load_locales
                _ways = load_ways()
                _locs = load_locales()
                here = cp.to_locale  # defenders are at to_locale
                # Note: defender retreats one Locale away. They may
                # not Avoid into a Locale containing enemy Lords.
                attacker_loc = cp.from_locale
                # Adjacent destinations.
                adj_set = set()
                for w in _ways:
                    if w["a"] == here:
                        adj_set.add(w["b"])
                    elif w["b"] == here:
                        adj_set.add(w["a"])
                for dest in sorted(adj_set):
                    if dest == attacker_loc:
                        continue  # cannot Avoid back through attackers
                    # Skip if enemy Lord present at dest.
                    enemy_at_dest = any(
                        l.side != side and l.state == "mustered"
                        and l.location == dest and not l.in_stronghold
                        for l in state.lords.values()
                    )
                    if enemy_at_dest:
                        continue
                    note = (
                        f"Avoid Battle to {dest} (4.3.4). Defender "
                        f"Lord(s) move to {dest}; no Battle this "
                        f"Approach. No Service shift on Avoid (Service "
                        f"shifts only on Retreat, 4.4.3). Defender "
                        f"discards all Loot and any Provender beyond "
                        f"Transport usable on the Avoid Way; discards "
                        f"transfer to attacker(s) as Spoils (4.4.3 "
                        f"\"as if Spoils\"). If Legate co-located "
                        f"with a Teutonic Avoiding Lord, Legate removed "
                        f"and William of Modena discarded (1.4.1)."
                    )
                    out.append({
                        "type": "avoid_battle", "side": side,
                        "args": {"to": dest},
                        "note": note,
                    })
            # Withdraw: convert Battle into Siege.
            withdraw_note = (
                "Withdraw all defender Lords into Stronghold at "
                f"{cp.to_locale} (no args required; capacity-checked "
                "per Stronghold type, becomes Besieged 4.3.4). "
                "After Withdraw: Siege marker placed at the Locale; "
                "defender Lord(s) are inside the Stronghold and "
                "Besieged; Tax/Forage and most actions blocked while "
                "Besieged (4.3.5)."
            )
            out.append({"type": "withdraw", "side": side, "args": {},
                        "note": withdraw_note})
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
                # Concrete entries: one per Mustered Lord + one for pass.
                for lid in mustered:
                    if lid not in deck.plan:  # cannot plan same Lord twice in one stack
                        out.append({
                            "type": "plan_add_card", "side": side,
                            "args": {"card": lid},
                            "note": f"Plan slot {len(deck.plan)+1}/{target}: include {lid} in this Campaign's activation order",
                        })
                out.append({
                    "type": "plan_add_card", "side": side,
                    "args": {"card": "pass"},
                    "note": f"Plan slot {len(deck.plan)+1}/{target}: Pass card (no Lord activates this slot)",
                })
            else:
                out.append({
                    "type": "finalize_plan", "side": side, "args": {},
                    "note": f"Finalize plan ({len(deck.plan)}/{target} cards stacked, ready)",
                })
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
        # Enumerate reachable destinations via Ways from active Lord's Locale.
        # Per 4.3.x: 1 Locale per March action.
        active = state.lords[active_lord]
        try:
            from nevsky.static_data import load_ways
            ways = load_ways()
            here = active.location
            adj = []
            for w in ways:
                if w["a"] == here:
                    adj.append((w["b"], w.get("type", "?")))
                elif w["b"] == here:
                    adj.append((w["a"], w.get("type", "?")))
            from nevsky.campaign import _has_enemy_stronghold_at
            for dest, way_type in adj:
                base_note = f"March {active_lord} {here}->{dest} via {way_type} (1 action Unladen, 2 Laden)"
                # Warn when entering enemy-territory Stronghold: per rule
                # 4.3 ends_card_when began_siege, this March places a
                # Siege marker AND ends the Command card.
                try:
                    if _has_enemy_stronghold_at(state, dest, side):
                        base_note += " | NOTE: enters enemy Stronghold; places Siege & ends the Command card (4.3)"
                except (KeyError, AttributeError):
                    pass
                # Warn when entering Locale with enemy Lord(s) -- triggers
                # Approach decision (Avoid Battle / Withdraw / Stand).
                enemy_at_dest = [
                    lid for lid, l in state.lords.items()
                    if l.side != side and l.state == "mustered"
                    and l.location == dest and not l.in_stronghold
                ]
                if enemy_at_dest:
                    base_note += f" | NOTE: enemy Lord(s) {enemy_at_dest} at dest; triggers Approach decision (4.3.4)"
                out.append({
                    "type": "cmd_march", "side": side,
                    "args": {"lord_id": active_lord, "to": dest},
                    "note": base_note,
                })
        except (ImportError, KeyError, AttributeError, FileNotFoundError) as e:
            # Static-data load failure or shape mismatch: fall back to the
            # template form so the consumer still sees an action shape.
            out.append({"type": "cmd_march", "side": side,
                        "args_template": {"lord_id": "<id>", "to": "<locale_id>", "group": "[<id>]"},
                        "note": f"March 1 Locale (preview unavailable: {type(e).__name__})"})
        # Siege/Storm if Lord is at a Stronghold with siege markers,
        # is not Besieged inside, and is besieging.
        # SMOKE-075 (Round 77): use _effective_stronghold so Castle
        # overlays on Town are recognized (T17 Stonemasons); the
        # earlier _stronghold_at keyed off the base type and returned
        # None for Town, hiding the cmd_siege / cmd_storm legal moves.
        from nevsky.campaign import _effective_stronghold, _is_besieged as _ib
        if active.location is not None:
            sh = _effective_stronghold(state, active.location)
            sm = state.locales[active.location].siege_markers
            if sh is not None and sm > 0 and not _ib(state, active_lord) and sh.get("side") != side:
                out.append({"type": "cmd_siege", "side": side,
                            "args": {"lord_id": active_lord},
                            "note": "Siege (4.5.1) -- entire card; surrender or siegeworks"})
                if not sh.get("no_storm"):
                    storm_note = _maybe_preview_note(
                        state,
                        {"type": "cmd_storm", "side": side,
                          "args": {"lord_id": active_lord}},
                        with_previews, "Storm (4.5.2) -- entire card",
                    )
                    out.append({"type": "cmd_storm", "side": side,
                                "args": {"lord_id": active_lord},
                                "note": storm_note})
            if _ib(state, active_lord):
                sally_note = _maybe_preview_note(
                    state,
                    {"type": "cmd_sally", "side": side,
                      "args": {"lord_id": active_lord}},
                    with_previews,
                    "Sally (4.5.3) -- entire card; Besieged Lord attacks Besiegers",
                )
                out.append({"type": "cmd_sally", "side": side,
                            "args": {"lord_id": active_lord},
                            "note": sally_note})
        out.append({"type": "cmd_pass", "side": side,
                    "args": {"lord_id": active_lord},
                    "note": "forfeit remaining actions"})
        out.append({"type": "cmd_tax", "side": side,
                    "args": {"lord_id": active_lord},
                    "note": "+1 Coin at own Seat (entire card)"})
        out.append({"type": "cmd_forage", "side": side,
                    "args": {"lord_id": active_lord},
                    "note": "+1 Provender (1 action)"})
        ravage_note = "Ravage current Locale (1-2 actions); +0.5 VP for own Ravaged marker"
        out.append({"type": "cmd_ravage", "side": side,
                    "args": {"lord_id": active_lord, "locale_id": active.location},
                    "note": ravage_note})
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
