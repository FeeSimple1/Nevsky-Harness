"""Fresh compact briefings and on-demand detail from player-filtered state.

No change-only cache: every briefing is self-contained, including after load or
perspective switch. Descriptive compression only; no strategic move ranking.
"""
from __future__ import annotations

from nevsky.llm.action_browser import encode
from nevsky.llm.briefing import _cylinder_box_str, _season_for_box, _service_box_str
from nevsky.llm.view import view_for_side
from nevsky.static_data import load_cards, load_locales, load_lords, load_ways

TOPICS = ("state", "lord", "locale", "map", "supply", "cards", "card", "pending",
          "combat", "calendar", "victory", "rules", "history")


def player_view(state, side):
    """Use the existing card/history mask AND existing optional Hidden Mats mask."""
    if state.meta.optional_rules.get("hidden_mats"):
        from nevsky.render import state_view_for_side
        state = state_view_for_side(state, side)
    view = view_for_side(state, side)
    for pending in view["pending_decisions"]:
        if pending["owed_by"] != side:
            pending["context"] = {"visibility": "owner only"}
            pending["note"] = None
    return view


def victory_info(state):
    rules = state.meta.special_rules
    return {
        "points": {"teutonic": state.calendar.teutonic_vp,
                   "russian": state.calendar.russian_vp},
        "end_box": state.meta.span_end_box,
        "campaign_victory": "During Campaign, zero Mustered Lords on one side ends "
                            "the game immediately in favor of the other side (5.2).",
        "scenario_end": ("Teutons need at least 7 VP AND twice Russian VP; otherwise "
                         "Russians win (Watland)." if rules.get("victory_override") == "watland"
                         else "Higher VP wins; equal VP is a draw (5.3)."),
        "scoring": "1 VP per Conquered/Castle marker; 0.5 per Ravaged; Veche "
                   "Conquered markers count; 17.5 VP cap (5.1).",
        "pleskau_departure_bonus": bool(rules.get("victory_lord_removed_bonus")),
    }


def _piles(pile):
    return ",".join(f"{k}={v}" for k, v in pile.items()) or "none"


def _cards(ids, kind):
    cards = load_cards()
    return ";".join(f"{cid}={cards.get(cid, {}).get(kind + '_name', '?')}" for cid in ids) or "none"


def compact_briefing(state, side):
    """Fresh descriptive position; full fields are available through details()."""
    view = player_view(state, side)
    meta = view["meta"]
    step = meta["levy_step"] if meta["phase"] == "levy" else meta["campaign_step"]
    lines = [f"{meta['scenario_id']} | view={side} active={meta['active_player']} "
             f"{meta['phase']}/{step} | box {meta['box']} {_season_for_box(meta['box'])} "
             f"span {meta['span_start_box']}-{meta['span_end_box']}",
             f"VP T={view['calendar']['teutonic_vp']:g} R={view['calendar']['russian_vp']:g} "
             "(T=teutonic, R=russian)."]
    victory = victory_info(state)
    ending = ("Teutons need >=7 VP AND >=2x Russian VP; else Russians win"
              if meta["special_rules"].get("victory_override") == "watland"
              else "higher VP wins (tie=draw)")
    lines.append(f"Victory: at box {meta['span_end_box']} {ending}; during Campaign, "
                 "you win immediately if the opponent has zero Mustered Lords. VP cap=17.5.")
    if victory["pleskau_departure_bonus"]:
        lines.append("Pleskau: +1 VP per enemy Lord departing map; departures "
                     f"T={state.calendar.pleskau_lords_removed_teutonic} "
                     f"R={state.calendar.pleskau_lords_removed_russian}.")
    if not meta["first_levy_done"]:
        lines.append("First Levy: drawn cards are Capabilities, not Events (3.1.2).")
    enabled = {k: v for k, v in meta["optional_rules"].items() if v}
    if enabled:
        lines.append("Optional rules: " + encode(enabled))
    if meta["phase"] == "campaign":
        turn = view["campaign_turn"]
        # Absent ancillary fields have their explicit zero/false/empty defaults;
        # the active-card/budget/FPD fields are always shown, even when empty.
        essential = ("active_card", "active_lord", "next_to_reveal", "actions_remaining",
                     "in_feed_pay_disband", "fpd_pay_window_side")
        command = {k: v for k, v in turn.items() if k not in essential and v}
        lines.append(f"Command: card={turn['active_card']} lord={turn['active_lord']} "
                     f"next={turn['next_to_reveal']} actions_left={turn['actions_remaining']} "
                     f"Feed/Pay/Disband={turn['in_feed_pay_disband']} "
                     f"pay_window={turn['fpd_pay_window_side']} "
                     f"flags={encode(command)} (unlisted flags zero/false/empty).")
    else:
        lines.append("Muster order=" + encode(meta["muster_lord_order"]) +
                     " bonus=" + encode(meta["lordship_bonus"]) +
                     " blocked T=" + encode(meta["block_lords_this_levy_t"]) +
                     " R=" + encode(meta["block_lords_this_levy_r"]))
    static = load_lords()
    hidden = bool(meta["optional_rules"].get("hidden_mats"))
    lines.append("On-map Lords (Mustered unless labelled): Lord@locale | Service=position/rating | "
                 "Command | Lordship=used/printed+bonus | forces | assets | flags/Capabilities. "
                 "Unlisted flags false; vassals: details('lord',lord=...).")
    for owner in (side, "russian" if side == "teutonic" else "teutonic"):
        short = owner[0].upper()
        off = []
        for lid, mat in view["lords"].items():
            if mat["side"] != owner:
                continue
            if mat["location"] is None:
                cyl = _cylinder_box_str(state, lid).replace("box ", "").replace("(on map)", "none")
                off.append(f"{lid}:{mat['state']}@{cyl}")
                continue
            ratings = static[lid]["ratings"]
            flags = [k for k in ("in_stronghold", "moved_fought", "just_arrived_this_levy",
                                "first_march_used_this_card", "raiders_used_this_card") if mat[k]]
            service = _service_box_str(state, lid).replace("box ", "")
            line = (f"{short} {lid}@{mat['location']} | {service}/{ratings['service']} | "
                    f"{ratings['command']} | {mat['lordship_used']}/"
                    f"{ratings['lordship']}+{meta['lordship_bonus'].get(lid, 0)}")
            if mat["state"] != "mustered":
                line += f" state={mat['state']}"
            if hidden and owner != side:
                line += " | mat=<hidden> | mat=<hidden> |"
            else:
                line += f" | {_piles(mat['forces'])} | {_piles(mat['assets'])} |"
                if mat["routed_units"]:
                    line += " routed[" + _piles(mat["routed_units"]) + "]"
                if mat["this_lord_capabilities"]:
                    line += " Capabilities=" + _cards(mat["this_lord_capabilities"], "capability")
            if flags:
                line += " " + ",".join(flags)
            if mat["lieutenant_of"] or mat["has_lower_lord"]:
                line += f" lieutenant_of={mat['lieutenant_of']} lower={mat['has_lower_lord']}"
            lines.append(line)
        if off:
            lines.append(short + " off-map: " + ";".join(off))
        deck = view["decks"][owner]
        lines.append(f"{short} Capabilities=" + _cards(deck["capabilities_in_play"], "capability") +
                     f"; Events Levy={deck['this_levy_events']} Campaign={deck['this_campaign_events']}")
        if owner == side:
            lines.append("Own holds=" + _cards(deck["holds"], "event") +
                         f"; pending_draw={deck['pending_draw']} plan={deck['plan']}; "
                         f"draw/discard/removed counts={len(deck['deck'])}/"
                         f"{len(deck['discard'])}/{len(deck['removed'])}")
        else:
            lines.append(f"Opponent private counts: holds={len(deck['holds'])} "
                         f"pending_draw={len(deck['pending_draw'])} plan={len(deck['plan'])}")
    veche, legate = view["veche"], view["legate"]
    lines.append(f"Veche: Coin={veche['coin']} VP={veche['vp_markers']} "
                 f"acted={veche['acted_this_call_to_arms']} "
                 f"extra_muster={veche['extra_muster_target_lord']} "
                 f"Novgorod_conquered={veche['novgorod_conquered']}")
    if legate["william_of_modena_in_play"] or legate["extra_muster_target_lord"]:
        lines.append("Legate: " + encode(legate))
    else:
        lines.append(f"Legate not in play; acted={legate['acted_this_call_to_arms']}.")
    if view["combat_pending"]:
        lines.append("COMBAT PENDING: " + encode(view["combat_pending"]))
    if view["pending_decisions"]:
        lines.append("PENDING DECISIONS: " + encode(view["pending_decisions"]))
    else:
        lines.append("Pending decisions: none; phase/Command progression still applies.")
    aliases = {"teutonic_conquered": "T-conquered", "russian_conquered": "R-conquered",
               "teutonic_ravaged": "T-ravaged", "russian_ravaged": "R-ravaged",
               "teutonic_castle": "T-castle", "russian_castle": "R-castle",
               "walls_plus_one": "walls+1", "siege_markers": "siege"}
    markers = []
    for lid, locale in view["locales"].items():
        notable = [aliases.get(k, k) + (f"={v}" if type(v) is not bool else "")
                   for k, v in locale.items() if k != "locale_id" and v]
        if notable:
            markers.append(lid + ":" + ",".join(notable))
    lines.append("Map: " + ("; ".join(markers) or "no markers"))
    lines.append("Details: state/lord/locale/map/supply/cards/card/pending/combat/calendar/"
                 "victory/rules/history. Supply detail covers Famine, Seats and transport.")
    return "\n".join(lines)


def detail_payload(state, side, topic, *, lord=None, locale=None, card_id=None):
    view = player_view(state, side)
    if topic == "state":
        return view
    if topic == "lord":
        if lord not in view["lords"]:
            raise ValueError("specify lord= with a valid Lord ID")
        return {"state": view["lords"][lord], "printed": load_lords()[lord]}
    if topic == "locale":
        if locale not in view["locales"]:
            raise ValueError("specify locale= with a valid Locale ID")
        return {"state": view["locales"][locale], "printed": load_locales()[locale],
                "ways": [w for w in load_ways() if locale in (w["a"], w["b"])]}
    if topic == "map":
        return {"locales": view["locales"], "printed": load_locales(), "ways": load_ways()}
    if topic == "cards":
        return view["decks"]
    if topic == "card":
        from nevsky.llm.tools import lookup_aow_reference, lookup_card
        return {**lookup_card(card_id), "reference": lookup_aow_reference(card_id)}
    if topic == "pending":
        return {"decisions": view["pending_decisions"], "phase": view["meta"],
                "combat": view["combat_pending"], "command": view["campaign_turn"]}
    if topic in ("calendar", "history"):
        return view[topic]
    if topic == "combat":
        return {"combat": view["combat_pending"], "command": view["campaign_turn"]}
    if topic == "victory":
        return victory_info(state)
    if topic == "rules":
        return {"special_rules": view["meta"]["special_rules"],
                "optional_rules": view["meta"]["optional_rules"], "victory": victory_info(state),
                "references": "reference/; ACTIONS.md (parameter grammar); "
                              "lookup_aow_reference and lookup_strategy in nevsky.llm.tools"}
    if topic == "supply":
        from nevsky.campaign import _supply_seat_counts, _supply_transport_pool
        own = [lid for lid, mat in state.lords.items()
               if mat.side == side and mat.state == "mustered"]
        if lord is not None and lord not in own:
            raise ValueError("supply detail requires a Mustered Lord belonging to the perspective")
        targets = [lord] if lord else own
        return {"lords": {lid: {"location": state.lords[lid].location,
                                "assets": view["lords"][lid]["assets"],
                                "seats": _supply_seat_counts(state, lid),
                                "transport_pool_default": _supply_transport_pool(state, lid),
                                "capabilities": view["lords"][lid]["this_lord_capabilities"]}
                          for lid in targets},
                "season": _season_for_box(state.meta.box),
                "campaign": view["campaign_turn"],
                "events": {owner: view["decks"][owner]["this_campaign_events"]
                           for owner in ("teutonic", "russian")},
                "note": "Seats and default shared pool are not a certified Supply Route. "
                        "Use details('map')/details('locale', locale=...) for Ways and control; "
                        "actions('cmd_supply') preserves the full Route template. "
                        "Optional Lodya conversions and route_transports are handler-validated."}
    raise ValueError("unknown detail topic; choose " + ", ".join(TOPICS))
