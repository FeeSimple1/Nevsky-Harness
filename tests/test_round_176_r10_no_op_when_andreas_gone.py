"""SMOKE-113 (Round 176): R10 Batu Khan raised no_cylinder when
Andreas was permanently removed (or otherwise absent from Calendar);
per rule convention, the event should no-op.

R10 Tip: "On Calendar, shift Andreas cylinder OR Service up to 2
boxes" — implicitly requires Andreas's marker to BE on the Calendar.
If Andreas is mustered on map only (cylinder removed) and his
service marker was also removed (e.g., permanent removal in
Battle), the event has no valid target.

Found via scripts/self_play.py (5 stuck sessions across peipus
seeds 2,3,4,5,10 and return_of_the_prince seeds 4,9): Andreas was
permanently removed in mid-game battles; subsequent Levies drew
R10 with no reachable target.

Same audit pattern as SMOKE-112 (immediate event with no valid
target should discard with no effect).

Fix: pre-flight check — if neither Andreas's cylinder nor service
marker is anywhere on the Calendar (in boxes or off-edges), return
{"event": "R10", "no_op": True, "reason": "andreas_unreachable_on_
calendar"} instead of raising.
"""
from __future__ import annotations

import inspect

import nevsky.actions  # noqa: F401
import nevsky.events as events
from nevsky.events import resolve_immediate_event
from nevsky.scenarios import load_scenario


def test_smoke_113_marker_present():
    src = inspect.getsource(events._ev_batu_khan)
    assert "SMOKE-113" in src
    assert "no_op" in src


def test_smoke_113_no_op_when_andreas_off_calendar():
    s = load_scenario("watland", seed=1)
    # Remove andreas from all Calendar positions
    cal = s.calendar
    for cb in cal.boxes:
        if "andreas" in cb.cylinders:
            cb.cylinders.remove("andreas")
        if "andreas" in cb.service_markers:
            cb.service_markers.remove("andreas")
    if "andreas" in cal.off_left:
        cal.off_left.remove("andreas")
    if "andreas" in cal.off_right:
        cal.off_right.remove("andreas")
    if "andreas" in cal.off_left_service:
        cal.off_left_service.remove("andreas")
    if "andreas" in cal.off_right_service:
        cal.off_right_service.remove("andreas")
    res = resolve_immediate_event(s, "R10", {})
    assert res.get("no_op") is True
    assert res.get("reason") == "andreas_unreachable_on_calendar"


def test_smoke_113_still_resolves_when_andreas_has_service_on_calendar():
    s = load_scenario("watland", seed=1)
    cal = s.calendar
    for cb in cal.boxes:
        if "andreas" in cb.cylinders:
            cb.cylinders.remove("andreas")
        if "andreas" in cb.service_markers:
            cb.service_markers.remove("andreas")
    if "andreas" in cal.off_left:
        cal.off_left.remove("andreas")
    if "andreas" in cal.off_right:
        cal.off_right.remove("andreas")
    # Place his service in box 5
    cal.boxes[4].service_markers.append("andreas")
    res = resolve_immediate_event(s, "R10", {"target": "service:andreas",
                                              "direction": "left", "boxes": 2})
    assert res.get("no_op") is None or res.get("no_op") is False
    assert res.get("new_box") == 3


def test_smoke_113_still_resolves_when_andreas_cylinder_on_calendar():
    s = load_scenario("watland", seed=1)
    cal = s.calendar
    # Clean up any existing cylinder positions
    for cb in cal.boxes:
        if "andreas" in cb.cylinders:
            cb.cylinders.remove("andreas")
    if "andreas" in cal.off_left:
        cal.off_left.remove("andreas")
    if "andreas" in cal.off_right:
        cal.off_right.remove("andreas")
    cal.boxes[7].cylinders.append("andreas")  # box 8
    res = resolve_immediate_event(s, "R10", {"target": "andreas",
                                              "direction": "left", "boxes": 2})
    assert res.get("no_op") is None or res.get("no_op") is False
    assert res.get("new_box") == 6


def test_smoke_113_off_edge_cylinder_counts_as_on_calendar():
    """Andreas in off_left or off_right is still tracked on Calendar."""
    s = load_scenario("watland", seed=1)
    cal = s.calendar
    for cb in cal.boxes:
        if "andreas" in cb.cylinders:
            cb.cylinders.remove("andreas")
    if "andreas" in cal.off_right:
        cal.off_right.remove("andreas")
    cal.off_left.append("andreas")
    # Should not no-op — andreas is in off_left, still tracked.
    res = resolve_immediate_event(s, "R10", {"target": "andreas",
                                              "direction": "right", "boxes": 1})
    # off_left=0 + 1 = 1; landing on box 1
    assert res.get("no_op") is None or res.get("no_op") is False
