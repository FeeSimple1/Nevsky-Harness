"""SMOKE-114 (Round 177): R9 Osilian Revolt raised ineligible_target
when no eligible target (Andreas/Heinrich Service at box >= 2)
existed; per rule convention, the event should no-op.

Pre-fix the resolver only checked the specific args.target; if the
agent's choice was ineligible, it raised. But if NEITHER Andreas
NOR Heinrich had a Service marker at box >= 2 (both removed, both
off-edge, or both at box 1), the event had no valid resolution path.

Found via scripts/self_play.py (10 stuck sessions across multiple
scenarios x seeds): mid-game battles permanently removed Andreas;
Heinrich's Service was at box 1 or also missing; subsequent Levies
drew R9 with no reachable target.

Same audit pattern as SMOKE-112/113 (immediate event with no valid
target should discard with no effect).

Fix: pre-flight check — if neither Andreas's nor Heinrich's Service
marker is at box >= 2, return {"event": "R9", "no_op": True,
"reason": "no_eligible_service_at_box_ge_2"}.
"""
from __future__ import annotations

import inspect

import nevsky.actions  # noqa: F401
import nevsky.events as events
from nevsky.events import resolve_immediate_event
from nevsky.scenarios import load_scenario


def _clear_service(s, lid):
    cal = s.calendar
    for cb in cal.boxes:
        if lid in cb.service_markers:
            cb.service_markers.remove(lid)
    if lid in cal.off_left_service:
        cal.off_left_service.remove(lid)
    if lid in cal.off_right_service:
        cal.off_right_service.remove(lid)


def _put_service(s, lid, box):
    _clear_service(s, lid)
    if box == 0:
        s.calendar.off_left_service.append(lid)
    elif box == 17:
        s.calendar.off_right_service.append(lid)
    else:
        s.calendar.boxes[box - 1].service_markers.append(lid)


def test_smoke_114_marker_present():
    src = inspect.getsource(events._ev_osilian_revolt)
    assert "SMOKE-114" in src
    assert "no_op" in src


def test_smoke_114_no_op_when_both_off_calendar():
    s = load_scenario("crusade_on_novgorod", seed=1)
    _clear_service(s, "andreas")
    _clear_service(s, "heinrich")
    res = resolve_immediate_event(s, "R9", {"target": "andreas"})
    assert res.get("no_op") is True
    assert res.get("reason") == "no_eligible_service_at_box_ge_2"


def test_smoke_114_no_op_when_both_at_box_1():
    s = load_scenario("crusade_on_novgorod", seed=1)
    _put_service(s, "andreas", 1)
    _put_service(s, "heinrich", 1)
    res = resolve_immediate_event(s, "R9", {"target": "andreas"})
    assert res.get("no_op") is True


def test_smoke_114_no_op_when_one_at_box_1_one_off_calendar():
    s = load_scenario("crusade_on_novgorod", seed=1)
    _put_service(s, "andreas", 1)
    _clear_service(s, "heinrich")
    res = resolve_immediate_event(s, "R9", {"target": "andreas"})
    assert res.get("no_op") is True


def test_smoke_114_still_resolves_when_at_least_one_eligible():
    """If at least one of Andreas/Heinrich has Service >= 2, R9
    proceeds with normal arg validation."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    _put_service(s, "andreas", 5)
    _clear_service(s, "heinrich")
    res = resolve_immediate_event(s, "R9", {"target": "andreas"})
    assert res.get("no_op") is None or res.get("no_op") is False
    assert res.get("new_box") == 3


def test_smoke_114_off_left_doesnt_count_as_eligible():
    """off_left_service (box 0) does NOT satisfy box >= 2 — no-op
    fires if both are off-left."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    _put_service(s, "andreas", 0)
    _put_service(s, "heinrich", 0)
    res = resolve_immediate_event(s, "R9", {"target": "andreas"})
    assert res.get("no_op") is True
