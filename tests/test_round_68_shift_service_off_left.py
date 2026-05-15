"""SMOKE-062 (Round 68): _shift_service must allow off_left_service shifts.

Per AoW Reference R10/T12/T18 Tips: "Shifting just one box off the
Calendar from box 1 or box 16 is allowed." Prior code used
max(1, cur - boxes), clamping at box 1 and silently no-op'ing legal
left-shifts that should have landed on off_left_service.
"""
from __future__ import annotations

from nevsky.events import _shift_service
from nevsky.scenarios import load_scenario


def _put_service(state, lord_id, box):
    """Place lord's service marker at `box` (1..16), or off_left_service
    if box==0, off_right_service if box==17."""
    cal = state.calendar
    for cb in cal.boxes:
        if lord_id in cb.service_markers:
            cb.service_markers.remove(lord_id)
    if lord_id in cal.off_left_service:
        cal.off_left_service.remove(lord_id)
    if lord_id in cal.off_right_service:
        cal.off_right_service.remove(lord_id)
    if box == 0:
        cal.off_left_service.append(lord_id)
    elif box == 17:
        cal.off_right_service.append(lord_id)
    else:
        cal.boxes[box - 1].service_markers.append(lord_id)


def test_shift_left_from_box_2_goes_off_left_when_2_boxes():
    s = load_scenario("crusade_on_novgorod", seed=1)
    _put_service(s, "andreas", 2)
    new = _shift_service(s, "andreas", 2, "left")
    assert new == 0
    assert "andreas" in s.calendar.off_left_service


def test_shift_left_from_box_1_goes_off_left():
    s = load_scenario("crusade_on_novgorod", seed=1)
    _put_service(s, "andreas", 1)
    new = _shift_service(s, "andreas", 1, "left")
    assert new == 0
    assert "andreas" in s.calendar.off_left_service


def test_shift_left_clamps_at_off_left_when_overshooting():
    """From box 1, shift 3 left would be -2; clamp at off_left_service."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    _put_service(s, "andreas", 1)
    new = _shift_service(s, "andreas", 3, "left")
    assert new == 0
    assert "andreas" in s.calendar.off_left_service


def test_shift_left_from_box_3_with_2_boxes_lands_at_1():
    s = load_scenario("crusade_on_novgorod", seed=1)
    _put_service(s, "andreas", 3)
    new = _shift_service(s, "andreas", 2, "left")
    assert new == 1
    assert "andreas" in s.calendar.boxes[0].service_markers


def test_shift_right_unchanged_behavior():
    """Right shifts still cap at off_right_service when going past 16."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    _put_service(s, "andreas", 15)
    new = _shift_service(s, "andreas", 3, "right")
    assert new == 17
    assert "andreas" in s.calendar.off_right_service


def test_shift_from_off_left_supported():
    """When marker is already off_left_service, the function finds it."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    _put_service(s, "andreas", 0)
    # Shifting right from off_left back onto Calendar
    new = _shift_service(s, "andreas", 2, "right")
    assert new == 2  # 0 + 2
    assert "andreas" in s.calendar.boxes[1].service_markers
