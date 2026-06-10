"""R202: event-implement candidate generation, in `src` so both the
harness (legal_moves + the aow_implement handler) and the agents can
use one source of truth.

`_populate_event_args` is a single best-guess arg populator; 
`_expand_event_variants` enumerates candidate arg-dicts (multiple
targets/directions/magnitudes) for an immediate / this_levy Event;
`applicable_event_implements` snapshot-tests those candidates and
returns the ones that actually resolve, which is how the harness
answers "does a legal target exist for this Event right now?".

Ported verbatim from scripts/self_play.py (which now imports from
here) plus the R202 additions: a boxes=0 ("up to N" -> shift 0)
candidate for R10, and applicable_event_implements.
"""
from __future__ import annotations

from typing import Any

from nevsky.static_data import load_locales, load_ways  # noqa: F401 (used in functions)


def _populate_event_args(state, cid, args):
    """Populate event-specific args for aow_implement_card. Resolves
    dynamic choices from current state."""
    new = dict(args)
    cal = state.calendar

    def cyl_on_cal(lid):
        if lid in cal.off_left or lid in cal.off_right:
            return True
        return any(lid in cb.cylinders for cb in cal.boxes)

    def service_on_cal(lid):
        if lid in cal.off_left_service or lid in cal.off_right_service:
            return True
        return any(lid in cb.service_markers for cb in cal.boxes)

    def first_on_calendar(lord_ids):
        for lid in lord_ids:
            if cyl_on_cal(lid):
                return lid
        return None

    def first_with_service(lord_ids):
        for lid in lord_ids:
            if service_on_cal(lid):
                return lid
        return None

    # T1 Grand Prince: prefer cylinder over service; pick whichever Lord
    # is actually on Calendar.
    if cid == "T1":
        if cyl_on_cal("andrey"):
            new.setdefault("target", "andrey")
        elif cyl_on_cal("aleksandr"):
            new.setdefault("target", "aleksandr")
        elif service_on_cal("andrey") and service_on_cal("aleksandr"):
            # Furthest right service (SMOKE-102): pick higher-box one.
            def sbox(lid):
                for cb in cal.boxes:
                    if lid in cb.service_markers:
                        return cb.box
                return 0
            if sbox("andrey") >= sbox("aleksandr"):
                new.setdefault("target", "service:andrey")
            else:
                new.setdefault("target", "service:aleksandr")
        elif service_on_cal("andrey"):
            new.setdefault("target", "service:andrey")
        elif service_on_cal("aleksandr"):
            new.setdefault("target", "service:aleksandr")
        # Only attach a direction when a target actually exists; otherwise
        # leave args bare so the handler no-legal-target reveal-and-discard
        # fallback (Q-R201-A) can fire. Direction was previously always set,
        # and _has_target_args counts it as a target arg, so the bare
        # implement got corrupted into an always-rejected move -> a hard
        # driver deadlock when neither Aleksandr nor Andrey is on the Calendar.
        if "target" in new:
            new.setdefault("direction", "left")
    # T12 Khan Baty
    elif cid == "T12":
        if cyl_on_cal("andrey"):
            new.setdefault("target", "andrey")
        elif cyl_on_cal("aleksandr"):
            new.setdefault("target", "aleksandr")
        elif service_on_cal("andrey"):
            new.setdefault("target", "service:andrey")
        elif service_on_cal("aleksandr"):
            new.setdefault("target", "service:aleksandr")
        if "target" in new:  # see T1 note: don't corrupt the no-target bare implement
            new.setdefault("direction", "left")
    elif cid == "T2":
        new.setdefault("target", "veche")
    elif cid == "T11":
        # Pick a Teutonic Lord with cylinder on Calendar
        for lid, l in state.lords.items():
            if l.side == "teutonic" and cyl_on_cal(lid):
                new.setdefault("target", lid)
                break
        else:
            new.setdefault("target", "andreas")
    elif cid == "T14":
        # Find a Russian-ravaged locale in Livonia/Estonia
        static = load_locales()
        for lid, loc in state.locales.items():
            if loc.russian_ravaged and static[lid].get("territory") in ("teutonic", "crusader"):
                new.setdefault("locale", lid)
                break
        else:
            # Fallback: any russian_ravaged locale
            for lid, loc in state.locales.items():
                if loc.russian_ravaged:
                    new.setdefault("locale", lid)
                    break
    elif cid == "R18":
        static = load_locales()
        for lid, loc in state.locales.items():
            if loc.teutonic_ravaged and static[lid].get("territory") == "russian":
                new.setdefault("locale", lid)
                break
        else:
            for lid, loc in state.locales.items():
                if loc.teutonic_ravaged:
                    new.setdefault("locale", lid)
                    break
    elif cid == "T15":
        # Russian-territory locale within 2 of ostrov, not ravaged, no Russian Lord/Stronghold
        static = load_locales()
        ways = load_ways()
        adj = {}
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
        for lid in visited:
            if (lid in state.locales and static[lid].get("territory") == "russian"
                    and not state.locales[lid].russian_ravaged
                    and not state.locales[lid].teutonic_ravaged
                    and not any(l.side == "russian" and l.location == lid
                                for l in state.lords.values())):
                new.setdefault("locale", lid)
                break
        else:
            new.setdefault("locale", "ostrov")
    elif cid == "R12":
        # Mirror of T15 with rositten
        static = load_locales()
        ways = load_ways()
        adj = {}
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
        for lid in visited:
            if (lid in state.locales
                    and static[lid].get("subregion") == "crusader_livonia"
                    and not state.locales[lid].russian_ravaged
                    and not state.locales[lid].teutonic_ravaged
                    and not any(l.side == "teutonic" and l.location == lid
                                for l in state.lords.values())):
                new.setdefault("locale", lid)
                break
    elif cid == "T18":
        new.setdefault("targets", {"vladislav": "cylinder", "karelians": "cylinder"})
        new.setdefault("direction", "right")
    elif cid == "R9":
        # Andreas or Heinrich; pick one whose Service is at >= 2
        cal = state.calendar
        def sbox(lid):
            for cb in cal.boxes:
                if lid in cb.service_markers:
                    return cb.box
            return None
        for target in ("andreas", "heinrich"):
            b = sbox(target)
            if b is not None and b >= 2:
                new.setdefault("target", target)
                break
        else:
            new.setdefault("target", "andreas")  # may raise; agent recovers
    elif cid == "R10":
        if cyl_on_cal("andreas"):
            new.setdefault("target", "andreas")
        elif service_on_cal("andreas"):
            new.setdefault("target", "service:andreas")
        else:
            new.setdefault("target", "andreas")  # may fail; agent recovers
        new.setdefault("direction", "left")
    elif cid == "R11":
        new.setdefault("target", "knud_and_abel")
        new.setdefault("direction", "left")
        new.setdefault("boxes", 1)
    elif cid == "R16":
        for lid, l in state.lords.items():
            if l.side == "teutonic" and l.state == "mustered":
                new.setdefault("target", lid)
                break
        else:
            new.setdefault("target", "andreas")
    elif cid == "R17":
        for tgt in ("andreas", "rudolf"):
            if cyl_on_cal(tgt):
                new.setdefault("target", tgt)
                break
        else:
            new.setdefault("target", "service:andreas")
        new.setdefault("direction", "left")
    return new




def _expand_event_variants(state, move):
    """For an aow_implement_card move, return a list of variant
    actions trying different valid targets. Used as a fallback when
    the primary target is unreachable."""
    cid = move.get("args", {}).get("card_id")
    if cid is None:
        return [move]
    base = {k: v for k, v in move.items() if k in ("type", "side", "args")}
    variants = []
    def variant(extra_args):
        new_action = {**base, "args": {**base["args"], **extra_args}}
        variants.append(new_action)
    # Multi-target events: produce one variant per possible target.
    if cid in ("T1", "T12"):
        # Try all four target options.
        for tgt in ("andrey", "aleksandr", "service:andrey", "service:aleksandr"):
            for direction in ("left", "right"):
                variant({"target": tgt, "direction": direction})
    elif cid == "T11":
        for lid, l in state.lords.items():
            if l.side == "teutonic":
                variant({"target": lid})
    elif cid in ("R10",):
        for tgt in ("andreas", "service:andreas"):
            for d in ("left", "right"):
                for boxes in (2, 1, 0):  # R202: "up to 2" includes shift 0
                    variant({"target": tgt, "direction": d, "boxes": boxes})
    elif cid in ("R17",):
        for tgt in ("andreas", "rudolf", "service:andreas", "service:rudolf"):
            for d in ("left", "right"):
                variant({"target": tgt, "direction": d})
    elif cid in ("R9",):
        for tgt in ("andreas", "heinrich"):
            variant({"target": tgt})
    elif cid in ("R16",):
        for lid, l in state.lords.items():
            if l.side == "teutonic" and l.state == "mustered":
                variant({"target": lid})
    elif cid in ("T2",):
        variant({"target": "veche"})
        variant({"target": "domash"})
    elif cid in ("T14", "R18"):
        # Try each locale that has the relevant ravaged marker.
        for lid, loc in state.locales.items():
            if cid == "T14" and loc.russian_ravaged:
                variant({"locale": lid})
            elif cid == "R18" and loc.teutonic_ravaged:
                variant({"locale": lid})
    elif cid in ("T15", "R12"):
        # Try each candidate locale within 2 of ostrov/rositten.
        center = "ostrov" if cid == "T15" else "rositten"
        ways = load_ways()
        adj = {}
        for w in ways:
            adj.setdefault(w["a"], []).append(w["b"])
            adj.setdefault(w["b"], []).append(w["a"])
        visited = {center: 0}
        frontier = [center]
        for d in range(1, 3):
            nxt = []
            for n in frontier:
                for m in adj.get(n, []):
                    if m not in visited:
                        visited[m] = d
                        nxt.append(m)
            frontier = nxt
        for lid in sorted(visited):
            variant({"locale": lid})
    elif cid in ("R11",):
        for d in ("left", "right"):
            for b in (1, 0):
                variant({"target": "knud_and_abel", "direction": d, "boxes": b})
    elif cid in ("T18",):
        for d in ("left", "right"):
            variant({"targets": {"vladislav": "cylinder", "karelians": "cylinder"},
                     "direction": d})
            variant({"targets": {"vladislav": "service", "karelians": "service"},
                     "direction": d})
    # Always include the original as a fallback (with populate_event_args).
    populated_args = _populate_event_args(state, cid, move.get("args", {}))
    variants.insert(0, {**base, "args": populated_args})
    return variants if variants else [move]




def applicable_event_implements(state, side: str, card_id: str) -> list[dict[str, Any]]:
    """Return the candidate aow_implement_card actions for `card_id`
    that APPLY cleanly (resolve without raising) against a snapshot of
    `state`. Empty list == no legal target exists for this Event right
    now (the only case in which a bare implement may reveal-and-discard
    per 3.1.4 Greed; otherwise the Event is mandatory and the player
    must pick one of these)."""
    from nevsky.actions import IllegalAction, apply_action
    move = {"type": "aow_implement_card", "side": side, "args": {"card_id": card_id}}
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    import json as _json
    for variant in _expand_event_variants(state, move):
        args = variant.get("args", {})
        # Skip the bare/no-target variant for the applicability probe.
        if not any(k != "card_id" for k in args):
            continue
        key = _json.dumps(args, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        snap = state.model_copy(deep=True)
        try:
            apply_action(snap, {"type": "aow_implement_card", "side": side, "args": dict(args)})
        except IllegalAction:
            continue
        except Exception:
            continue
        out.append({"type": "aow_implement_card", "side": side, "args": dict(args)})
    return out
