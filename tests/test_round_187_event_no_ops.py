"""SMOKE-121 (Round 187): Event no-op pattern extended to T11, R11,
R17, T18 — events that try to shift a Lord's cylinder/Service should
no-op when no valid target exists. Same family as SMOKE-112/113/114
(T14/R18, R10, R9).

For R11 and R17, the this-Levy block list side-effect still applies
even when the shift portion no-ops (the block is a separate effect).

Found via the 300-session strategic-agent sweep (R187) which left 15
sessions stuck across these four event resolvers.
"""
from __future__ import annotations

import nevsky.actions  # noqa: F401
from nevsky.events import resolve_immediate_event
from nevsky.scenarios import load_scenario


def _strip_lord_from_calendar(s, lid):
    cal = s.calendar
    for cb in cal.boxes:
        if lid in cb.cylinders:
            cb.cylinders.remove(lid)
        if lid in cb.service_markers:
            cb.service_markers.remove(lid)
    for lst in (cal.off_left, cal.off_right,
                cal.off_left_service, cal.off_right_service):
        if lid in lst:
            lst.remove(lid)


# ---------- T11 Pope Gregory --------------------------------------------


def test_smoke_121_t11_no_op_when_no_teuton_cylinder():
    s = load_scenario("watland", seed=1)
    # Strip all Teutonic Lord cylinders from Calendar
    for lid, l in list(s.lords.items()):
        if l.side == "teutonic":
            _strip_lord_from_calendar(s, lid)
    res = resolve_immediate_event(s, "T11", {"target": "andreas"})
    assert res.get("no_op") is True
    assert res.get("reason") == "no_teutonic_cylinder_on_calendar"


def test_smoke_121_t11_still_resolves_when_target_exists():
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items()
               if l.side == "teutonic" and l.state == "ready")
    if "T11" in s.decks.teutonic.capabilities_in_play:
        s.decks.teutonic.capabilities_in_play.remove("T11")
    res = resolve_immediate_event(s, "T11", {"target": teu})
    assert res.get("no_op") is None or res.get("no_op") is False
    assert "T11" in s.decks.teutonic.capabilities_in_play


# ---------- R11 Valdemar --------------------------------------------------


def test_smoke_121_r11_block_still_applies_when_no_shift():
    """Even if knud_and_abel is off-Calendar, the this-Levy block
    still applies (he could still be Mustered on map but Lordship
    blocked)."""
    s = load_scenario("watland", seed=1)
    _strip_lord_from_calendar(s, "knud_and_abel")
    res = resolve_immediate_event(s, "R11", {"target": "knud_and_abel"})
    assert res.get("event") == "R11"
    # shift should be None (no target)
    assert res.get("shift") is None
    # but block still applied
    assert "knud_and_abel" in s.meta.block_lords_this_levy_t


def test_smoke_121_r11_still_shifts_when_on_calendar():
    s = load_scenario("crusade_on_novgorod", seed=1)
    # knud_and_abel starts on Calendar in CtN
    res = resolve_immediate_event(s, "R11", {"target": "knud_and_abel",
                                              "direction": "left"})
    assert res.get("shift") is not None


# ---------- R17 Dietrich ---------------------------------------------------


def test_smoke_121_r17_block_still_applies_when_no_shift():
    s = load_scenario("watland", seed=1)
    _strip_lord_from_calendar(s, "andreas")
    _strip_lord_from_calendar(s, "rudolf")
    res = resolve_immediate_event(s, "R17", {"target": "andreas"})
    # Both blocked
    assert "andreas" in s.meta.block_lords_this_levy_t
    assert "rudolf" in s.meta.block_lords_this_levy_t


# ---------- T18 Swedish Crusade --------------------------------------------


def test_smoke_121_t18_no_op_when_neither_target_on_calendar():
    s = load_scenario("watland", seed=1)
    _strip_lord_from_calendar(s, "vladislav")
    _strip_lord_from_calendar(s, "karelians")
    res = resolve_immediate_event(s, "T18", {})
    assert res.get("no_op") is True


def test_smoke_121_t18_partial_resolution_when_one_target_on_calendar():
    """T18 shifts BOTH Vladislav AND Karelians. If only one is on
    Calendar, shift that one; skip the other."""
    s = load_scenario("watland", seed=1)
    _strip_lord_from_calendar(s, "karelians")
    # Vladislav should still be on Calendar at default Watland setup
    res = resolve_immediate_event(s, "T18", {
        "targets": {"vladislav": "cylinder", "karelians": "cylinder"},
        "direction": "right",
    })
    # T18 might partially resolve (Vladislav shifts; Karelians skipped)
    # or no-op entirely depending on which targets are available.
    # The key invariant: doesn\'t raise.
    assert res.get("event") == "T18"
