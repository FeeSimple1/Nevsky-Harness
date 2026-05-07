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
    Lord,
    PendingDecision,
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


def render_summary(state: GameState) -> str:
    """Compact, LLM-budget-friendly view of game state."""
    lines: list[str] = []
    m = state.meta
    lines.append(
        f"{m.scenario_display_name} (box {m.box}/{m.span_end_box}, "
        f"{season(m.box)}, {m.phase}, {m.active_player or '-'} to act)"
    )
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
        lines.append(f"  off-left: {', '.join(state.calendar.off_left)}")
    if state.calendar.off_right:
        lines.append(f"  off-right: {', '.join(state.calendar.off_right)}")

    # Locale markers (only non-empty)
    map_lines = _summarize_locale_markers(state.locales)
    if map_lines:
        lines.append("Map markers:")
        lines.extend("  " + ml for ml in map_lines)

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
        lines.append(f"  off-left: {calendar.off_left}")
    if calendar.off_right:
        lines.append(f"  off-right: {calendar.off_right}")
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
