"""Event resolvers (per-card Arts of War effects).

Tier 1 immediate events: calendar shifts, Asset/Ravaged manipulation,
this-levy blocks, the Lordship +2 hold mechanic. Resolved via
resolve_immediate_event / resolve_hold_event.

Tier 2 battle Hold events (Bridge T4 / R1, Marsh T5 / R2, Ambush
T6 / R6, Hill T9 / R5, Field Organ T10, Raven's Rock R4) are
consumed via _consume_battle_holds at Battle invocation time and
applied as modifiers inside battle.py.

Tier 3 hold events with non-Battle effects (T3 Vodian Treachery,
T13 Heinrich Sees the Curia, R3 Pogost) resolve via dedicated
handlers below.

Events whose resolver is not yet wired up return a `deferred: True`
placeholder; callers can detect this and fall back to manual play
of the card text.

Each resolver mutates state in place and returns a result dict or
raises IllegalAction on missing/invalid args. Resolvers do NOT
discard the card themselves (the caller in actions.py decides
whether the card goes to discard / removed / stays in holds).

API:
  resolve_immediate_event(state, card_id, args) -> dict
  resolve_hold_event(state, card_id, args) -> dict
  apply_lordship_plus_2(state, card_id, lord_id) -> dict
"""

from __future__ import annotations

from typing import Any

from nevsky.actions import IllegalAction, _shift_service_right
from nevsky.state import GameState
from nevsky.static_data import load_locales, load_lords


def _shift_cylinder(state: GameState, lord_id: str, boxes: int, direction: str) -> int:
    """Shift `lord_id` cylinder by `boxes` in `direction` ('left'|'right').

    Returns the resulting box (1..16, or 0/17 for off-edges)."""
    cal = state.calendar
    # Find current position.
    cur = None
    if lord_id in cal.off_left:
        cur = 0
        cal.off_left.remove(lord_id)
    elif lord_id in cal.off_right:
        cur = 17
        cal.off_right.remove(lord_id)
    else:
        for cb in cal.boxes:
            if lord_id in cb.cylinders:
                cur = cb.box
                cb.cylinders.remove(lord_id)
                break
    if cur is None:
        raise IllegalAction("no_cylinder", f"{lord_id} cylinder not on Calendar")
    if direction == "left":
        new = cur - boxes
    else:
        new = cur + boxes
    if new < 1:
        cal.off_left.append(lord_id)
        return 0
    if new > 16:
        cal.off_right.append(lord_id)
        return 17
    cal.boxes[new - 1].cylinders.append(lord_id)
    return new


def _shift_service(state: GameState, lord_id: str, boxes: int, direction: str) -> int:
    """Shift a Service marker by `boxes` in `direction`. Returns the
    resulting box (1..16, or 0/17 for off-edges).

    SMOKE-062 (Round 68): per AoW Reference R10/T12/T18 Tips —
    "Shifting just one box off the Calendar from box 1 or box 16 is
    allowed" — the function supports landing on off_left_service
    (0) and off_right_service (17). Prior code clamped at box 1 on
    left-shifts via max(1, cur - boxes), which silently disallowed
    legal off-Calendar service shifts.
    """
    cal = state.calendar
    cur = None
    if lord_id in cal.off_right_service:
        cur = 17
        cal.off_right_service.remove(lord_id)
    elif lord_id in cal.off_left_service:
        cur = 0
        cal.off_left_service.remove(lord_id)
    else:
        for cb in cal.boxes:
            if lord_id in cb.service_markers:
                cur = cb.box
                cb.service_markers.remove(lord_id)
                break
    if cur is None:
        raise IllegalAction("no_service_marker", f"{lord_id} has no Service marker")
    if direction == "left":
        new = cur - boxes
        if new < 1:
            # Clamp at off_left_service (one box off Calendar max).
            cal.off_left_service.append(lord_id)
            return 0
    else:
        new = cur + boxes
        if new > 16:
            cal.off_right_service.append(lord_id)
            return 17
    cal.boxes[new - 1].service_markers.append(lord_id)
    return new


# ---------------------------------------------------------------------------
# Immediate events
# ---------------------------------------------------------------------------


def _ev_grand_prince(state: GameState, args: dict[str, Any]) -> dict[str, Any]:
    """T1 Grand Prince favors a son (immediate). Teuton choice.

    args:
      target: "aleksandr" | "andrey" | "service:aleksandr" | "service:andrey"
      direction: "left" | "right"
    Shift 2 boxes.
    """
    target = args.get("target")
    direction = args.get("direction", "left")
    if target not in ("aleksandr", "andrey", "service:aleksandr", "service:andrey"):
        raise IllegalAction("missing_arg", "args.target required for T1")
    if direction not in ("left", "right"):
        raise IllegalAction("bad_direction", "direction must be left or right")
    if target.startswith("service:"):
        lid = target.split(":", 1)[1]
        new = _shift_service(state, lid, 2, direction)
        return {"event": "T1", "target": target, "new_box": new}
    new = _shift_cylinder(state, target, 2, direction)
    return {"event": "T1", "target": target, "new_box": new}


def _ev_torzhok(state: GameState, args: dict[str, Any]) -> dict[str, Any]:
    """T2 Torzhok: remove 3 Assets from Domash OR 3 Coin from Veche. Teuton choice.

    args:
      target: "domash" | "veche"
      assets: list[str] (only when target=domash; up to 3 asset types in any combination)
    """
    target = args.get("target")
    if target == "veche":
        amt = min(3, state.veche.coin)
        state.veche.coin -= amt
        return {"event": "T2", "target": "veche", "coin_removed": amt}
    if target == "domash":
        if "domash" not in state.lords:
            raise IllegalAction("no_target", "domash not in state")
        d = state.lords["domash"]
        order = args.get("asset_order", ["coin", "loot", "provender", "boat", "cart", "sled"])
        removed: dict[str, int] = {}
        n = 3
        for k in order:
            if n <= 0:
                break
            have = d.assets.get(k, 0)
            take = min(have, n)
            if take > 0:
                d.assets[k] = have - take
                if d.assets[k] == 0:
                    del d.assets[k]
                removed[k] = take
                n -= take
        return {"event": "T2", "target": "domash", "removed": removed}
    raise IllegalAction("missing_arg", "args.target must be 'domash' or 'veche'")


def _ev_pope_gregory(state: GameState, args: dict[str, Any]) -> dict[str, Any]:
    """T11 Pope Gregory issues indulgences (immediate, side-wide capability + event).
    Shift 1 Teuton cylinder 1 box LEFT and add Crusade card to capabilities_in_play.
    """
    target = args.get("target")
    if not isinstance(target, str) or target not in state.lords or state.lords[target].side != "teutonic":
        raise IllegalAction("missing_arg", "args.target Teutonic lord_id required for T11")
    new = _shift_cylinder(state, target, 1, "left")
    if "T11" not in state.decks.teutonic.capabilities_in_play:
        state.decks.teutonic.capabilities_in_play.append("T11")
    return {"event": "T11", "shifted": target, "new_box": new, "crusade_added": True}


def _ev_khan_baty(state: GameState, args: dict[str, Any]) -> dict[str, Any]:
    """T12 Khan Baty (immediate). Shift Aleksandr/Andrey/their Service 2 boxes.
    Teuton choice direction.
    """
    target = args.get("target")
    direction = args.get("direction", "left")
    if target not in ("aleksandr", "andrey", "service:aleksandr", "service:andrey"):
        raise IllegalAction("missing_arg", "args.target required for T12")
    if target.startswith("service:"):
        lid = target.split(":", 1)[1]
        new = _shift_service(state, lid, 2, direction)
    else:
        new = _shift_cylinder(state, target, 2, direction)
    return {"event": "T12", "target": target, "new_box": new}


def _ev_swedish_crusade(state: GameState, args: dict[str, Any]) -> dict[str, Any]:
    """T18 Swedish Crusade. Shift Vladislav AND Karelians cylinder/Service each 1 box.
    Teuton choice direction.
    """
    direction = args.get("direction", "left")
    targets = args.get("targets", {"vladislav": "cylinder", "karelians": "cylinder"})
    out: dict[str, int] = {}
    for lid, kind in targets.items():
        if kind == "service":
            out[f"service:{lid}"] = _shift_service(state, lid, 1, direction)
        else:
            out[lid] = _shift_cylinder(state, lid, 1, direction)
    return {"event": "T18", "shifted": out}


def _ev_bountiful_harvest_t(state: GameState, args: dict[str, Any]) -> dict[str, Any]:
    """T14 Bountiful Harvest (Teutonic). Remove 1 Russian (white) Ravaged marker
    from Livonia or Estonia. Russian VP -0.5.
    """
    locale = args.get("locale")
    static = load_locales()
    if not isinstance(locale, str) or locale not in state.locales:
        raise IllegalAction("missing_arg", "args.locale required")
    info = static[locale]
    if info.get("territory") not in ("teutonic", "crusader"):
        raise IllegalAction("not_eligible_locale", "T14 removes Ravaged in Livonia/Estonia")
    if not state.locales[locale].russian_ravaged:
        raise IllegalAction("not_ravaged", f"{locale} has no Russian Ravaged marker")
    state.locales[locale].russian_ravaged = False
    state.calendar.russian_vp = max(0.0, state.calendar.russian_vp - 0.5)
    return {"event": "T14", "locale": locale}


def _ev_bountiful_harvest_r(state: GameState, args: dict[str, Any]) -> dict[str, Any]:
    """R18 Bountiful Harvest (Russian). Remove 1 Teutonic Ravaged marker from Rus."""
    locale = args.get("locale")
    static = load_locales()
    if not isinstance(locale, str) or locale not in state.locales:
        raise IllegalAction("missing_arg", "args.locale required")
    if static[locale].get("territory") != "russian":
        raise IllegalAction("not_eligible_locale", "R18 removes Ravaged in Rus")
    if not state.locales[locale].teutonic_ravaged:
        raise IllegalAction("not_ravaged", f"{locale} has no Teutonic Ravaged marker")
    state.locales[locale].teutonic_ravaged = False
    state.calendar.teutonic_vp = max(0.0, state.calendar.teutonic_vp - 0.5)
    return {"event": "R18", "locale": locale}


def _ev_mindaugas_t(state: GameState, args: dict[str, Any]) -> dict[str, Any]:
    """T15 Mindaugas. Place black Ravaged in Rus within 2 of Ostrov,
    not at Russian Lord or Stronghold, not already Ravaged.
    Phase 4c: trust args.locale; verify within-2 distance via BFS over Ways.
    """
    locale = args.get("locale")
    if not isinstance(locale, str) or locale not in state.locales:
        raise IllegalAction("missing_arg", "args.locale required for T15")
    static = load_locales()
    if static[locale].get("territory") != "russian":
        raise IllegalAction("not_eligible_locale", "T15 places Ravaged in Rus")
    # Distance check: BFS up to depth 2 from ostrov.
    from nevsky.static_data import load_ways
    ways = load_ways()
    adj: dict[str, list[str]] = {}
    for w in ways:
        adj.setdefault(w["a"], []).append(w["b"])
        adj.setdefault(w["b"], []).append(w["a"])
    visited = {"ostrov": 0}
    frontier = ["ostrov"]
    for d in range(1, 3):
        nxt = []
        for n in frontier:
            for m in adj.get(n, []):
                if m not in visited:
                    visited[m] = d
                    nxt.append(m)
        frontier = nxt
    if locale not in visited or visited[locale] > 2:
        raise IllegalAction("too_far", f"{locale} is more than 2 from Ostrov")
    # No Russian Lord at locale.
    if any(l.location == locale and l.side == "russian" for l in state.lords.values()):
        raise IllegalAction("russian_lord_present", f"Russian Lord at {locale}")
    # No Russian Stronghold (not Conquered by Teutons).
    # SMOKE-073 (Round 76): use _effective_stronghold so trade_route
    # base type AND Russian Castle markers on Town overlays count as
    # Russian Strongholds. The prior static-type list (fort, city,
    # novgorod) missed trade_route and Castle-on-Town overlays.
    sloc = state.locales[locale]
    from nevsky.campaign import _effective_stronghold
    eff_sh = _effective_stronghold(state, locale)
    has_russian_stronghold = (
        eff_sh is not None
        and eff_sh.get("side") == "russian"
        and sloc.teutonic_conquered == 0
    )
    if has_russian_stronghold:
        raise IllegalAction("russian_stronghold", f"{locale} has Russian Stronghold")
    if sloc.teutonic_ravaged or sloc.russian_ravaged:
        raise IllegalAction("already_ravaged", f"{locale} already Ravaged")
    sloc.teutonic_ravaged = True
    state.calendar.teutonic_vp += 0.5
    return {"event": "T15", "locale": locale}


def _ev_mindaugas_r(state: GameState, args: dict[str, Any]) -> dict[str, Any]:
    """R12 Mindaugas (Russian). Place white Ravaged in Livonia within 2 of Rositten,
    not at Teutonic Lord or Stronghold.
    """
    locale = args.get("locale")
    if not isinstance(locale, str) or locale not in state.locales:
        raise IllegalAction("missing_arg", "args.locale required for R12")
    static = load_locales()
    if static[locale].get("subregion") != "crusader_livonia":
        raise IllegalAction("not_eligible_locale", "R12 places Ravaged in Crusader Livonia")
    from nevsky.static_data import load_ways
    ways = load_ways()
    adj: dict[str, list[str]] = {}
    for w in ways:
        adj.setdefault(w["a"], []).append(w["b"])
        adj.setdefault(w["b"], []).append(w["a"])
    visited = {"rositten": 0}
    frontier = ["rositten"]
    for d in range(1, 3):
        nxt = []
        for n in frontier:
            for m in adj.get(n, []):
                if m not in visited:
                    visited[m] = d
                    nxt.append(m)
        frontier = nxt
    if locale not in visited:
        raise IllegalAction("too_far", f"{locale} not within 2 of Rositten")
    if any(l.location == locale and l.side == "teutonic" for l in state.lords.values()):
        raise IllegalAction("teutonic_lord_present", f"Teutonic Lord at {locale}")
    sloc = state.locales[locale]
    # SMOKE-073 (Round 76): use _effective_stronghold so Teutonic Castle
    # markers on Town overlays count as Teutonic Strongholds. The prior
    # static-type list (bishopric, castle) missed Castle-on-Town
    # overlays placed via T17 Stonemasons.
    from nevsky.campaign import _effective_stronghold
    eff_sh = _effective_stronghold(state, locale)
    has_teutonic_stronghold = (
        eff_sh is not None
        and eff_sh.get("side") == "teutonic"
        and sloc.russian_conquered == 0
    )
    if has_teutonic_stronghold:
        raise IllegalAction("teutonic_stronghold", f"{locale} has Teutonic Stronghold")
    if sloc.teutonic_ravaged or sloc.russian_ravaged:
        raise IllegalAction("already_ravaged", f"{locale} already Ravaged")
    sloc.russian_ravaged = True
    state.calendar.russian_vp += 0.5
    return {"event": "R12", "locale": locale}


def _ev_osilian_revolt(state: GameState, args: dict[str, Any]) -> dict[str, Any]:
    """R9 Osilian Revolt (immediate). Teutons choose to shift Service of Andreas
    OR Heinrich 2 boxes left.

    SMOKE-063 (Round 69): per AoW Reference R9 Tip — "shift the Service
    marker ... by 2 boxes to the degree able. ... as long as neither
    marker is yet in box 1 or off the left end of the Calendar." The
    target's Service marker must be at box >= 2; the shift is clamped
    so the marker does NOT go off the left end (R9's Tip omits the
    "1 box off Calendar allowed" allowance that R10/T12/T18 carry).
    """
    target = args.get("target")
    if target not in ("andreas", "heinrich"):
        raise IllegalAction("missing_arg", "args.target must be 'andreas' or 'heinrich'")
    from nevsky.actions import _find_service_marker_box
    sm_box = _find_service_marker_box(state, target)
    if sm_box is None:
        raise IllegalAction(
            "ineligible_target",
            f"R9: {target} has no Service marker on Calendar",
        )
    if sm_box <= 1:
        # Box 1 (cur=1) or off_left_service (cur=0) — illegal per Tip.
        raise IllegalAction(
            "ineligible_target",
            f"R9: {target} Service marker at box {sm_box} (must be >=2 per R9 Tip)",
        )
    # "Shift 2 boxes to the degree able" with no off-Calendar allowance:
    # clamp effective shift so the marker stays in box >=1.
    effective = min(2, sm_box - 1)
    new = _shift_service(state, target, effective, "left")
    return {"event": "R9", "target": target, "new_box": new}


def _ev_batu_khan(state: GameState, args: dict[str, Any]) -> dict[str, Any]:
    """R10 Batu Khan. Shift Andreas cylinder OR Service up to 2 boxes
    (Russian choice direction).
    """
    target = args.get("target")  # "andreas" | "service:andreas"
    direction = args.get("direction", "left")
    boxes = int(args.get("boxes", 2))
    if target not in ("andreas", "service:andreas"):
        raise IllegalAction("missing_arg", "args.target required")
    if not 1 <= boxes <= 2:
        raise IllegalAction("bad_boxes", "boxes must be 1 or 2")
    if target.startswith("service:"):
        new = _shift_service(state, "andreas", boxes, direction)
    else:
        new = _shift_cylinder(state, "andreas", boxes, direction)
    return {"event": "R10", "target": target, "new_box": new}


def _ev_prussian_revolt(state: GameState, args: dict[str, Any]) -> dict[str, Any]:
    """R14 Prussian Revolt (immediate).
    If Andreas on map AND Unbesieged AND nothing at Riga -> put him at Riga.
    Else (on Calendar) shift his cylinder 2 boxes RIGHT.
    """
    if "andreas" not in state.lords:
        raise IllegalAction("no_andreas", "Andreas not in state")
    a = state.lords["andreas"]
    riga = state.locales.get("riga")
    riga_static = load_locales()["riga"]
    riga_empty = (
        riga is not None
        and riga.siege_markers == 0
        and riga.russian_conquered == 0
        and riga.teutonic_conquered == 0
        and not riga.russian_ravaged
        and not riga.teutonic_ravaged
        and all(l.location != "riga" for l in state.lords.values())
        and (state.legate.locale_id != "riga")
    )
    if a.state == "mustered" and a.location is not None:
        # Check Besieged.
        besieged = a.in_stronghold and state.locales[a.location].siege_markers > 0
        if not besieged and riga_empty:
            a.location = "riga"
            # SMOKE-036 (Round 47/49): movement clears in_stronghold.
            a.in_stronghold = False
            return {"event": "R14", "moved_to_riga": True}
        return {"event": "R14", "no_effect": True, "reason": "andreas_on_map_but_riga_not_empty_or_besieged"}
    # Andreas not on map -> shift cylinder 2 right.
    try:
        new = _shift_cylinder(state, "andreas", 2, "right")
        return {"event": "R14", "shifted_right": new}
    except IllegalAction:
        return {"event": "R14", "no_effect": True, "reason": "andreas_not_on_calendar"}


def _ev_death_of_pope(state: GameState, args: dict[str, Any]) -> dict[str, Any]:
    """R15 Death of the Pope (immediate, this_levy persistence).
    Discard William of Modena from capabilities_in_play; remove Legate pawn;
    block Modena re-Levy this Levy.
    """
    discarded = False
    if "T13" in state.decks.teutonic.capabilities_in_play:
        state.decks.teutonic.capabilities_in_play.remove("T13")
        state.decks.teutonic.discard.append("T13")
        discarded = True
    state.legate.william_of_modena_in_play = False
    state.legate.location = "card"
    state.legate.locale_id = None
    # Block this-Levy re-Levy: tracked via meta.special_rules flag.
    state.meta.special_rules["block_william_of_modena_this_levy"] = True
    return {"event": "R15", "modena_discarded": discarded}


def _ev_tempest(state: GameState, args: dict[str, Any]) -> dict[str, Any]:
    """R16 Tempest (immediate). Remove all Ships from a chosen Teutonic Lord;
    half (rounded up) if he has Cogs.
    """
    target = args.get("target")
    if not isinstance(target, str) or target not in state.lords:
        raise IllegalAction("missing_arg", "args.target Teutonic lord_id required")
    if state.lords[target].side != "teutonic":
        raise IllegalAction("bad_target", "R16 target must be Teutonic")
    from nevsky.capabilities import has_lord_capability

    n = state.lords[target].assets.get("ship", 0)
    if has_lord_capability(state, target, "Cogs"):
        # Keep half rounded up.
        keep = (n + 1) // 2
        removed = n - keep
        if keep == 0:
            state.lords[target].assets.pop("ship", None)
        else:
            state.lords[target].assets["ship"] = keep
    else:
        removed = n
        state.lords[target].assets.pop("ship", None)
    return {"event": "R16", "target": target, "ships_removed": removed}


# ---------------------------------------------------------------------------
# This-levy block events (immediate-resolved + persistence=this_levy)
# ---------------------------------------------------------------------------


def _ev_valdemar(state: GameState, args: dict[str, Any]) -> dict[str, Any]:
    """R11 Valdemar (this-levy block). Russian choice direction shift Knud&Abel
    cylinder OR Service up to 1 box; THIS LEVY no Muster of or by them.
    """
    target = args.get("target", "knud_and_abel")  # "knud_and_abel" or "service:knud_and_abel"
    direction = args.get("direction", "left")
    boxes = int(args.get("boxes", 1))
    if not 0 <= boxes <= 1:
        raise IllegalAction("bad_boxes", "boxes must be 0 or 1")
    if boxes > 0:
        if target.startswith("service:"):
            new = _shift_service(state, "knud_and_abel", boxes, direction)
        else:
            new = _shift_cylinder(state, "knud_and_abel", boxes, direction)
    else:
        new = None
    if "knud_and_abel" not in state.meta.block_lords_this_levy_t:
        state.meta.block_lords_this_levy_t.append("knud_and_abel")
    return {"event": "R11", "shift": new, "blocked_this_levy": ["knud_and_abel"]}


def _ev_dietrich_r17(state: GameState, args: dict[str, Any]) -> dict[str, Any]:
    """R17 Dietrich von Grueningen leads Order to Kurland (this-levy block).
    Shift Andreas OR Rudolf OR Service of either 1 box; this Levy no Muster of or by them.
    """
    target = args.get("target", "andreas")
    direction = args.get("direction", "left")
    if target not in ("andreas", "rudolf", "service:andreas", "service:rudolf"):
        raise IllegalAction("missing_arg", "args.target required for R17")
    if target.startswith("service:"):
        lid = target.split(":", 1)[1]
        new = _shift_service(state, lid, 1, direction)
    else:
        lid = target
        new = _shift_cylinder(state, lid, 1, direction)
    for blocked in ("andreas", "rudolf"):
        if blocked not in state.meta.block_lords_this_levy_t:
            state.meta.block_lords_this_levy_t.append(blocked)
    return {"event": "R17", "shift": new, "blocked_this_levy": ["andreas", "rudolf"]}


# ---------------------------------------------------------------------------
# Hold events (resolve on play)
# ---------------------------------------------------------------------------


def _ev_pogost(state: GameState, args: dict[str, Any]) -> dict[str, Any]:
    """R3 Pogost (hold). Add 4 Provender to a Lord in Rus."""
    target = args.get("target")
    if not isinstance(target, str) or target not in state.lords:
        raise IllegalAction("missing_arg", "args.target Russian lord_id required")
    lord = state.lords[target]
    if lord.side != "russian" or lord.state != "mustered":
        raise IllegalAction("bad_target", "Pogost requires Russian Mustered Lord")
    if lord.location is None:
        raise IllegalAction("no_location", "Lord has no location")
    if load_locales()[lord.location]["territory"] != "russian":
        raise IllegalAction("not_in_rus", "Pogost requires Lord in Rus")
    pre = lord.assets.get("provender", 0)
    new = min(8, pre + 4)
    lord.assets["provender"] = new
    return {"event": "R3", "lord_id": target, "provender_added": new - pre}


# ---------------------------------------------------------------------------
# Lordship +2 hold events
# ---------------------------------------------------------------------------


_LORDSHIP_PLUS_2_TARGETS = {
    "T7":  {"side": "teutonic", "lords": {"hermann", "yaroslav"},   "shift_boxes": 2},
    "T8":  {"side": "teutonic", "lords": {"rudolf"},                "shift_boxes": 2},
    "T17": {"side": "teutonic", "lords": {"andreas", "rudolf"},     "shift_boxes": 2},
    "R8":  {"side": "russian",  "lords": "any_russian",             "shift_boxes": 1},
    "R13": {"side": "russian",  "lords": {"vladislav", "karelians"}, "shift_boxes": 2},
}


def apply_lordship_plus_2(state: GameState, card_id: str, lord_id: str) -> dict[str, Any]:
    """Apply Lordship +2 from a Hold event card to `lord_id`. Used during
    Muster (3.4) or Call to Arms (3.5). Adds 2 to meta.lordship_bonus[lord_id].
    """
    if card_id not in _LORDSHIP_PLUS_2_TARGETS:
        raise IllegalAction("bad_card", f"{card_id} is not a Lordship +2 hold")
    spec = _LORDSHIP_PLUS_2_TARGETS[card_id]
    side: str = spec["side"]  # type: ignore[assignment]
    lords = spec["lords"]
    if lords == "any_russian":
        if state.lords[lord_id].side != "russian":
            raise IllegalAction("bad_target", f"{card_id} targets any Russian Lord")
    else:
        if lord_id not in lords:  # type: ignore[operator]
            raise IllegalAction("bad_target", f"{card_id} targets {sorted(lords)} only")
    state.meta.lordship_bonus[lord_id] = state.meta.lordship_bonus.get(lord_id, 0) + 2
    return {"card": card_id, "lord_id": lord_id, "bonus": 2}


def apply_calendar_shift_hold(state: GameState, card_id: str, lord_id: str, direction: str) -> dict[str, Any]:
    """Alternate use of a Lordship +2 hold: shift the target Lord's
    cylinder by `shift_boxes` in chosen direction. Per card text."""
    if card_id not in _LORDSHIP_PLUS_2_TARGETS:
        raise IllegalAction("bad_card", f"{card_id} is not a Lordship-or-shift hold")
    spec = _LORDSHIP_PLUS_2_TARGETS[card_id]
    lords = spec["lords"]
    if lords == "any_russian":
        if state.lords[lord_id].side != "russian":
            raise IllegalAction("bad_target", f"{card_id} targets any Russian Lord")
    else:
        if lord_id not in lords:  # type: ignore[operator]
            raise IllegalAction("bad_target", f"{card_id} targets {sorted(lords)} only")
    boxes = int(spec["shift_boxes"])  # type: ignore[arg-type]
    new = _shift_cylinder(state, lord_id, boxes, direction)
    return {"card": card_id, "lord_id": lord_id, "new_box": new}


# ---------------------------------------------------------------------------
# Public dispatchers
# ---------------------------------------------------------------------------


_IMMEDIATE_RESOLVERS = {
    "T1":  _ev_grand_prince,
    "T2":  _ev_torzhok,
    "T11": _ev_pope_gregory,
    "T12": _ev_khan_baty,
    "T14": _ev_bountiful_harvest_t,
    "T15": _ev_mindaugas_t,
    "T18": _ev_swedish_crusade,
    "R9":  _ev_osilian_revolt,
    "R10": _ev_batu_khan,
    "R11": _ev_valdemar,
    "R12": _ev_mindaugas_r,
    "R14": _ev_prussian_revolt,
    "R15": _ev_death_of_pope,
    "R16": _ev_tempest,
    "R17": _ev_dietrich_r17,
    "R18": _ev_bountiful_harvest_r,
}

_HOLD_RESOLVERS = {
    "R3": _ev_pogost,
}


def resolve_immediate_event(state: GameState, card_id: str, args: dict[str, Any]) -> dict[str, Any]:
    """Dispatch an immediate event resolver. Tier 1 immediate events
    are wired here. Tier 2 Battle-context events are NOT routed
    through this dispatcher; they sit in a side's Holds and are
    consumed by _consume_battle_holds at Battle invocation. Events
    without a resolver return `deferred: True` and the caller falls
    back to manual play of the card text."""
    fn = _IMMEDIATE_RESOLVERS.get(card_id)
    if fn is None:
        return {"event": card_id, "deferred": True,
                "note": "no resolver wired; play the card text manually"}
    return fn(state, args)


def resolve_hold_event(state: GameState, card_id: str, args: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a hold event resolver. Covers R3 Pogost (and the Tier
    3 hold events T3 Vodian Treachery / T13 Heinrich Curia, which
    have their own handler entries). Events without a resolver return
    `deferred: True` and the caller falls back to manual play."""
    fn = _HOLD_RESOLVERS.get(card_id)
    if fn is None:
        return {"event": card_id, "deferred": True,
                "note": "no resolver wired; play the card text manually"}
    return fn(state, args)


# ---------------------------------------------------------------------------
# Tier 2 battle Hold consumption (Phase 4d)
# ---------------------------------------------------------------------------


def _consume_battle_holds(state: GameState, cp, holds_arg: dict) -> list[dict]:
    """Validate and consume Tier 2 Battle Hold events from each side's
    holds list. Returns a record of what was consumed.

    holds_arg shape (any subset):
      "marsh":         "T5"|"R2"   -> opposite-side Horse blocked rounds 1-2
      "hill":          "T9"|"R5"   -> defender Archery x1 rounds 1-2
      "ambush":        "T6"|"R6"   -> Round 1 ignore enemy left/right (no-op)
      "field_organ":   "T10"       -> with args.field_organ_lord
      "raven_rock":    "R4"        -> Russian defender Walls 1-2 vs Melee R1
      "bridge":        "T4"|"R1"   -> opposing front center Lord melee cap
                                       (Q-008 candidate: front-center IS
                                       modeled per Q-005, but the Bridge
                                       Melee cap rule is not yet wired
                                       into battle.py per-Lord step caps)

    Each consumed card is moved from holds to discard. If the card isn't
    in the side's holds list, IllegalAction is raised.
    """
    consumed = []
    side_decks = {
        "T4": ("teutonic", "marsh_holder"),
        "T5": ("teutonic", "marsh_holder"),
        "T6": ("teutonic", "ambush"),
        "T9": ("teutonic", "hill"),
        "T10": ("teutonic", "field_organ"),
        "R1": ("russian", "marsh_holder"),
        "R2": ("russian", "marsh_holder"),
        "R4": ("russian", "raven_rock"),
        "R5": ("russian", "hill"),
        "R6": ("russian", "ambush"),
    }
    for key, cid in holds_arg.items():
        if not isinstance(cid, str):
            continue
        if key in ("marsh", "hill", "ambush", "field_organ", "raven_rock", "bridge"):
            spec = side_decks.get(cid)
            if spec is None:
                raise IllegalAction("bad_hold", f"{cid} is not a Tier 2 battle Hold")
            side, _ = spec
            deck = state.decks.teutonic if side == "teutonic" else state.decks.russian
            if cid not in deck.holds:
                raise IllegalAction("not_in_holds", f"{cid} not in {side} holds")
            deck.holds.remove(cid)
            deck.discard.append(cid)
            consumed.append({"card": cid, "key": key})
    return consumed


# ---------------------------------------------------------------------------
# Tier 3 hold events (Phase 4d)
# ---------------------------------------------------------------------------


def _ev_vodian_treachery(state: GameState, args: dict[str, Any]) -> dict[str, Any]:
    """T3 Vodian Treachery (hold). Play if Teuton Lord closer than any
    Russian to Kaibolovo or Koporye Fort to Conquer it (no Spoils).

    "Closer" means shortest chain of adjacent Locales (by Ways, not by
    sea). Cannot apply if a Stone Kremlin (R18) Walls +1 marker is at
    the target. If Stonemasons converted both Forts to Castles, the
    event cannot be played.

    args:
      target: "kaibolovo" | "koporye"
    """
    from nevsky.static_data import load_locales, load_ways

    target = args.get("target")
    if target not in ("kaibolovo", "koporye"):
        raise IllegalAction("bad_target", "target must be kaibolovo or koporye")
    if target not in state.locales:
        raise IllegalAction("bad_target", f"{target} not in state")
    static = load_locales()[target]
    # Must still be a Fort (not converted to Castle).
    if static["type"] != "fort":
        raise IllegalAction("not_fort", f"{target} is no longer a Fort (Castle?)")
    # SMOKE-051 (Round 62): dynamic Castle marker also disqualifies.
    # T17 Stonemasons Tip: "Castles are permanent." Plus T3 Tip: "If
    # Stonemasons converted both Forts to Castles, this Event cannot
    # be played, because neither Locale has a Fort." The static type
    # stays "fort" even after a Castle marker is placed; we must
    # consult state.locales[*].teutonic_castle / russian_castle.
    if state.locales[target].teutonic_castle or state.locales[target].russian_castle:
        raise IllegalAction(
            "castle_marker",
            f"{target} has a Castle marker; Vodian Treachery requires a Fort (T3 Tip)",
        )
    # Walls +1 from R18 blocks Vodian Treachery.
    if state.locales[target].walls_plus_one:
        raise IllegalAction("stone_kremlin", f"{target} has Walls +1; Vodian Treachery blocked")
    # Compute closeness: BFS from target via Ways. Find min distance to
    # any T-side Mustered Lord vs any R-side.
    ways = load_ways()
    adj: dict[str, list[str]] = {}
    for w in ways:
        adj.setdefault(w["a"], []).append(w["b"])
        adj.setdefault(w["b"], []).append(w["a"])
    visited = {target: 0}
    frontier = [target]
    teu_dist = None
    rus_dist = None
    # SMOKE-052 (Round 62): check Lords AT the target locale (distance
    # 0). Previously the BFS only registered Lords as it expanded
    # outward; a Teutonic Lord standing at the target Fort itself was
    # silently missed, producing wrong teu_dist or no_teutonic_lord.
    for lid, l in state.lords.items():
        if l.state == "mustered" and l.location == target:
            if l.side == "teutonic" and teu_dist is None:
                teu_dist = 0
            elif l.side == "russian" and rus_dist is None:
                rus_dist = 0
    while frontier and (teu_dist is None or rus_dist is None):
        nxt = []
        for n in frontier:
            for m in adj.get(n, []):
                if m in visited:
                    continue
                visited[m] = visited[n] + 1
                nxt.append(m)
                # Check Lords here.
                for lid, l in state.lords.items():
                    if l.state == "mustered" and l.location == m:
                        if l.side == "teutonic" and teu_dist is None:
                            teu_dist = visited[m]
                        elif l.side == "russian" and rus_dist is None:
                            rus_dist = visited[m]
        frontier = nxt
    if teu_dist is None:
        raise IllegalAction("no_teutonic_lord", "no Teutonic Lord reachable from target")
    if rus_dist is not None and teu_dist >= rus_dist:
        raise IllegalAction(
            "not_closer",
            f"Teu distance {teu_dist} not strictly less than Rus distance {rus_dist}",
        )
    # Conquer (no Spoils).
    state.locales[target].teutonic_conquered += 1
    state.calendar.teutonic_vp += 1.0  # Fort = 1 VP
    return {"event": "T3", "conquered": target, "teu_dist": teu_dist, "rus_dist": rus_dist}


def _ev_heinrich_curia(state: GameState, args: dict[str, Any]) -> dict[str, Any]:
    """T13 Heinrich Sees the Curia (hold). Disband Heinrich on play;
    add 4 non-Loot Assets each to 2 on-map Teutonic Lords.

    args:
      recipients: list of 2 Teutonic Lord ids (on map).
      assets: optional dict {recipient_id: dict[asset_type, int]} where
              asset_type in {coin, provender, boat, cart, sled, ship}
              and totals 4 per recipient. If not provided, default:
              4 Coin to each.
    """
    from nevsky.actions import _remove_lord_permanently
    from nevsky.static_data import load_lords

    if "heinrich" not in state.lords:
        raise IllegalAction("no_heinrich", "heinrich not in state")
    h = state.lords["heinrich"]
    if h.state != "mustered" or h.location is None:
        raise IllegalAction(
            "heinrich_off_map",
            "Heinrich must be on map; otherwise this event is held until he Musters",
        )
    recipients = args.get("recipients", [])
    if not isinstance(recipients, list) or len(recipients) != 2:
        raise IllegalAction("bad_recipients", "args.recipients must be 2 Teutonic Lord ids")
    for rid in recipients:
        if rid not in state.lords:
            raise IllegalAction("bad_recipients", f"{rid} not in state")
        r = state.lords[rid]
        if r.side != "teutonic" or r.state != "mustered" or r.location is None:
            raise IllegalAction("bad_recipients", f"{rid} must be Teutonic and on map")

    asset_grants = args.get("assets") or {rid: {"coin": 4} for rid in recipients}
    # Validate totals = 4 per recipient and no Loot.
    distributed = {}
    for rid, grant in asset_grants.items():
        if rid not in recipients:
            raise IllegalAction("bad_grant", f"{rid} not in recipients list")
        if not isinstance(grant, dict):
            raise IllegalAction("bad_grant", f"{rid} grant must be a dict")
        if "loot" in grant:
            raise IllegalAction("loot_forbidden", "Heinrich Curia: no Loot")
        total = sum(int(v) for v in grant.values())
        if total != 4:
            raise IllegalAction("bad_grant_total", f"{rid} grant total {total} != 4")
        for k in grant:
            if k not in ("coin", "provender", "boat", "cart", "sled", "ship"):
                raise IllegalAction("bad_grant_type", f"{k} not a valid asset type")
        distributed[rid] = dict(grant)

    # Apply.
    for rid, grant in distributed.items():
        recip = state.lords[rid]
        for k, v in grant.items():
            recip.assets[k] = min(8, recip.assets.get(k, 0) + int(v))  # type: ignore[index]

    # SMOKE-053 (Round 62): Disband (NOT permanent remove) Heinrich.
    # Per AoW Reference T13 Tip: "play the Event to immediately
    # Disband him regardless of Service or situation; other Disband
    # rules apply." Permanent removal requires Battle/Storm losses,
    # not the Curia event. Use _disband_at_limit with cylinder placed
    # at his current Service-marker box (or current Levy box) +
    # service_rating, mirroring 3.3.2 at-limit Disband.
    from nevsky.actions import _disband_at_limit, _find_service_marker_box, _find_levy_marker_box
    sl = load_lords()["heinrich"]
    srating = int(sl["ratings"]["service"])
    # Choose the base box: prefer current Service marker box, else
    # fall back to the current Levy box (Heinrich must be on map per
    # the earlier check, so Service marker should be on Calendar).
    sm_box = _find_service_marker_box(state, "heinrich")
    if sm_box is None:
        try:
            sm_box = _find_levy_marker_box(state)
        except Exception:
            sm_box = 1
    new_box = sm_box + srating
    _disband_at_limit(state, "heinrich", new_box)
    return {"event": "T13", "heinrich_disbanded": True,
            "heinrich_new_box": min(new_box, 17),
            "recipients": recipients, "distributed": distributed}


_HOLD_RESOLVERS["T3"] = _ev_vodian_treachery
_HOLD_RESOLVERS["T13"] = _ev_heinrich_curia
