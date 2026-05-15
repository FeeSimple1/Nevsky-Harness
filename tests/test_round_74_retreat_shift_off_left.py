"""SMOKE-070 (Round 74): Retreat service shift must support off_left_service
landings (matching SMOKE-062's _shift_service semantics).

When a Retreating Lord's Service marker is near box 1 and the d6 shift
carries it past box 1, the marker lands on off_left_service. Marker
there triggers 3.3.1 permanent removal at the next Disband. Previously
apply_retreat_service_shift clamped at box 1.
"""
from __future__ import annotations

import random

import nevsky.actions  # noqa: F401
from nevsky.battle import apply_retreat_service_shift
from nevsky.scenarios import load_scenario


def _put_service(state, lord_id, where):
    cal = state.calendar
    for cb in cal.boxes:
        if lord_id in cb.service_markers:
            cb.service_markers.remove(lord_id)
    if lord_id in cal.off_left_service:
        cal.off_left_service.remove(lord_id)
    if lord_id in cal.off_right_service:
        cal.off_right_service.remove(lord_id)
    if where == "off_left":
        cal.off_left_service.append(lord_id)
    elif where == "off_right":
        cal.off_right_service.append(lord_id)
    else:
        cal.boxes[where - 1].service_markers.append(lord_id)


def test_retreat_shift_from_box_1_goes_off_left_service():
    """Any d6 shift >= 1 from box 1 lands on off_left_service."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    _put_service(s, "hermann", 1)
    apply_retreat_service_shift(s, "hermann")
    assert "hermann" in s.calendar.off_left_service
    for cb in s.calendar.boxes:
        assert "hermann" not in cb.service_markers


def test_retreat_shift_from_box_2_goes_off_left_on_large_shift():
    """seed gives shift table values; from box 2, any shift >= 2 lands
    on off_left_service. Use a seed that produces a high d6 to make
    the shift deterministic."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    _put_service(s, "hermann", 2)
    boxes = apply_retreat_service_shift(s, "hermann")
    if boxes >= 2:
        assert "hermann" in s.calendar.off_left_service
    else:
        # shift 0 or 1 leaves marker on Calendar at box >= 1
        found = False
        for cb in s.calendar.boxes:
            if "hermann" in cb.service_markers:
                assert cb.box >= 1
                found = True
                break
        assert found or "hermann" in s.calendar.off_left_service


def test_retreat_shift_from_off_left_stays_off_left():
    """Marker already at off_left_service stays there (capped one box off)."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    _put_service(s, "hermann", "off_left")
    apply_retreat_service_shift(s, "hermann")
    # Even if shift is positive, marker stays at off_left_service.
    assert "hermann" in s.calendar.off_left_service


def test_retreat_shift_from_off_right_handled():
    """Marker at off_right_service still gets handled (SMOKE-057 path).
    Off-right is cur=17; small shift lands within boxes."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    _put_service(s, "hermann", "off_right")
    boxes = apply_retreat_service_shift(s, "hermann")
    if boxes > 0:
        # Marker landed somewhere; if shift was small (1..6 mapped via
        # _SERVICE_SHIFT_TABLE values 0..3), should be on Calendar.
        in_cal = any("hermann" in cb.service_markers for cb in s.calendar.boxes)
        on_off = ("hermann" in s.calendar.off_right_service
                  or "hermann" in s.calendar.off_left_service)
        assert in_cal or on_off
