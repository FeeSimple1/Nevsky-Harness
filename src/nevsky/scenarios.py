"""Scenario loader.

Two entry points:

- `load_scenario_raw(scenario_id)` returns the parsed scenario JSON
  dict without further processing. Used by Phase 0 smoke tests and as
  the input to the state-building loader.

- `load_scenario(scenario_id, seed=...)` returns a fully populated
  GameState ready to play: Lords mustered/ready/removed per the
  scenario, Locales with starting markers, Calendar with cylinders /
  Service markers / Levy/Campaign marker / Victory markers, Veche
  contents, Decks built per side with No-Event handling per scenario,
  Legate not-in-play.

Open question (Q-001 in RULES_QUESTIONS.md): how to resolve "Transport
(any)" starting-asset choices that the rules leave to the player at
setup. Phase 1 captures unresolved choices as PendingDecision entries
and does not pre-pick a Transport type; Phase 2 (Levy mechanics) wires
up the resolution flow.
"""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

from nevsky import SCHEMA_VERSION
from nevsky.state import (
    Calendar,
    CalendarBox,
    Decks,
    GameState,
    Legate,
    Locale,
    Lord,
    Meta,
    PendingDecision,
    SideDeck,
    VassalState,
    Veche,
)
from nevsky.static_data import load_cards, load_locales, load_lords

SCENARIO_IDS: tuple[str, ...] = (
    "pleskau",
    "watland",
    "return_of_the_prince",
    "return_of_the_prince_nicolle",
    "peipus",
    "crusade_on_novgorod",
    "quickstart",
)


def load_scenario_raw(scenario_id: str) -> dict[str, Any]:
    """Load and parse a scenario JSON file by id (no processing)."""
    if scenario_id not in SCENARIO_IDS:
        raise ValueError(
            f"unknown scenario id: {scenario_id!r}. "
            f"known ids: {', '.join(SCENARIO_IDS)}"
        )
    package = "nevsky.data.scenarios"
    filename = f"{scenario_id}.json"
    text = resources.files(package).joinpath(filename).read_text(encoding="utf-8")
    return json.loads(text)


# ---------------------------------------------------------------------------
# State builder
# ---------------------------------------------------------------------------


# Per-scenario / lord / slot Transport defaults per Q-001 decision
# (RULES_DECISIONS.md). Values are lists of strings (one per slot) drawn
# from {"boat","cart","sled","ship"}. Order matches the slot index in
# lords.json starting_transport_choice. Slots not listed here use the
# loader's general heuristic (fallback to first allowed option).
_Q001_DEFAULTS: dict[str, dict[str, list[str]]] = {
    "pleskau": {
        "gavrilo":   ["cart"],
        "vladislav": ["boat"],
    },
    "watland": {
        "andreas":   ["sled", "sled"],
        "domash":    ["sled"],
        "vladislav": ["sled"],
    },
    "return_of_the_prince": {
        "andreas":   ["ship", "cart"],
        "aleksandr": ["boat", "cart"],
    },
    "return_of_the_prince_nicolle": {
        "andreas":   ["ship", "cart"],
        "aleksandr": ["boat", "cart"],
        "gavrilo":   ["cart"],
    },
    "peipus": {
        "aleksandr": ["sled", "sled"],
        "andrey":    ["sled", "sled"],
        "domash":    ["sled"],
        "karelians": ["sled"],
    },
    "crusade_on_novgorod": {
        "gavrilo":   ["cart"],
        "vladislav": ["boat"],
    },
}

# Player-prompt hotspots: scenario_id -> set of lord_ids whose
# default the harness should NOT silently auto-confirm. The loader
# emits the PendingDecision exactly the same way; this set is used
# by the auto-confirm hook to decide which decisions persist past
# the first Levy action.
_Q001_NO_AUTO_CONFIRM: dict[str, set[str]] = {
    "pleskau": {"vladislav"},
    "crusade_on_novgorod": {"vladislav"},
    "return_of_the_prince": {"aleksandr"},
    "return_of_the_prince_nicolle": {"aleksandr"},
}


class ScenarioPlaceholderError(ValueError):
    """Raised when load_scenario is called on a placeholder scenario."""


def load_scenario(scenario_id: str, seed: int = 0) -> GameState:
    """Build a fully populated GameState from a scenario id."""
    raw = load_scenario_raw(scenario_id)
    if raw.get("status") == "placeholder":
        raise ScenarioPlaceholderError(
            f"scenario {scenario_id!r} is a placeholder: "
            f"{raw.get('notes', 'setup not yet authored')}"
        )

    setup = raw.get("setup", {})
    static_lords = load_lords()
    static_locales = load_locales()

    meta = _build_meta(raw, scenario_id, seed)
    veche = _build_veche(setup)
    locales = _build_locales(setup, static_locales)
    lords, pending = _build_lords(scenario_id, setup, static_lords)
    calendar = _build_calendar(setup)
    decks = _build_decks(raw, setup)
    legate = Legate(william_of_modena_in_play=False, location="card", locale_id=None)

    russian_vp = _compute_vp("russian", locales, veche)
    teutonic_vp = _compute_vp("teutonic", locales, veche)
    calendar.russian_vp = russian_vp
    calendar.teutonic_vp = teutonic_vp
    _set_victory_markers(calendar, russian_vp, teutonic_vp)

    return GameState(
        meta=meta,
        calendar=calendar,
        veche=veche,
        lords=lords,
        locales=locales,
        decks=decks,
        legate=legate,
        pending_decisions=pending,
        history=[],
    )


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _build_meta(raw: dict[str, Any], scenario_id: str, seed: int) -> Meta:
    span = raw.get("span", {})
    start_box = int(span.get("start_box", 1))
    return Meta(
        scenario_id=scenario_id,
        scenario_display_name=raw.get("display_name", scenario_id),
        edition="2",
        schema_version=SCHEMA_VERSION,
        seed=seed,
        sequence=0,
        box=start_box,
        phase="levy",
        active_player="teutonic",  # default Levy order T-then-R (Sequence of Play 2.2.4).
        span_start_box=start_box,
        span_end_box=int(span.get("end_box", 16)),
        aggressor=raw.get("aggressor", "teutonic"),
        special_rules=dict(raw.get("special_rules", {})),
    )


def _build_veche(setup: dict[str, Any]) -> Veche:
    v = setup.get("veche", {})
    return Veche(
        coin=int(v.get("coin", 0)),
        vp_markers=int(v.get("vp_markers", 0)),
        novgorod_conquered=False,
    )


def _build_locales(setup: dict[str, Any], static_locales: dict[str, dict]) -> dict[str, Locale]:
    locales: dict[str, Locale] = {lid: Locale(locale_id=lid) for lid in static_locales}
    for marker in setup.get("markers_on_map", []):
        lid = marker["locale_id"]
        if lid not in locales:
            raise ValueError(f"scenario references unknown locale {lid!r}")
        loc = locales[lid]
        side = marker["side"]
        kind = marker["marker_type"]
        count = int(marker.get("count", 1))
        if kind == "conquered":
            if side == "russian":
                loc.russian_conquered += count
            else:
                loc.teutonic_conquered += count
        elif kind == "ravaged":
            if side == "russian":
                loc.russian_ravaged = True
            else:
                loc.teutonic_ravaged = True
        elif kind == "castle":
            if side == "russian":
                loc.russian_castle = True
            else:
                loc.teutonic_castle = True
        elif kind == "walls_plus_one":
            loc.walls_plus_one = True
        elif kind == "siege":
            loc.siege_markers = max(loc.siege_markers, count)
        else:
            raise ValueError(f"unknown marker_type {kind!r} at {lid!r}")
    return locales


def _build_lords(
    scenario_id: str,
    setup: dict[str, Any],
    static_lords: dict[str, dict],
) -> tuple[dict[str, Lord], list[PendingDecision]]:
    """Build the Lord dict.

    For each Lord in static data:
      - If listed in setup.removed_from_play -> state="removed", no
        forces / assets / vassals deployed.
      - If listed in setup.mustered_lords -> state="mustered" with
        starting forces / assets / Vassals (face-up) at the specified
        locale.
      - Otherwise -> state="ready" with cylinder available for Levy;
        forces and assets are zero (deployed at Muster, Phase 2).

    Pending transport-choice decisions are captured for any Mustered
    Lord whose starting transports include "any" slots (Q-001).
    """
    mustered_index = {m["lord_id"]: m for m in setup.get("mustered_lords", [])}
    removed_set = set(setup.get("removed_from_play", []))

    lords: dict[str, Lord] = {}
    pending: list[PendingDecision] = []

    for lord_id, sl in static_lords.items():
        side = sl["side"]
        if lord_id in removed_set:
            lords[lord_id] = Lord(
                lord_id=lord_id,
                side=side,
                location=None,
                state="removed",
                forces={},
                assets={},
                vassals={},
                this_lord_capabilities=[],
            )
            continue

        if lord_id in mustered_index:
            mreq = mustered_index[lord_id]
            location = mreq["locale_id"]
            forces = {k: int(v) for k, v in sl["starting_forces"].items() if int(v) != 0}
            assets = {k: int(v) for k, v in sl["starting_assets"].items() if int(v) != 0}
            vassals = _build_vassals_for_lord(sl, mustered=True)
            lords[lord_id] = Lord(
                lord_id=lord_id,
                side=side,
                location=location,
                state="mustered",
                forces=forces,
                assets=assets,
                vassals=vassals,
                this_lord_capabilities=[],
            )
            # Q-001: apply per-scenario/lord defaults; populate Lord.assets
            # with the chosen Transport pieces and emit a PendingDecision
            # per slot with default_value/current_value pre-populated.
            scenario_defaults = _Q001_DEFAULTS.get(scenario_id, {}).get(lord_id, [])
            no_auto = lord_id in _Q001_NO_AUTO_CONFIRM.get(scenario_id, set())
            slot_idx_global = 0
            for slot in sl.get("starting_transport_choice", []):
                allowed = list(slot["options"])
                # If the Lord is Ships-authorized but "ship" is not in
                # the JSON options, fall back to allowed as-is. The
                # defaults table is authoritative.
                count = int(slot["count"])
                for sub_idx in range(count):
                    if slot_idx_global < len(scenario_defaults):
                        chosen = scenario_defaults[slot_idx_global]
                    else:
                        # Fallback heuristic: pick first option.
                        chosen = allowed[0]
                    if chosen not in allowed:
                        # Hard-coded default not in JSON options; trust
                        # the table (Q-001 spec is authoritative).
                        pass
                    # Apply: increment Lord.assets[chosen].
                    lords[lord_id].assets[chosen] = lords[lord_id].assets.get(chosen, 0) + 1  # type: ignore[index]
                    pending.append(
                        PendingDecision(
                            kind="setup_transport_choice",
                            owed_by=side,
                            context={
                                "lord_id": lord_id,
                                "slot_index": slot_idx_global,
                                "default_value": chosen,
                                "current_value": chosen,
                                "allowed_values": allowed,
                                "auto_confirm_on_levy": not no_auto,
                                "resolved": False,
                            },
                            note=(
                                f"{lord_id} starts with Transport (any) slot {slot_idx_global}; "
                                f"default = {chosen} (Q-001). "
                                + ("Player MUST confirm or override before Levy." if no_auto
                                   else "Auto-confirms at first Levy action.")
                            ),
                        )
                    )
                    slot_idx_global += 1
        else:
            lords[lord_id] = Lord(
                lord_id=lord_id,
                side=side,
                location=None,
                state="ready",
                forces={},
                assets={},
                vassals=_build_vassals_for_lord(sl, mustered=False),
                this_lord_capabilities=[],
            )
    return lords, pending


def _build_vassals_for_lord(sl: dict[str, Any], mustered: bool) -> dict[str, VassalState]:
    """Vassal markers face up on mat (CoA-up = ready), Forces not yet
    deployed (mustered=False on each Vassal). Special Vassals start
    not-ready since their gating Capability is not yet in play.

    `mustered` parameter is the LORD's mustered state, not the Vassal's;
    Vassals are never auto-mustered with the Lord — they require a
    Muster Vassal action in Levy (3.4.2). For ready vs not-ready Lords
    we still create the VassalState entries so the data is consistent;
    the harness uses the Lord's state to decide whether Vassal mechanics
    apply at this moment.
    """
    out: dict[str, VassalState] = {}
    for v in sl.get("vassals", []):
        out[v["vassal_id"]] = VassalState(
            vassal_id=v["vassal_id"],
            ready=(v.get("special") is None),
            mustered=False,
            on_calendar=False,
            calendar_box=None,
        )
    return out


def _build_calendar(setup: dict[str, Any]) -> Calendar:
    boxes = [CalendarBox(box=i) for i in range(1, 17)]
    for entry in setup.get("calendar", []):
        b = int(entry["box"])
        if not 1 <= b <= 16:
            raise ValueError(f"calendar entry box out of range: {b}")
        cb = boxes[b - 1]
        for cyl in entry.get("cylinders", []):
            cb.cylinders.append(cyl)
        for sm in entry.get("service_markers", []):
            cb.service_markers.append(sm)
        for vsm in entry.get("vassal_service_markers", []):
            cb.vassal_service_markers.append(vsm)
        if entry.get("levy_campaign_marker") is not None:
            cb.has_levy_campaign_marker = True
            cb.levy_campaign_face = entry["levy_campaign_marker"]
    return Calendar(
        boxes=boxes,
        off_left=list(setup.get("calendar_off_left", [])),
        off_right=list(setup.get("calendar_off_right", [])),
    )


def _build_decks(raw: dict[str, Any], setup: dict[str, Any]) -> Decks:
    """Build per-side AoW decks.

    Standard: deck = all 18 numbered cards + 3 No-Event cards. The 3
    No-Event cards are removed from play permanently when drawn during
    Levy (rule 3.1.3, 2E).

    Pleskau special: remove all No-Event cards before play (rule 6.0,
    Pleskau Special Rule) -- they go to `removed`, not the deck.

    Crusade on Novgorod special: keep No-Event cards in deck even when
    drawn (the deck retains them, no removal-on-draw); the 3.1.3
    permanent-removal rule is suspended.

    The deck is left in a pre-shuffle order; the harness reorders at
    each Levy's Arts of War step (3.1.1) using the seeded RNG.
    """
    cards = load_cards()
    special_rules = raw.get("special_rules", {})
    pleskau_pre_remove = bool(special_rules.get("remove_no_event_cards_before_play"))

    teu_deck: list[str] = []
    teu_removed: list[str] = []
    rus_deck: list[str] = []
    rus_removed: list[str] = []
    for cid, card in cards.items():
        if card["side"] == "teutonic":
            if card["no_event"] and pleskau_pre_remove:
                teu_removed.append(cid)
            else:
                teu_deck.append(cid)
        else:
            if card["no_event"] and pleskau_pre_remove:
                rus_removed.append(cid)
            else:
                rus_deck.append(cid)

    return Decks(
        teutonic=SideDeck(deck=sorted(teu_deck), removed=sorted(teu_removed)),
        russian=SideDeck(deck=sorted(rus_deck), removed=sorted(rus_removed)),
    )


# ---------------------------------------------------------------------------
# Victory point computation
# ---------------------------------------------------------------------------


def _compute_vp(side: str, locales: dict[str, Locale], veche: Veche) -> float:
    """Total VP for `side` from on-map markers + Veche (Russian only).

    VP scoring per scenario reference:
      - 1 VP per Conquered marker of your color on the map.
      - 1 VP per Castle marker of your color on the map.
      - 1/2 VP per Ravaged marker of your color on the map.
      - PLESKAU only: +1 VP per enemy Lord removed from the map by any
        means. (Pleskau bonus is applied via Calendar.pleskau_lords_
        removed_* counters, which are zero at scenario start.)
      - Russian total includes Veche white VP markers.

    Cap of 17.5 (rule 5.3) is NOT applied here -- the cap applies only
    at scoring time. Calendar VP track display uses min(VP, 16) for box.
    """
    total = 0.0
    for loc in locales.values():
        if side == "russian":
            total += loc.russian_conquered  # 1 each
            total += 1.0 if loc.russian_castle else 0.0
            total += 0.5 if loc.russian_ravaged else 0.0
        else:
            total += loc.teutonic_conquered
            total += 1.0 if loc.teutonic_castle else 0.0
            total += 0.5 if loc.teutonic_ravaged else 0.0
    if side == "russian":
        total += float(veche.vp_markers)
    return total


def _set_victory_markers(calendar: Calendar, russian_vp: float, teutonic_vp: float) -> None:
    """Place each side's Calendar Victory marker.

    Box position = floor(VP), clamped to 1..16. Zero-VP totals leave the
    marker off Calendar (no box flagged). Half-VPs are tracked as the
    fractional portion of `russian_vp`/`teutonic_vp` on Calendar; the
    physical Victory marker has a "+1/2" face used at the box position.
    Phase 1 records the per-box bool only; the +1/2 indicator is
    derivable from the total. (No-marker for 0 VP is the convention used
    by the scenario reference's example setups.)
    """

    def place(side: str, vp: float) -> None:
        if vp < 1.0:
            return
        b = min(16, int(vp))
        if side == "russian":
            calendar.boxes[b - 1].russian_victory_marker = True
        else:
            calendar.boxes[b - 1].teutonic_victory_marker = True

    place("russian", russian_vp)
    place("teutonic", teutonic_vp)
