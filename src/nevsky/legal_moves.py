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
        # R199 (SMOKE-131): in Arts of War, advance_step is illegal
        # while this side still owes implementation of drawn cards.
        _sd_deck = state.decks.teutonic if side == "teutonic" else state.decks.russian
        # R199/R201 (SMOKE-131): suppress advance whenever this side
        # still owes implementation of drawn AoW cards (all Levies).
        # Pending cards always have a clearing move: implement (cap or
        # event-with-target), auto-discard (no eligible Lord, Q-R190-A),
        # or bare-implement no-op-discard (un-targetable Event, R201).
        if not (step == "arts_of_war" and _sd_deck.pending_draw):
            moves.append({"type": "advance_step", "side": side, "args": {}})
    elif state.meta.phase == "campaign":
        moves.extend(_campaign_moves(state, side, with_previews=with_previews))
    return moves


def _aow_moves(state: GameState, side: Side) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    sd = state.decks.teutonic if side == "teutonic" else state.decks.russian
    # SMOKE-124 (Round 190): need cards static data for capability scope check.
    cards = load_cards()
    if sd.pending_draw:
        # Must implement before drawing more.
        # SMOKE-124 (Round 190): when this is first_levy implementation
        # AND the card has capability_scope == "this_lord", the handler
        # requires args.lord_id targeting a Mustered own-side Lord with
        # capacity and eligibility (per 3.1.2 / 3.4.4 / SMOKE-029). The
        # naive pending_draw[0] emit-without-lord_id was rejected with
        # missing_arg. Expand to one option per eligible Lord.
        cid_pending = sd.pending_draw[0]
        card_pending = cards[cid_pending]
        is_capability_phase = not state.meta.first_levy_done
        scope_pending = card_pending.get("capability_scope") or "?"
        if (is_capability_phase
                and scope_pending == "this_lord"
                and not card_pending.get("no_event")):
            from nevsky.actions import _check_capability_eligibility
            eligible_lords = []
            for lid, lord in state.lords.items():
                if lord.side != side or lord.state != "mustered":
                    continue
                if len(lord.this_lord_capabilities) >= 2:
                    continue
                cap_name_p = card_pending.get("capability_name") or "?"
                if any(cards[ex].get("capability_name") == cap_name_p
                       for ex in lord.this_lord_capabilities):
                    continue
                try:
                    _check_capability_eligibility(card_pending, lid, role="target")
                except Exception:
                    continue
                eligible_lords.append(lid)
            for lid in eligible_lords:
                out.append({
                    "type": "aow_implement_card",
                    "side": side,
                    "args": {"card_id": cid_pending, "lord_id": lid},
                    "note": f"implements pending_draw {cid_pending} on {lid} (this_lord scope, 3.1.2)",
                })
            if not eligible_lords:
                # Q-R190-A (Round 193, adjudicated): when no Mustered
                # own-side Lord matches the Capability's coats of arms,
                # the handler auto-discards. Emit a single option
                # routing through that path so the agent/LLM has a
                # legal move to pick rather than stalling on
                # pending_draw.
                out.append({
                    "type": "aow_implement_card",
                    "side": side,
                    "args": {"card_id": cid_pending},
                    "note": f"auto-discards pending_draw {cid_pending} "
                            f"— no Mustered own-side Lord matches "
                            f"coats of arms (3.1.2 bullet)",
                })
        elif not is_capability_phase:
            # R202: subsequent Levy -> the pending card implements as an
            # Event (3.1.3). Events are mandatory when targetable
            # (Q-R201-A, 3.1.4 Greed), so offer the arg-populated
            # implements that actually resolve (one per legal
            # target/direction/magnitude). The advance-block stays
            # satisfiable with a concrete legal move. If NONE resolve
            # (no legal target), offer the bare implement, which the
            # handler reveal-and-discards with no effect.
            from nevsky.event_args import applicable_event_implements
            try:
                applicable = applicable_event_implements(state, side, cid_pending)
            except Exception:
                applicable = []
            for act in applicable:
                out.append({
                    "type": "aow_implement_card", "side": side,
                    "args": act["args"],
                    "note": f"implements Event {cid_pending} (3.1.3)",
                })
            if not applicable:
                out.append({
                    "type": "aow_implement_card", "side": side,
                    "args": {"card_id": cid_pending},
                    "note": f"reveal-and-discard {cid_pending} "
                            f"— no legal target (3.1.4 Greed)",
                })
        else:
            # First-Levy side_wide Capability: implement needs no
            # lord_id (3.1.2).
            out.append({
                "type": "aow_implement_card",
                "side": side,
                "args": {"card_id": cid_pending},
                "note": "implements side-wide Capability (3.1.2)",
            })
    else:
        # R199 (SMOKE-132): SoP 3.1 draws exactly 2 cards per Levy.
        # Only offer shuffle/draw if this side hasn't already drawn
        # this Levy; once drawn (and implemented), the only AoW move
        # left is advance_step.
        already_drawn = (state.meta.aow_drawn_t if side == "teutonic"
                         else state.meta.aow_drawn_r)
        if not already_drawn:
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
    # R199 (SMOKE-133): exclude Lords blocked from using Lordship this
    # Levy (R11 Valdemar / R17 Dietrich set block_lords_this_levy_*).
    # _h_muster_lord / _h_muster_vassal reject these with
    # blocked_this_levy; levy_capability already filters them
    # (SMOKE-118) but the muster enumeration did not, so muster_lord /
    # muster_vassal were offered for a blocked Lord -- an
    # enumerator/handler asymmetry. Surfaced when a trajectory reached
    # a Levy with a blocked Lord still holding Lordship budget.
    _block = (state.meta.block_lords_this_levy_t if side == "teutonic"
              else state.meta.block_lords_this_levy_r)
    by_with_budget = [
        lid for lid in own_mustered
        if state.lords[lid].lordship_used < int(static[lid]["ratings"]["lordship"])
        and lid not in _block
    ]

    # Muster Lord: identify Ready own-side Lords with Free Seats (Aleksandr excluded).
    ready_targets: dict[str, list[str]] = {}
    for lid, sl in static.items():
        if sl["side"] != side or lid == "aleksandr":
            continue
        if state.lords[lid].state != "ready":
            continue
        # SMOKE-147 (R209): a Lord blocked this Levy (R11/R17) cannot be a
        # Muster TARGET either -- _h_muster_lord rejects target_id in block
        # with blocked_this_levy. The enumerator filtered the by_lord
        # (SMOKE-133) but not the target, so a blocked Ready Lord was still
        # offered as a Muster target. Exclude blocked targets.
        if lid in _block:
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
            # SMOKE-123 (Round 190): T13 William of Modena requires
            # Heinrich on map (per AoW Reference Event Tip). The
            # handler hardcodes this check in actions.py; the
            # SMOKE-118 capability_eligibility filter doesn't catch
            # it because T13's eligibility data permits any Lord
            # to Levy it -- the runtime condition is separate.
            if cid == "T13" and side == "teutonic":
                h = state.lords.get("heinrich")
                if h is None or h.state != "mustered" or h.location is None:
                    continue
                # SMOKE-149 (R209): R15 Death of the Pope blocks Levy of
                # T13 William of Modena for the rest of this Levy
                # (handler raises capability_blocked). Mirror it here.
                if state.meta.special_rules.get("block_william_of_modena_this_levy"):
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
        # Sea-trade (R8 Black Sea / R9 Baltic). SMOKE-148 (R209): mirror
        # ALL of _veche_sea_trade's reject conditions so the enumerator
        # does not offer a guaranteed-illegal sea_trade. Pre-fix it
        # checked only capability-in-play, coin<8, and R9-winter; it
        # omitted the once-per-CtA flag (sea_trade_blocked already_used)
        # and the Conquered/ship-parity blocks.
        for cid in ("R8", "R9"):
            if cid not in state.decks.russian.capabilities_in_play:
                continue
            if state.veche.coin >= 8:
                continue
            if state.meta.special_rules.get(f"sea_trade_{cid.lower()}_used_this_cta"):
                continue
            _nov = state.locales["novgorod"]
            if cid == "R8":
                if _nov.teutonic_conquered > 0 or state.locales["lovat"].teutonic_conquered > 0:
                    continue
            else:  # R9
                if _nov.teutonic_conquered > 0 or state.locales["neva"].teutonic_conquered > 0:
                    continue
                if _season_of_box(state.meta.box) in ("early_winter", "late_winter"):
                    continue
                from nevsky.campaign import effective_ship_count, effective_boat_count
                _teu = sum(effective_ship_count(state, lid)
                           for lid, l in state.lords.items()
                           if l.side == "teutonic" and l.state == "mustered")
                _rus = sum(effective_ship_count(state, lid)
                           + (effective_boat_count(state, lid)
                              - state.lords[lid].assets.get("boat", 0))
                           for lid, l in state.lords.items()
                           if l.side == "russian" and l.state == "mustered")
                if _teu > _rus:
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
            if cp.ambush_block_pending:
                # R204: Ambush response window (SMOKE-115). The attacker
                # (response owed) holds T6/R6 and may Play it to block the
                # defender's Avoid, or Decline. No stand/avoid/withdraw
                # here -- those were previously (wrongly) the only options
                # offered, and play/decline were not enumerated at all.
                out.append({"type": "play_ambush_block", "side": side, "args": {},
                            "note": "Play T6/R6 Ambush to block the defender's Avoid Battle"})
                out.append({"type": "decline_ambush_block", "side": side, "args": {},
                            "note": "Decline Ambush; the defender's Avoid Battle resolves as declared"})
                return out
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
            # R204: 4.1.3 Lieutenant pairing -- an optional Plan-time action
            # (a Lieutenant carries one co-located Lower Lord). Mirror
            # _h_place_lieutenant; was never enumerated.
            try:
                from nevsky.campaign import (
                    _is_currently_marshal as _icm_lt, _is_besieged as _ib_lt,
                )
                _own_lt = [
                    lid for lid, l in state.lords.items()
                    if l.side == side and l.state == "mustered"
                    and l.location is not None and not _ib_lt(state, lid)
                    and not _icm_lt(state, lid)
                    and not l.lieutenant_of
                ]
                for _lt in _own_lt:
                    if state.lords[_lt].has_lower_lord:
                        continue  # already carrying a Lower Lord
                    for _ll in _own_lt:
                        if _ll == _lt:
                            continue
                        if state.lords[_ll].location != state.lords[_lt].location:
                            continue
                        if state.lords[_ll].has_lower_lord:
                            continue  # _ll is itself a Lieutenant (no chains)
                        out.append({
                            "type": "place_lieutenant", "side": side,
                            "args": {"lieutenant": _lt, "lower_lord": _ll},
                            "note": f"Pair {_ll} as Lower Lord under Lieutenant {_lt} (4.1.3)",
                        })
            except (ImportError, KeyError, AttributeError):
                pass
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
            # BUG-4 (R203): during this side's 4.8.2 Pay window, offer Pay
            # (3.2 mechanics) to shift Service right and avert a pending
            # mid-campaign Disband. fpd_resolve then runs the Disband check.
            if state.campaign_turn.fpd_pay_window_side == side:
                out.extend(_pay_moves(state, side))
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
        # BUG-2 (R203): entire-card Commands (Siege/Storm/Sally/Tax/Sail,
        # plus Stone Kremlin) require a pristine Command card. At reveal
        # actions_remaining == _effective_command_rating(lord); once the
        # Lord has Marched/acted it drops below, so these moves must be
        # suppressed (the handlers now raise must_be_full_card).
        from nevsky.campaign import _effective_command_rating as _ecr_lm
        pristine = (state.campaign_turn.actions_remaining
                    >= _ecr_lm(state, active_lord))
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
            from nevsky.campaign import (
                _has_enemy_stronghold_at,
                _is_laden as _il_mr,
                _must_discard_to_move_excess as _mdme_mr,
            )
            for dest, way_type in adj:
                # SMOKE-128 (Round 190): cmd_march costs 1 action
                # Unladen, 2 Laden (4.3). Suppress the option when the
                # active Lord's actions_remaining can't cover the cost
                # for this specific way_type -- the handler raises
                # insufficient_actions. The enumerator already had way
                # information per-edge, so the check is cheap.
                # SMOKE-146 (R209): an active Lieutenant MUST March
                # together with his Lower Lord (4.1.3; handler raises
                # lower_lord_required otherwise). The handler computes
                # Laden cost and the 4.3.2 excess-Provender gate across
                # ALL group members, so SMOKE-151 (R210) computes both
                # over the whole March group -- not just the active Lord
                # -- otherwise a Lieutenant whose Lower Lord is Laden /
                # carries excess Provender is over-enumerated (rejected
                # with insufficient_actions / excess_provender).
                _lower = state.lords[active_lord].has_lower_lord
                march_group = [active_lord] + ([_lower] if _lower is not None else [])
                march_laden = any(_il_mr(state, gid, way_type=way_type) for gid in march_group)
                march_cost = 2 if march_laden else 1
                if state.campaign_turn.actions_remaining < march_cost:
                    continue
                # SMOKE-127 (Round 190): 4.3.2 gate -- a Lord with more
                # than 2x usable Transport in Provender may NOT March
                # unless he discards the excess. The handler accepts
                # an explicit args.discard_excess_provender=True to
                # auto-discard. Emit the flag when ANY group member
                # would trip the gate, so every emitted cmd_march is legal.
                excess_mr = sum(_mdme_mr(state, gid, way_type=way_type) for gid in march_group)
                base_note = f"March {active_lord} {here}->{dest} via {way_type} (cost={march_cost})"
                args_mr: dict[str, Any] = {"lord_id": active_lord, "to": dest}
                if _lower is not None:
                    args_mr["group"] = [active_lord, _lower]
                if excess_mr > 0:
                    args_mr["discard_excess_provender"] = True
                    base_note += f" | NOTE: discards {excess_mr} excess Provender (4.3.2)"
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
                    "args": args_mr,
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
            if pristine and sh is not None and sm > 0 and not _ib(state, active_lord) and sh.get("side") != side:
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
            if pristine and _ib(state, active_lord):
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
            # BUG-1 (R203): R18 Stone Kremlin is a Campaign Command
            # action (entire card) and was never enumerated, so a player
            # driving off legal_actions could never use the capability.
            # Mirror _h_cmd_stone_kremlin preconditions (pristine card;
            # own Russian Fort/City/Novgorod; no Castle; no existing
            # Walls +1; < 4 markers in play). A Besieged Lord may use it.
            if pristine and side == "russian":
                try:
                    from nevsky.capabilities import has_lord_capability as _hlc_sk
                    from nevsky.static_data import load_locales as _ll_sk
                    _sl_sk = _ll_sk().get(active.location)
                    _ls_sk = state.locales.get(active.location)
                    if (_sl_sk is not None and _ls_sk is not None
                            and _hlc_sk(state, active_lord, "Stone Kremlin")
                            and _sl_sk.get("territory") == "russian"
                            and _sl_sk.get("type") in ("fort", "city", "novgorod")
                            and not _ls_sk.teutonic_castle
                            and not _ls_sk.russian_castle
                            and not _ls_sk.walls_plus_one
                            and sum(1 for _l in state.locales.values()
                                    if _l.walls_plus_one) < 4):
                        out.append({"type": "cmd_stone_kremlin", "side": side,
                                    "args": {"lord_id": active_lord},
                                    "note": "Stone Kremlin (R18): Walls +1 (entire card)"})
                except (ImportError, KeyError, AttributeError, FileNotFoundError):
                    pass
            # R204: T17 Stonemasons -- entire-card Teutonic capability that
            # converts an Unbesieged Russian Fort/Town in Rus into a Castle
            # for 6 Provender (own + co-located shared). Mirror
            # _h_cmd_stonemasons preconditions; was never enumerated.
            if pristine and side == "teutonic":
                try:
                    from nevsky.capabilities import has_lord_capability as _hlc_sm
                    from nevsky.static_data import load_locales as _ll_sm
                    _sl_sm = _ll_sm().get(active.location)
                    _ls_sm = state.locales.get(active.location)
                    _built = int(state.meta.special_rules.get("stonemasons_castles_built", 0))
                    if (_sl_sm is not None and _ls_sm is not None
                            and _hlc_sm(state, active_lord, "Stonemasons")
                            and not _ib(state, active_lord)
                            and _sl_sm.get("territory") == "russian"
                            and _sl_sm.get("type") in ("fort", "town")
                            and not _ls_sm.teutonic_castle
                            and not _ls_sm.russian_castle
                            and _ls_sm.siege_markers == 0
                            and _built < 2):
                        _own_p = active.assets.get("provender", 0)
                        _shared = sum(
                            ol.assets.get("provender", 0)
                            for olid, ol in state.lords.items()
                            if olid != active_lord and ol.side == side
                            and ol.state == "mustered"
                            and ol.location == active.location)
                        if _own_p + _shared >= 6:
                            out.append({"type": "cmd_stonemasons", "side": side,
                                        "args": {"lord_id": active_lord},
                                        "note": "Stonemasons (T17): build Castle, 6 Provender (entire card)"})
                except (ImportError, KeyError, AttributeError, FileNotFoundError):
                    pass
        # SMOKE-143 (R206): Legate Command bonus (4.2). Offer the +1 when
        # the active Teutonic Lord started his card co-located with the
        # on-map Legate and has not already taken it this card.
        if (side == "teutonic"
                and state.campaign_turn.legate_bonus_available
                and not state.campaign_turn.legate_bonus_elected):
            out.append({"type": "legate_command_bonus", "side": side,
                        "args": {"lord_id": active_lord},
                        "note": "Legate (4.2): +1 Command action this card "
                                "(pawn returns to William of Modena when the extra action is used)"})
        out.append({"type": "cmd_pass", "side": side,
                    "args": {"lord_id": active_lord},
                    "note": "forfeit remaining actions"})
        # SMOKE-125 (Round 190): cmd_tax requires the active Lord be
        # at his own Seat (4.7.4). Without this filter the enumerator
        # surfaces guaranteed-illegal Tax actions whenever the active
        # Lord is anywhere but his Seat -- which is most of the game.
        from nevsky.campaign import _is_own_seat
        if (active.location is not None
                and pristine
                and _is_own_seat(state, active_lord, active.location)
                and active.assets.get("coin", 0) < 8):
            out.append({"type": "cmd_tax", "side": side,
                        "args": {"lord_id": active_lord},
                        "note": "+1 Coin at own Seat (entire card)"})
        # SMOKE-126 (Round 190): cmd_forage requires (a) Locale NOT
        # Ravaged AND (b) at a Friendly Stronghold OR season is Summer
        # (4.7.1). The enumerator was offering forage at ravaged
        # Locales (forage code: ravaged) and at non-friendly non-Summer
        # Locales (forage_seasonal). Mirror _h_cmd_forage's pre-checks.
        forage_ok = False
        if active.location is not None and active.assets.get("provender", 0) < 8:
            try:
                from nevsky.campaign import (
                    _effective_stronghold as _es_fg,
                    _is_friendly_locale as _ifr_fg,
                )
                from nevsky.scenarios import _season_for_box as _sfb_fg
                loc_state_fg = state.locales.get(active.location)
                if loc_state_fg is not None:
                    own_rav = (loc_state_fg.teutonic_ravaged if side == "teutonic"
                               else loc_state_fg.russian_ravaged)
                    enemy_rav = (loc_state_fg.russian_ravaged if side == "teutonic"
                                 else loc_state_fg.teutonic_ravaged)
                    if not (own_rav or enemy_rav):
                        season_fg = _sfb_fg(state.meta.box)
                        eff_sh_fg = _es_fg(state, active.location)
                        is_fr_sh = (
                            eff_sh_fg is not None
                            and not eff_sh_fg.get("no_storm")
                            and _ifr_fg(state, active.location, side)
                        )
                        if is_fr_sh or season_fg == "summer":
                            forage_ok = True
            except (ImportError, KeyError, AttributeError, FileNotFoundError):
                forage_ok = False
        if forage_ok:
            out.append({"type": "cmd_forage", "side": side,
                        "args": {"lord_id": active_lord},
                        "note": "+1 Provender (1 action)"})
        # SMOKE-122 (Round 188): pre-filter cmd_ravage by the same
        # rejection conditions enforced in _h_cmd_ravage (campaign.py
        # 4.7.2): NOT own territory, NOT already Conquered, NOT
        # Friendly to active side, NOT already Ravaged. Without this
        # filter the enumerator surfaces guaranteed-illegal options
        # (e.g. ravage at own Seat), which trips LLM agents and is a
        # known over-enumeration pattern (see SMOKE-118/120).
        ravage_ok = False
        if active.location is not None:
            try:
                from nevsky.static_data import load_locales as _ll_rv
                _static_locs_rv = _ll_rv()
                _static_loc_rv = _static_locs_rv.get(active.location)
                _loc_state_rv = state.locales.get(active.location)
                if _static_loc_rv is not None and _loc_state_rv is not None:
                    if (
                        _static_loc_rv.get("territory") != side
                        and _loc_state_rv.russian_conquered == 0
                        and _loc_state_rv.teutonic_conquered == 0
                        and not _is_friendly_locale(state, active.location, side)
                        and not _loc_state_rv.russian_ravaged
                        and not _loc_state_rv.teutonic_ravaged
                    ):
                        ravage_ok = True
                        # SMOKE-150 (R209): Ravage costs 2 actions if an
                        # Unbesieged enemy Lord is adjacent to the target
                        # (4.7.2 2E); _h_cmd_ravage raises
                        # insufficient_actions otherwise. Suppress when the
                        # active Lord can't afford the cost.
                        from nevsky.static_data import load_ways as _lw_rv
                        from nevsky.campaign import _is_besieged as _ib_rv
                        _adj_rv = set()
                        for _w in _lw_rv():
                            if _w["a"] == active.location:
                                _adj_rv.add(_w["b"])
                            elif _w["b"] == active.location:
                                _adj_rv.add(_w["a"])
                        _rv_cost = 1
                        for _ol, _olst in state.lords.items():
                            if (_olst.state == "mustered" and _olst.side != side
                                    and _olst.location in _adj_rv
                                    and not _ib_rv(state, _ol)):
                                _rv_cost = 2
                                break
                        if state.campaign_turn.actions_remaining < _rv_cost:
                            ravage_ok = False
            except (ImportError, KeyError, AttributeError, FileNotFoundError):
                # On static-data load failure, conservatively suppress
                # the option rather than offer a likely-illegal one.
                ravage_ok = False
        if ravage_ok:
            ravage_note = "Ravage current Locale (1-2 actions); +0.5 VP for own Ravaged marker"
            out.append({"type": "cmd_ravage", "side": side,
                        "args": {"lord_id": active_lord, "locale_id": active.location},
                        "note": ravage_note})
        # R204: R4 Smerdi -- 1-action Russian capability to Muster 1 Serf
        # (pool of 6) at an Unbesieged Russian Lord in Rus. Mirror
        # _h_cmd_muster_serf; was never enumerated.
        if side == "russian" and active.location is not None:
            try:
                from nevsky.capabilities import has_side_capability as _hsc_sm
                from nevsky.static_data import load_locales as _ll_serf
                _sl_serf = _ll_serf().get(active.location)
                _serfs_in_play = sum(
                    l.forces.get("serfs", 0) for l in state.lords.values()
                    if l.side == "russian" and l.state == "mustered")
                if (_sl_serf is not None
                        and _hsc_sm(state, "russian", "Smerdi")
                        and not _ib(state, active_lord)
                        and _sl_serf.get("territory") == "russian"
                        and _serfs_in_play < 6):
                    out.append({"type": "cmd_muster_serf", "side": side,
                                "args": {"lord_id": active_lord},
                                "note": "Smerdi (R4): Muster 1 Serf (1 action)"})
            except (ImportError, KeyError, AttributeError, FileNotFoundError):
                pass
        # R204: T2/R12/R14 Raiders -- 1-action Ravage of an adjacent enemy
        # Locale via an eligible Way with the right Horse. Mirror
        # _h_cmd_raiders_ravage; emit one move per legal target. Was never
        # enumerated.
        if active.location is not None:
            try:
                from nevsky.capabilities import has_lord_capability as _hlc_rr
                from nevsky.static_data import (
                    load_locales as _ll_rr, load_ways as _lw_rr,
                )
                if _hlc_rr(state, active_lord, "Raiders") and not _ib(state, active_lord):
                    _is_teu_r = side == "teutonic"
                    _elig = (["knights", "sergeants", "light_horse"] if _is_teu_r
                             else ["light_horse", "asiatic_horse"])
                    _has_horse = any(active.forces.get(u, 0) > 0 for u in _elig)
                    _t2_used = _is_teu_r and active.raiders_used_this_card
                    if _has_horse and not _t2_used:
                        _locs_rr = _ll_rr()
                        _here_rr = active.location
                        _adj_rr = []
                        for w in _lw_rr():
                            if w["a"] == _here_rr:
                                _adj_rr.append((w["b"], w.get("type", "?")))
                            elif w["b"] == _here_rr:
                                _adj_rr.append((w["a"], w.get("type", "?")))
                        for _dest_rr, _wt_rr in _adj_rr:
                            if _is_teu_r and _wt_rr != "trackway":
                                continue
                            _sd_rr = _locs_rr.get(_dest_rr)
                            _ds_rr = state.locales.get(_dest_rr)
                            if _sd_rr is None or _ds_rr is None:
                                continue
                            if _sd_rr.get("territory") == side:
                                continue
                            if _ds_rr.russian_conquered > 0 or _ds_rr.teutonic_conquered > 0:
                                continue
                            if _ds_rr.russian_ravaged or _ds_rr.teutonic_ravaged:
                                continue
                            if any(l.state == "mustered" and l.location == _dest_rr
                                   and l.side != side for l in state.lords.values()):
                                continue
                            out.append({"type": "cmd_raiders_ravage", "side": side,
                                        "args": {"lord_id": active_lord, "to": _dest_rr},
                                        "note": f"Raiders: Ravage {_dest_rr} (1 action)"})
            except (ImportError, KeyError, AttributeError, FileNotFoundError):
                pass
        out.append({"type": "cmd_supply", "side": side,
                    "args_template": {"lord_id": "<id>", "sources": "[{locale_id, route, transport}]"},
                    "note": "Supply (1 action)"})
        if pristine:
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
