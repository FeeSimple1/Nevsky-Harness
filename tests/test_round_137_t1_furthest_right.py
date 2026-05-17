"""SMOKE-102 (Round 137): T1 Grand Prince — "furthest right Service" rule
not enforced.

Per AoW Reference T1 card text:
    "On Calendar, shift Aleksandr OR Andrey OR furthest right Service
     of either 2 boxes"

Tips:
    "If both Service are [on the Calendar], the one in the highest
     Calendar box shifts. If both Service are in the same box, or if
     one cylinder and one Service is on the Calendar, Teutons choose."

Pre-fix, the harness allowed the agent to pick either `service:aleksandr`
or `service:andrey` regardless of which was further right when both
Service markers were on the Calendar. Same audit pattern as SMOKE-046
(Marshal gate), SMOKE-048 (Transport count), SMOKE-067 (Way type arg):
"rule-cite-but-no-enforce."

Compare to T12 Khan Baty, whose card text is "shift Aleksandr OR Andrey
OR Service of either" (no "furthest right" qualifier) — so T12 retains
free Teuton choice on the Service target. The fix is therefore scoped
to T1 only.

Fix raises IllegalAction("not_furthest_right") if the agent picks the
lower-box service when both are on the Calendar in different boxes.
"""
from __future__ import annotations

import inspect

import nevsky.actions  # noqa: F401
import nevsky.events as events
import pytest
from nevsky.actions import IllegalAction
from nevsky.events import resolve_immediate_event
from nevsky.scenarios import load_scenario


def _clear_service(s, lord_id):
    for cb in s.calendar.boxes:
        if lord_id in cb.service_markers:
            cb.service_markers.remove(lord_id)
    if lord_id in s.calendar.off_left_service:
        s.calendar.off_left_service.remove(lord_id)
    if lord_id in s.calendar.off_right_service:
        s.calendar.off_right_service.remove(lord_id)


def _put_service_at(s, lord_id, box):
    _clear_service(s, lord_id)
    s.calendar.boxes[box - 1].service_markers.append(lord_id)


def test_smoke_102_marker_present():
    src = inspect.getsource(events._ev_grand_prince)
    assert "SMOKE-102" in src
    assert "furthest right" in src.lower()


def test_smoke_102_rejects_lower_box_service_when_both_on_calendar():
    """Aleksandr service at box 3, Andrey service at box 7.
    Picking service:aleksandr is illegal (Andrey is further right)."""
    s = load_scenario("return_of_the_prince", seed=1)
    _put_service_at(s, "aleksandr", 3)
    _put_service_at(s, "andrey", 7)
    with pytest.raises(IllegalAction) as ei:
        resolve_immediate_event(s, "T1", {"target": "service:aleksandr",
                                          "direction": "left"})
    assert "not_furthest_right" in str(ei.value) or "furthest" in str(ei.value).lower()


def test_smoke_102_allows_higher_box_service_when_both_on_calendar():
    """Aleksandr at box 3, Andrey at box 7. service:andrey is legal."""
    s = load_scenario("return_of_the_prince", seed=1)
    _put_service_at(s, "aleksandr", 3)
    _put_service_at(s, "andrey", 7)
    res = resolve_immediate_event(s, "T1", {"target": "service:andrey",
                                            "direction": "left"})
    assert res["new_box"] == 5  # 7 - 2 = 5
    assert "andrey" in s.calendar.boxes[4].service_markers


def test_smoke_102_allows_either_when_same_box():
    """If both services in same box, Teuton chooses."""
    s = load_scenario("return_of_the_prince", seed=1)
    _put_service_at(s, "aleksandr", 5)
    _put_service_at(s, "andrey", 5)
    # Either should be legal.
    res = resolve_immediate_event(s, "T1", {"target": "service:aleksandr",
                                            "direction": "right"})
    assert res["new_box"] == 7


def test_smoke_102_allows_lone_service_on_calendar():
    """If only Aleksandr service is on Calendar, picking it is legal."""
    s = load_scenario("return_of_the_prince", seed=1)
    _put_service_at(s, "aleksandr", 3)
    _clear_service(s, "andrey")  # ensure not present
    res = resolve_immediate_event(s, "T1", {"target": "service:aleksandr",
                                            "direction": "right"})
    assert res["new_box"] == 5


def test_smoke_102_off_calendar_does_not_count_for_constraint():
    """If one service is on Calendar at box X and the other is in
    off_left_service or off_right_service, the off-Calendar one
    doesn't count as 'on the Calendar' — the on-Calendar one is
    freely shiftable regardless of relative position."""
    s = load_scenario("return_of_the_prince", seed=1)
    _put_service_at(s, "aleksandr", 8)
    _clear_service(s, "andrey")
    s.calendar.off_right_service.append("andrey")  # off-Calendar
    # Picking aleksandr should be legal even though off-right "would"
    # be higher in box-order.
    res = resolve_immediate_event(s, "T1", {"target": "service:aleksandr",
                                            "direction": "left"})
    assert res["new_box"] == 6


def test_smoke_102_cylinder_target_unaffected():
    """The constraint applies only to service: targets; cylinder
    targets are unconstrained (Teuton choice per the rule)."""
    s = load_scenario("return_of_the_prince", seed=1)
    # Both cylinders on Calendar.
    for cb in s.calendar.boxes:
        if "aleksandr" in cb.cylinders:
            cb.cylinders.remove("aleksandr")
        if "andrey" in cb.cylinders:
            cb.cylinders.remove("andrey")
    s.calendar.boxes[3].cylinders.append("aleksandr")  # box 4
    s.calendar.boxes[7].cylinders.append("andrey")     # box 8
    # Either cylinder target is legal per the rule.
    res = resolve_immediate_event(s, "T1", {"target": "aleksandr",
                                            "direction": "right"})
    assert res["new_box"] == 6


def test_smoke_102_does_not_affect_t12():
    """T12 Khan Baty card text is 'Service of either' with no
    'furthest right' qualifier. The fix is scoped to T1 only."""
    src = inspect.getsource(events._ev_khan_baty)
    assert "SMOKE-102" not in src
    # T12 still accepts either service freely.
    s = load_scenario("return_of_the_prince", seed=1)
    _put_service_at(s, "aleksandr", 3)
    _put_service_at(s, "andrey", 7)
    res = resolve_immediate_event(s, "T12", {"target": "service:aleksandr",
                                             "direction": "left"})
    assert res["new_box"] == 1
