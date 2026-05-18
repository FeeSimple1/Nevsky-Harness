"""Curated natural-language briefing renderer.

The LLM gets a ~2-3 KB briefing per turn covering:
  - What phase + step the game is in
  - Whose turn it is (LLM's or opponent's)
  - The active Lord (if in Command phase mid-card)
  - Per-Lord summary: location, forces, assets, service marker box,
    capability tucked
  - VP track + scenario victory condition
  - Calendar position + box's season
  - Combat-pending state (if any) with key fields surfaced
  - Veche / Legate state (Russian / Teutonic CtA respectively)

The briefing is descriptive but NOT prescriptive — strategic
priors stay in the system prompt; the briefing is just state.
"""
from __future__ import annotations

from typing import Any

from nevsky.scenarios import determine_scenario_winner
from nevsky.static_data import load_lords


def _season_for_box(box: int) -> str:
    table = {
        1: "Summer", 2: "Summer",
        3: "Early Winter", 4: "Early Winter",
        5: "Late Winter", 6: "Late Winter",
        7: "Rasputitsa", 8: "Rasputitsa",
        9: "Summer", 10: "Summer",
        11: "Early Winter", 12: "Early Winter",
        13: "Late Winter", 14: "Late Winter",
        15: "Rasputitsa", 16: "Rasputitsa",
    }
    return table.get(box, "?")


def _service_box_str(state, lord_id: str) -> str:
    cal = state.calendar
    if lord_id in cal.off_left_service:
        return "off-left"
    if lord_id in cal.off_right_service:
        return "off-right"
    for cb in cal.boxes:
        if lord_id in cb.service_markers:
            return f"box {cb.box}"
    return "not on Calendar"


def _cylinder_box_str(state, lord_id: str) -> str:
    cal = state.calendar
    if lord_id in cal.off_left:
        return "off-left"
    if lord_id in cal.off_right:
        return "off-right"
    for cb in cal.boxes:
        if lord_id in cb.cylinders:
            return f"box {cb.box}"
    return "(on map)"


def briefing_for_side(state, side: str) -> str:
    """Generate the per-turn LLM briefing string."""
    lines = []
    other = "russian" if side == "teutonic" else "teutonic"
    sl = load_lords()

    # Header
    lines.append(f"# Nevsky game state — you play {side.upper()}")
    lines.append(f"")
    lines.append(f"Scenario: {state.meta.scenario_id}  Seed: {state.meta.seed}  "
                 f"Calendar box: {state.meta.box} ({_season_for_box(state.meta.box)})")
    lines.append(f"Span: box {state.meta.span_start_box} → {state.meta.span_end_box}")

    # Phase
    lines.append(f"")
    lines.append(f"## Phase")
    if state.meta.phase == "levy":
        step = state.meta.levy_step
        active = state.meta.active_player
        lines.append(f"Levy phase, step **{step}**, active player **{active}**.")
        if state.meta.first_levy_done is False:
            lines.append("This is the FIRST Levy (3.1.2): drawn AoW cards "
                          "are implemented as Capabilities, not Events.")
    elif state.meta.phase == "campaign":
        cstep = state.meta.campaign_step
        active = state.meta.active_player
        lines.append(f"Campaign phase, step **{cstep}**, active player **{active}**.")
        if cstep == "command":
            cl = state.campaign_turn.active_lord
            ac = state.campaign_turn.actions_remaining
            in_fpd = state.campaign_turn.in_feed_pay_disband
            if in_fpd:
                lines.append("In Feed/Pay/Disband sub-step.")
            elif cl:
                lines.append(f"Active card: **{cl}**, actions remaining: {ac}.")
            else:
                lines.append(f"Waiting to reveal next Command card "
                             f"(next reveal: {state.campaign_turn.next_to_reveal}).")
            if state.combat_pending is not None:
                cp = state.combat_pending
                lines.append(f"")
                lines.append(f"### COMBAT PENDING")
                lines.append(f"Attacker: {cp.attacker_side} from {cp.from_locale} via "
                             f"{cp.way_type} to {cp.to_locale}.")
                lines.append(f"Attacker group: {cp.attacker_group}.")
                lines.append(f"Defender side: {cp.defender_side}, defenders: {cp.defender_lords}.")
                lines.append(f"Response owed by: **{cp.pending_response_by}** "
                             f"(options: avoid_battle / withdraw / stand_battle).")
                if cp.ambush_block_pending:
                    lines.append(f"AMBUSH BLOCK INTERRUPT: attacker has T6/R6 Ambush in holds; "
                                 f"play_ambush_block or decline_ambush_block.")
    else:
        lines.append(f"Phase: {state.meta.phase}")

    # VP
    lines.append(f"")
    lines.append(f"## Victory Points")
    lines.append(f"Teutonic: {state.calendar.teutonic_vp:.1f}  "
                 f"Russian: {state.calendar.russian_vp:.1f}")
    if state.meta.special_rules.get("victory_override") == "watland":
        lines.append("Watland override: Teutons need ≥7 VP AND ≥2× Russian VP.")
    if state.meta.special_rules.get("victory_lord_removed_bonus"):
        lines.append("Pleskau bonus: +1 VP per enemy Lord removed "
                     f"(T removed by R: {state.calendar.pleskau_lords_removed_teutonic}, "
                     f"R removed by T: {state.calendar.pleskau_lords_removed_russian}).")

    # Your Lords
    lines.append(f"")
    lines.append(f"## Your Lords ({side})")
    for lid, lord in state.lords.items():
        if lord.side != side:
            continue
        srating = int(sl[lid]["ratings"]["service"])
        cmd = int(sl[lid]["ratings"]["command"])
        lord_rating = int(sl[lid]["ratings"]["lordship"])
        loc_str = lord.location if lord.location else "(off-board)"
        cyl_str = _cylinder_box_str(state, lid)
        svc_str = _service_box_str(state, lid)
        caps = lord.this_lord_capabilities
        caps_str = (", " + ", ".join(caps)) if caps else ""
        forces_str = ", ".join(f"{u}×{n}" for u, n in lord.forces.items() if n > 0)
        assets_str = ", ".join(f"{a}×{n}" for a, n in lord.assets.items() if n > 0)
        lines.append(f"- **{lid}** [{lord.state}]: at {loc_str}{caps_str}")
        lines.append(f"    cmd {cmd}, lordship {lord_rating}, service {srating}; "
                     f"cylinder {cyl_str}, service marker {svc_str}")
        if forces_str:
            lines.append(f"    forces: {forces_str}")
        if assets_str:
            lines.append(f"    assets: {assets_str}")
        if lord.routed_units:
            r = ", ".join(f"{u}×{n}" for u, n in lord.routed_units.items() if n > 0)
            lines.append(f"    routed (await Losses roll): {r}")
        if lord.lieutenant_of:
            lines.append(f"    Lower Lord under {lord.lieutenant_of}")
        if lord.has_lower_lord:
            lines.append(f"    Lieutenant of {lord.has_lower_lord}")

    # Opponent Lords (public info only)
    lines.append(f"")
    lines.append(f"## Opponent Lords ({other})")
    for lid, lord in state.lords.items():
        if lord.side != other:
            continue
        srating = int(sl[lid]["ratings"]["service"])
        cmd = int(sl[lid]["ratings"]["command"])
        loc_str = lord.location if lord.location else "(off-board)"
        cyl_str = _cylinder_box_str(state, lid)
        svc_str = _service_box_str(state, lid)
        caps = lord.this_lord_capabilities  # public — tucked face-up
        caps_str = (", " + ", ".join(caps)) if caps else ""
        forces_str = ", ".join(f"{u}×{n}" for u, n in lord.forces.items() if n > 0)
        lines.append(f"- **{lid}** [{lord.state}]: at {loc_str}{caps_str}")
        lines.append(f"    cmd {cmd}, service {srating}; cylinder {cyl_str}, "
                     f"service marker {svc_str}")
        if forces_str:
            lines.append(f"    forces: {forces_str}")

    # Own deck
    own_deck = state.decks.teutonic if side == "teutonic" else state.decks.russian
    lines.append(f"")
    lines.append(f"## Your AoW deck")
    lines.append(f"deck: {len(own_deck.deck)} cards  discard: {len(own_deck.discard)} cards  "
                 f"removed: {len(own_deck.removed)} cards")
    if own_deck.pending_draw:
        lines.append(f"PENDING DRAW: {own_deck.pending_draw}")
    if own_deck.holds:
        lines.append(f"holds: {own_deck.holds}")
    if own_deck.capabilities_in_play:
        lines.append(f"side capabilities in play: {own_deck.capabilities_in_play}")
    if own_deck.this_levy_events:
        lines.append(f"this-Levy events: {own_deck.this_levy_events}")
    if own_deck.this_campaign_events:
        lines.append(f"this-Campaign events: {own_deck.this_campaign_events}")
    if own_deck.plan:
        lines.append(f"plan stack ({len(own_deck.plan)} cards): {own_deck.plan}")

    # Opponent's PUBLIC deck info (capabilities only)
    other_deck = state.decks.teutonic if other == "teutonic" else state.decks.russian
    lines.append(f"")
    lines.append(f"## Opponent deck (public info only)")
    lines.append(f"side capabilities in play: {other_deck.capabilities_in_play}")
    lines.append(f"this-Campaign events: {other_deck.this_campaign_events}")
    lines.append(f"opponent hold/draw/plan counts: holds={len(other_deck.holds)} "
                 f"pending_draw={len(other_deck.pending_draw)} plan={len(other_deck.plan)}")

    # Veche / Legate
    lines.append(f"")
    lines.append(f"## Veche")
    lines.append(f"VP markers: {state.veche.vp_markers}  Coin: {state.veche.coin}  "
                 f"acted this CtA: {state.veche.acted_this_call_to_arms}")
    lines.append(f"")
    lines.append(f"## Legate (William of Modena)")
    if state.legate.william_of_modena_in_play:
        lines.append(f"In play. Pawn at: "
                     f"{state.legate.locale_id if state.legate.location == 'locale' else 'on card'}. "
                     f"acted this CtA: {state.legate.acted_this_call_to_arms}.")
    else:
        lines.append("NOT in play (T13 William of Modena not Levied yet, or discarded).")

    # Key locale flags (Conquered / Ravaged / Castle / siege)
    lines.append(f"")
    lines.append(f"## Locale notes")
    notable = []
    for lid, loc in state.locales.items():
        markers = []
        if loc.russian_conquered > 0:
            markers.append(f"R-conq×{loc.russian_conquered}")
        if loc.teutonic_conquered > 0:
            markers.append(f"T-conq×{loc.teutonic_conquered}")
        if loc.russian_castle:
            markers.append("R-castle")
        if loc.teutonic_castle:
            markers.append("T-castle")
        if loc.walls_plus_one:
            markers.append("walls+1")
        if loc.russian_ravaged:
            markers.append("R-ravaged")
        if loc.teutonic_ravaged:
            markers.append("T-ravaged")
        if loc.siege_markers > 0:
            markers.append(f"siege×{loc.siege_markers}")
        if markers:
            notable.append(f"  {lid}: {', '.join(markers)}")
    if notable:
        lines.extend(notable)
    else:
        lines.append("  (no special markers placed yet)")

    return "\n".join(lines)
