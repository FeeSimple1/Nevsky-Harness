"""State rendering.

Three modes per BRIEF:
  - summary: ~500 tokens; the LLM-friendly default. Compact, designed
    so an LLM can read the board, last few actions, and active
    pending decisions in one budget-friendly chunk.
  - verbose: full state dump, suitable for debugging. JSON-shaped text.
  - focus: a single subsystem's state -- one Lord's mat, one Locale,
    the Calendar, the Veche, or one side's deck composition.

Render functions return strings (no I/O); the CLI handles printing.
"""

from __future__ import annotations

from typing import Any

from nevsky.state import (
    Calendar,
    Decks,
    GameState,
    Locale,
    Veche,
)
from nevsky.static_data import load_cards, load_locales, load_lords

# ---------------------------------------------------------------------------
# Season labels per Calendar reference (8 seasons across 16 boxes).
# Boxes 1-2 = Summer 1240, 3-4 = Early Winter 40-41, 5-6 = Late Winter,
# 7-8 = Rasputitsa 41, 9-10 = Summer 41, 11-12 = Early Winter 41-42,
# 13-14 = Late Winter, 15-16 = Rasputitsa 42.
# ---------------------------------------------------------------------------
_SEASON_BY_BOX: dict[int, str] = {
    1: "Summer 1240", 2: "Summer 1240",
    3: "Early Winter 1240", 4: "Early Winter 1240",
    5: "Late Winter 1241", 6: "Late Winter 1241",
    7: "Rasputitsa 1241", 8: "Rasputitsa 1241",
    9: "Summer 1241", 10: "Summer 1241",
    11: "Early Winter 1241", 12: "Early Winter 1241",
    13: "Late Winter 1242", 14: "Late Winter 1242",
    15: "Rasputitsa 1242", 16: "Rasputitsa 1242",
}


def season(box: int) -> str:
    return _SEASON_BY_BOX.get(box, f"box {box}")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def _next_expected_action(state: GameState) -> str:
    """One-line hint for the LLM consumer: what action is the active side expected
    to issue next? Encodes the lockstep flow so callers don't need to grep the
    source. Returns a short imperative string.
    """
    m = state.meta
    side = m.active_player or "?"
    if m.phase == "setup":
        return f"{side}: confirm_all_setup_transports"
    if m.phase == "levy":
        deck = state.decks.teutonic if side == "teutonic" else state.decks.russian
        step = m.levy_step
        if step == "arts_of_war":
            if not deck.discard and not deck.holds and not deck.capabilities_in_play and not deck.pending_draw:
                # Likely first call: nothing drawn yet.
                return f"{side}: aow_shuffle then aow_draw"
            if deck.pending_draw:
                return f"{side}: aow_implement_card (pending: {deck.pending_draw})"
            return f"{side}: advance_step (Arts of War complete)"
        if step in ("pay", "disband"):
            return f"{side}: advance_step (no {step} action required, or apply per-Lord {step} actions)"
        if step == "muster":
            return f"{side}: muster_lord (or advance_step if no Muster needed)"
        if step == "call_to_arms":
            if side == "teutonic":
                return f"{side}: legate_arrives | legate_move | legate_use | legate_skip, then aow_discard_this_levy, then advance_step"
            else:
                return f"{side}: veche_action, then aow_discard_this_levy, then advance_step"
        return f"{side}: advance_step"
    if m.phase == "campaign":
        step = m.campaign_step
        if step == "plan":
            from nevsky.campaign import _plan_target_size
            size = _plan_target_size(m.box)
            t_done = m.plan_complete_t
            r_done = m.plan_complete_r
            if side == "teutonic" and not t_done:
                return f"{side}: plan_add_card (need {size} cards) then finalize_plan"
            if side == "russian" and not r_done:
                return f"{side}: plan_add_card (need {size} cards) then finalize_plan"
            return f"{side}: waiting on the other side\'s plan"
        if step == "command":
            if state.campaign_turn.in_feed_pay_disband:
                return f"{side}: fpd_resolve"
            return f"{side}: command_reveal then issue cmd_* actions for the active Lord"
        if step == "end_campaign":
            return f"{side}: end_campaign_resolve"
    return ""


def _pending_draws_block(state: GameState) -> list[str]:
    """If either side has pending Arts of War draws, render id, names, and effect
    text inline so the consumer doesn't need to fetch from the reference."""
    out: list[str] = []
    from nevsky.static_data import load_cards
    cards = load_cards()
    for side, deck in (("Teu", state.decks.teutonic), ("Rus", state.decks.russian)):
        if not deck.pending_draw:
            continue
        out.append(f"Pending AoW {side}:")
        for cid in deck.pending_draw:
            c = cards.get(cid, {})
            ev_name = c.get("event_name") or "—"
            ev_text = c.get("event_text") or ""
            cap_name = c.get("capability_name") or "—"
            cap_text = c.get("capability_text") or ""
            scope = c.get("capability_scope") or ""
            persist = c.get("event_persistence") or ""
            out.append(f"  {cid}: EVENT [{persist}] {ev_name} — {ev_text}")
            out.append(f"       CAP [{scope}] {cap_name} — {cap_text}")
    return out


def render_summary(state: GameState) -> str:
    """Compact, LLM-budget-friendly view of game state."""
    lines: list[str] = []
    m = state.meta
    lines.append(
        f"{m.scenario_display_name} (box {m.box}/{m.span_end_box}, "
        f"{season(m.box)}, {m.phase}, {m.active_player or '-'} to act)"
    )
    # Lockstep / next-action hint.
    hint = _next_expected_action(state)
    if hint:
        lines.append(f"Next expected: {hint}")
    # Optional rules in effect.
    active_optional = [r for r, on in m.optional_rules.items() if on]
    if active_optional:
        lines.append(f"Optional rules: {', '.join(sorted(active_optional))}")
    lines.append(
        f"VP: R={state.calendar.russian_vp:g}  T={state.calendar.teutonic_vp:g}  "
        f"Veche: {state.veche.coin} coin, {state.veche.vp_markers} VP markers"
    )
    if state.veche.novgorod_conquered:
        lines.append("  Novgorod CONQUERED (Veche cannot generate Coin via Sea Trade)")

    # Lords by side
    teu_mustered = [l for l in state.lords.values() if l.side == "teutonic" and l.state == "mustered"]
    rus_mustered = [l for l in state.lords.values() if l.side == "russian" and l.state == "mustered"]
    teu_ready = [l.lord_id for l in state.lords.values() if l.side == "teutonic" and l.state == "ready"]
    rus_ready = [l.lord_id for l in state.lords.values() if l.side == "russian" and l.state == "ready"]
    teu_removed = [l.lord_id for l in state.lords.values() if l.side == "teutonic" and l.state == "removed"]
    rus_removed = [l.lord_id for l in state.lords.values() if l.side == "russian" and l.state == "removed"]

    lines.append("Mustered Teu: " + (
        ", ".join(f"{l.lord_id}@{l.location}" for l in teu_mustered) or "(none)"
    ))
    lines.append("Mustered Rus: " + (
        ", ".join(f"{l.lord_id}@{l.location}" for l in rus_mustered) or "(none)"
    ))
    if teu_ready:
        lines.append(f"Ready Teu: {', '.join(teu_ready)}")
    if rus_ready:
        lines.append(f"Ready Rus: {', '.join(rus_ready)}")
    if teu_removed:
        lines.append(f"Removed Teu: {', '.join(teu_removed)}")
    if rus_removed:
        lines.append(f"Removed Rus: {', '.join(rus_removed)}")

    # Calendar non-empty boxes
    lines.append("Calendar:")
    for cb in state.calendar.boxes:
        bits: list[str] = []
        if cb.has_levy_campaign_marker:
            bits.append(f"L/C={cb.levy_campaign_face}")
        if cb.russian_victory_marker:
            bits.append("R-VP")
        if cb.teutonic_victory_marker:
            bits.append("T-VP")
        if cb.cylinders:
            bits.append("cyl[" + ",".join(cb.cylinders) + "]")
        if cb.service_markers:
            bits.append("svc[" + ",".join(cb.service_markers) + "]")
        if cb.vassal_service_markers:
            bits.append("vsvc[" + ",".join(cb.vassal_service_markers) + "]")
        if bits:
            lines.append(f"  box {cb.box} ({season(cb.box)}): {' '.join(bits)}")
    if state.calendar.off_left:
        lines.append(f"  off-left (cyl): {', '.join(state.calendar.off_left)}")
    if state.calendar.off_right:
        lines.append(f"  off-right (cyl): {', '.join(state.calendar.off_right)}")
    if state.calendar.off_left_service:
        lines.append(f"  off-left (svc): {', '.join(state.calendar.off_left_service)}")
    if state.calendar.off_right_service:
        lines.append(f"  off-right (svc): {', '.join(state.calendar.off_right_service)}")

    # Locale markers (only non-empty)
    map_lines = _summarize_locale_markers(state.locales)
    if map_lines:
        lines.append("Map markers:")
        lines.extend("  " + ml for ml in map_lines)

    # Pending Arts of War draws with full effect text
    pending_block = _pending_draws_block(state)
    if pending_block:
        lines.extend(pending_block)

    # Plan-step extras: required size, current sizes per side
    if m.phase == "campaign" and m.campaign_step == "plan":
        from nevsky.campaign import _plan_target_size
        plan_size = _plan_target_size(m.box)
        t_size = len(state.decks.teutonic.plan)
        r_size = len(state.decks.russian.plan)
        lines.append(
            f"Plan: required={plan_size} | T={t_size}{'(done)' if m.plan_complete_t else ''} "
            f"| R={r_size}{'(done)' if m.plan_complete_r else ''}"
        )

    # Decks
    lines.append(
        f"Decks: Teu deck/discard/removed/cap-in-play/holds = "
        f"{len(state.decks.teutonic.deck)}/{len(state.decks.teutonic.discard)}/"
        f"{len(state.decks.teutonic.removed)}/{len(state.decks.teutonic.capabilities_in_play)}/"
        f"{len(state.decks.teutonic.holds)}"
    )
    lines.append(
        f"        Rus deck/discard/removed/cap-in-play/holds = "
        f"{len(state.decks.russian.deck)}/{len(state.decks.russian.discard)}/"
        f"{len(state.decks.russian.removed)}/{len(state.decks.russian.capabilities_in_play)}/"
        f"{len(state.decks.russian.holds)}"
    )

    if state.legate.william_of_modena_in_play:
        lines.append(
            f"Legate: William of Modena IN PLAY, pawn={state.legate.location}"
            f"{(' ' + state.legate.locale_id) if state.legate.locale_id else ''}"
        )
    else:
        lines.append("Legate: William of Modena not in play")

    if state.pending_decisions:
        lines.append(f"Pending ({len(state.pending_decisions)}):")
        for pd in state.pending_decisions[:6]:
            lines.append(f"  {pd.kind} owed by {pd.owed_by}: {pd.note or pd.context}")
        if len(state.pending_decisions) > 6:
            lines.append(f"  ... and {len(state.pending_decisions) - 6} more")

    if state.history:
        last = state.history[-3:]
        lines.append(f"Last {len(last)} actions:")
        for h in last:
            lines.append(f"  #{h.sequence} ({h.actor}): {h.action.get('kind', h.action)}")

    return "\n".join(lines)


def _summarize_locale_markers(locales: dict[str, Locale]) -> list[str]:
    out: list[str] = []
    for lid in sorted(locales):
        loc = locales[lid]
        bits: list[str] = []
        if loc.russian_conquered:
            bits.append(f"Rconq×{loc.russian_conquered}")
        if loc.teutonic_conquered:
            bits.append(f"Tconq×{loc.teutonic_conquered}")
        if loc.russian_castle:
            bits.append("R-castle")
        if loc.teutonic_castle:
            bits.append("T-castle")
        if loc.russian_ravaged:
            bits.append("R-rav")
        if loc.teutonic_ravaged:
            bits.append("T-rav")
        if loc.walls_plus_one:
            bits.append("Walls+1")
        if loc.siege_markers:
            bits.append(f"Siege×{loc.siege_markers}")
        if bits:
            out.append(f"{lid}: {' '.join(bits)}")
    return out


# ---------------------------------------------------------------------------
# Verbose
# ---------------------------------------------------------------------------


def render_verbose(state: GameState) -> str:
    """Full JSON-shaped dump (pretty-printed) of GameState."""
    return state.model_dump_json(indent=2)


# ---------------------------------------------------------------------------
# Focus
# ---------------------------------------------------------------------------


def render_focus(state: GameState, focus: str) -> str:
    """Render one subsystem.

    focus syntax:
      - "lord:<lord_id>"      -> that Lord's mat
      - "locale:<locale_id>"  -> that Locale's state + neighbors
      - "calendar"            -> full Calendar (all 16 boxes)
      - "veche"               -> Novgorod Veche box
      - "deck:teutonic" or "deck:russian" -> deck composition
    """
    if ":" in focus:
        kind, _, key = focus.partition(":")
    else:
        kind, key = focus, ""

    if kind == "lord":
        return _render_lord(state, key)
    if kind == "locale":
        return _render_locale(state, key)
    if kind == "calendar":
        return _render_calendar(state.calendar)
    if kind == "veche":
        return _render_veche(state.veche)
    if kind == "deck":
        return _render_deck(state.decks, key)
    raise ValueError(f"unknown focus {focus!r}; valid: lord:<id> | locale:<id> | calendar | veche | deck:<side>")


def _render_lord(state: GameState, lord_id: str) -> str:
    if lord_id not in state.lords:
        raise ValueError(f"unknown lord_id {lord_id!r}")
    lord = state.lords[lord_id]
    static = load_lords().get(lord_id, {})
    lines = [
        f"Lord: {static.get('name', lord_id)} ({lord.side}, id={lord_id})",
        f"  state={lord.state}, location={lord.location or '(off map)'}, moved_fought={lord.moved_fought}",
    ]
    r = static.get("ratings", {})
    lines.append(
        f"  ratings: Fealty={r.get('fealty')}, Service={r.get('service')}, "
        f"Lordship={r.get('lordship')}, Command={r.get('command')}"
    )
    seats = static.get("primary_seats", [])
    lines.append(f"  primary seats: {', '.join(seats) if seats else '(none)'}")
    if static.get("conditional_seats"):
        cond = "; ".join(_describe_conditional_seat(c) for c in static["conditional_seats"])
        lines.append(f"  conditional seats: {cond}")
    if static.get("ships_authorized"):
        lines.append("  ships_authorized: yes (mat carries Ships notation)")
    if static.get("muster_restriction"):
        lines.append(f"  muster_restriction: {static['muster_restriction']} -- {static.get('muster_restriction_note', '')}")
    if static.get("marshal_role"):
        lines.append(f"  marshal_role: {static['marshal_role']}")
    if lord.forces:
        lines.append(f"  forces: {_describe_counts(dict(lord.forces))}")
    else:
        lines.append("  forces: (none deployed)")
    if lord.assets:
        lines.append(f"  assets: {_describe_counts(dict(lord.assets))}")
    else:
        lines.append("  assets: (none)")
    if lord.this_lord_capabilities:
        lines.append(f"  this-lord capabilities: {', '.join(lord.this_lord_capabilities)}")
    if lord.vassals:
        lines.append("  vassals:")
        static_v = {v["vassal_id"]: v for v in static.get("vassals", [])}
        for vid, vstate in lord.vassals.items():
            sv = static_v.get(vid, {})
            forces_str = _describe_counts(sv.get("forces", {}))
            sp = f" [special: {sv.get('special')}]" if sv.get("special") else ""
            lines.append(
                f"    {vid} ({sv.get('name', vid)}): forces={forces_str}, "
                f"service={sv.get('service')}, ready={vstate.ready}, mustered={vstate.mustered}{sp}"
            )
    return "\n".join(lines)


def _describe_conditional_seat(c: dict[str, Any]) -> str:
    parts = []
    if c.get("capability"):
        parts.append(f"if {c['capability']}")
    if c.get("scope"):
        parts.append(f"scope={c['scope']}")
    if c.get("locale_id"):
        parts.append(f"locale={c['locale_id']}")
    if c.get("requirement"):
        parts.append(f"requires {c['requirement']}")
    return " ".join(parts) or "(unspecified)"


def _describe_counts(d: dict[str, Any]) -> str:
    items = [(k, v) for k, v in d.items() if v]
    if not items:
        return "(none)"
    return ", ".join(f"{v}× {k}" for k, v in sorted(items))


def _render_locale(state: GameState, locale_id: str) -> str:
    static_loc = load_locales().get(locale_id)
    if static_loc is None:
        raise ValueError(f"unknown locale_id {locale_id!r}")
    loc = state.locales.get(locale_id, Locale(locale_id=locale_id))
    lines = [
        f"Locale: {static_loc['name']} (id={locale_id})",
        f"  type={static_loc['type']}, territory={static_loc['territory']}, "
        f"subregion={static_loc['subregion']}, seaport={static_loc['seaport']}, "
        f"vp_when_conquered={static_loc['vp_when_conquered']}",
    ]
    bits = _summarize_locale_markers({locale_id: loc})
    if bits:
        lines.append(f"  markers: {bits[0].split(': ', 1)[1]}")
    else:
        lines.append("  markers: (none)")
    # occupants: any Lord whose location == this locale
    occ = [lid for lid, l in state.lords.items() if l.location == locale_id and l.state == "mustered"]
    lines.append(f"  occupying Lords: {', '.join(occ) if occ else '(none)'}")
    # neighbors
    from nevsky.static_data import neighbors as _nb
    nbs = _nb(locale_id)
    if nbs:
        lines.append("  neighbors:")
        for nb_id, way in sorted(nbs):
            lines.append(f"    {nb_id} ({way})")
    return "\n".join(lines)


def _render_calendar(calendar: Calendar) -> str:
    lines = [
        f"Calendar: R-VP={calendar.russian_vp:g}  T-VP={calendar.teutonic_vp:g}",
    ]
    if calendar.pleskau_lords_removed_russian or calendar.pleskau_lords_removed_teutonic:
        lines.append(
            f"  Pleskau bonus: R={calendar.pleskau_lords_removed_russian}, "
            f"T={calendar.pleskau_lords_removed_teutonic}"
        )
    for cb in calendar.boxes:
        bits: list[str] = []
        if cb.has_levy_campaign_marker:
            bits.append(f"L/C={cb.levy_campaign_face}")
        if cb.russian_victory_marker:
            bits.append("R-VP-marker")
        if cb.teutonic_victory_marker:
            bits.append("T-VP-marker")
        if cb.cylinders:
            bits.append(f"cylinders={cb.cylinders}")
        if cb.service_markers:
            bits.append(f"service={cb.service_markers}")
        if cb.vassal_service_markers:
            bits.append(f"vassal_service={cb.vassal_service_markers}")
        marker = "  " if bits else "  (empty) "
        season_str = season(cb.box)
        lines.append(f"  box {cb.box:2d} {season_str:<22s}{marker}{' '.join(bits)}")
    if calendar.off_left:
        lines.append(f"  off-left (cylinders): {calendar.off_left}")
    if calendar.off_right:
        lines.append(f"  off-right (cylinders): {calendar.off_right}")
    if calendar.off_left_service:
        lines.append(f"  off-left (service): {calendar.off_left_service}")
    if calendar.off_right_service:
        lines.append(f"  off-right (service): {calendar.off_right_service}")
    return "\n".join(lines)


def _render_veche(veche: Veche) -> str:
    return (
        f"Veche (Novgorod):\n"
        f"  coin: {veche.coin}/8\n"
        f"  vp_markers: {veche.vp_markers}/8\n"
        f"  novgorod_conquered: {veche.novgorod_conquered}"
    )


def _render_deck(decks: Decks, side: str) -> str:
    if side == "teutonic":
        sd = decks.teutonic
    elif side == "russian":
        sd = decks.russian
    else:
        raise ValueError(f"deck side must be 'teutonic' or 'russian', got {side!r}")
    cards = load_cards()

    def label(card_id: str) -> str:
        c = cards.get(card_id, {})
        if c.get("no_event"):
            return f"{card_id} [No Event/No Capability]"
        ev = c.get("event_name") or "-"
        cap = c.get("capability_name") or "-"
        return f"{card_id} ({ev} | {cap})"

    lines = [f"Deck ({side}):"]
    lines.append(f"  draw pile ({len(sd.deck)}):")
    for cid in sd.deck:
        lines.append(f"    {label(cid)}")
    lines.append(f"  discard ({len(sd.discard)}):")
    for cid in sd.discard:
        lines.append(f"    {label(cid)}")
    lines.append(f"  removed from play ({len(sd.removed)}):")
    for cid in sd.removed:
        lines.append(f"    {label(cid)}")
    lines.append(f"  capabilities in play (side-wide, {len(sd.capabilities_in_play)}):")
    for cid in sd.capabilities_in_play:
        lines.append(f"    {label(cid)}")
    lines.append(f"  hold events ({len(sd.holds)}):")
    for cid in sd.holds:
        lines.append(f"    {label(cid)}")
    lines.append(f"  current Plan ({len(sd.plan)}):")
    for cid in sd.plan:
        lines.append(f"    {cid}")
    return "\n".join(lines)



def lord_combat_summary(state: GameState, lord_id: str) -> dict[str, Any]:
    """Compact per-Lord summary an LLM consumer can read instead of grepping
    static data + capability lookups. Includes effective Command, hit output
    by Strike step (Battle and Storm), Provender clock, and Service-disband box.

    Returns a dict; consumer can format as needed.
    """
    if lord_id not in state.lords:
        return {"error": f"unknown lord {lord_id}"}
    lord = state.lords[lord_id]
    if lord.state != "mustered":
        return {
            "lord_id": lord_id, "side": lord.side, "state": lord.state,
            "note": "Not Mustered; no combat summary available",
        }
    from nevsky.static_data import load_lords
    sl = load_lords()[lord_id]
    from nevsky.battle import _hits_for_lord_strike, _storm_hits_for_units
    from nevsky.campaign import _effective_command_rating

    # Battle strike hits per step (Lord's own Forces, default capabilities).
    battle_arch = _hits_for_lord_strike(state, lord_id, "archery")
    battle_melee_horse = _hits_for_lord_strike(state, lord_id, "melee_horse")
    battle_melee_foot = _hits_for_lord_strike(state, lord_id, "melee_foot")
    storm_arch = _storm_hits_for_units(lord.forces, "archery", in_storm=True)
    storm_melee = _storm_hits_for_units(lord.forces, "melee", in_storm=True)

    # Service-disband box.
    svc_box = None
    for cb in state.calendar.boxes:
        if lord_id in cb.service_markers:
            svc_box = cb.box
            break

    # Provender clock: 1 prov/Campaign for 1-6 units; 2 for 7+.
    units = sum(lord.forces.values())
    feed_cost = 2 if units >= 7 else 1

    return {
        "lord_id": lord_id,
        "side": lord.side,
        "location": lord.location,
        "in_stronghold": lord.in_stronghold,
        "ratings": {
            "command_base": int(sl["ratings"]["command"]),
            "command_effective": _effective_command_rating(state, lord_id),
            "lordship": int(sl["ratings"]["lordship"]),
            "lordship_used": lord.lordship_used,
            "service": int(sl["ratings"]["service"]),
            "fealty": sl["ratings"].get("fealty"),
        },
        "service_disband_box": svc_box,
        "forces": dict(lord.forces),
        "units_total": units,
        "feed_cost_prov": feed_cost,
        "assets": dict(lord.assets),
        "this_lord_capabilities": list(lord.this_lord_capabilities),
        "battle_strike_hits": {
            "archery": round(battle_arch, 2),
            "melee_horse": round(battle_melee_horse, 2),
            "melee_foot": round(battle_melee_foot, 2),
            "total_battle_melee": round(battle_melee_horse + battle_melee_foot, 2),
        },
        "storm_strike_hits": {
            "archery": round(storm_arch, 2),
            "melee_capped_at_6": round(min(6.0, storm_melee), 2),
            "melee_uncapped": round(storm_melee, 2),
        },
    }



def paths_from(
    state: GameState, from_locale: str, *, max_hops: int = 4,
    season: str | None = None, transport: str | None = None,
) -> dict[str, list[str]]:
    """Return shortest-Way paths from `from_locale` to every reachable Locale
    within `max_hops` hops.

    Result format: `{locale_id: [intermediate, ..., target]}` with the
    starting locale present as `from_locale: []`. Use len(path) as hop
    count.

    `season` and `transport` are accepted for API completeness but not
    used in the BFS (the harness doesn't currently filter Ways by
    season-availability or transport-type at the path-query level; the
    rules apply those constraints at cmd_march time). An LLM consumer
    can use these args to remember which season they're planning for.
    """
    from nevsky.static_data import load_ways
    ways = load_ways()
    adj: dict[str, list[tuple[str, str]]] = {}
    for w in ways:
        adj.setdefault(w["a"], []).append((w["b"], w.get("type", "?")))
        adj.setdefault(w["b"], []).append((w["a"], w.get("type", "?")))
    visited: dict[str, list[str]] = {from_locale: []}
    frontier = [from_locale]
    hops = 0
    while frontier and hops < max_hops:
        new_front = []
        for n in frontier:
            for m, way_type in adj.get(n, []):
                if m not in visited:
                    visited[m] = visited[n] + [m]
                    new_front.append(m)
        frontier = new_front
        hops += 1
    return visited


def lord_card_status(state: GameState, lord_id: str) -> dict[str, Any]:
    """Per-Lord activation-loop bookkeeping helper:

    Returns:
      {
        "lord_id": ...,
        "in_plan": bool,         # appears in this side's plan deck
        "in_plan_position": int | None,  # 0-indexed position if in plan
        "is_active": bool,       # currently active card_id == lord_id
        "actions_remaining": int,  # only meaningful when is_active
        "service_disband_box": int | None,  # Calendar box where this Lord disbands
        "is_besieged": bool,
        "is_mustered": bool,
      }
    """
    from nevsky.campaign import _is_besieged
    if lord_id not in state.lords:
        return {"error": f"unknown lord {lord_id}"}
    lord = state.lords[lord_id]
    deck = state.decks.teutonic if lord.side == "teutonic" else state.decks.russian
    plan = deck.plan
    in_plan = lord_id in plan
    in_plan_position = plan.index(lord_id) if in_plan else None
    is_active = state.campaign_turn.active_lord == lord_id
    actions = state.campaign_turn.actions_remaining if is_active else 0
    svc_box = None
    for cb in state.calendar.boxes:
        if lord_id in cb.service_markers:
            svc_box = cb.box
            break
    return {
        "lord_id": lord_id,
        "side": lord.side,
        "is_mustered": lord.state == "mustered",
        "is_besieged": _is_besieged(state, lord_id) if lord.state == "mustered" else False,
        "in_plan": in_plan,
        "in_plan_position": in_plan_position,
        "is_active": is_active,
        "actions_remaining": actions,
        "service_disband_box": svc_box,
    }



def state_view_for_side(state: GameState, side: Side) -> GameState:
    """Return a deep-copied GameState with opposing-side Lord details
    masked, when meta.optional_rules.hidden_mats is True (Rules of Play
    1.5.2). Otherwise returns a deep copy unchanged.

    Masked on opposing Lords:
      - forces (replaced with sentinel `{"_hidden": 1}` if non-empty)
      - routed_units (cleared)
      - assets (cleared)
      - this_lord_capabilities (cleared)
    Visible on opposing Lords:
      - lord_id, side, state, location, vassals (mustered status only)
    Masked on opposing deck:
      - pending_draw (replaced with `["<hidden>"] * n`)
      - Side-wide capabilities_in_play remain visible per 3.4.4.

    Use this view as input to render_summary, lord_combat_summary, etc.
    so the consumer operates within the fog-of-war consistently.
    """
    from copy import deepcopy
    s2 = deepcopy(state)
    if not s2.meta.optional_rules.get("hidden_mats", False):
        return s2
    other: Side = "russian" if side == "teutonic" else "teutonic"
    for lid, lord in s2.lords.items():
        if lord.side != other:
            continue
        if lord.state != "mustered":
            continue
        lord.forces = {"_hidden": 1} if lord.forces else {}
        lord.routed_units = {}
        lord.assets = {}
        lord.this_lord_capabilities = []
    opp_deck = s2.decks.teutonic if other == "teutonic" else s2.decks.russian
    if opp_deck.pending_draw:
        opp_deck.pending_draw = ["<hidden>"] * len(opp_deck.pending_draw)
    return s2


def render_summary_for_side(state: GameState, side: Side) -> str:
    """Render state from `side`'s perspective. When `hidden_mats` is
    active, opposing-side Lord-mat details are hidden via
    state_view_for_side. When the flag is OFF, returns the same as
    render_summary."""
    if not state.meta.optional_rules.get("hidden_mats", False):
        return render_summary(state)
    view = state_view_for_side(state, side)
    rendered = render_summary(view)
    return f"[VIEW: {side} (Hidden Mats active — opposing Lord details concealed)]\n" + rendered

