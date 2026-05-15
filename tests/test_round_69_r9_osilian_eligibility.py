"""SMOKE-063 (Round 69): R9 Osilian Revolt eligibility + clamp.

AoW Reference R9 Tip:
- "shift the Service marker ... by 2 boxes to the degree able"
- "as long as neither marker is yet in box 1 or off the left end of
  the Calendar"

R9 lacks the "1 box off Calendar from box 1 is allowed" allowance that
R10/T12/T18 Tips carry. So the target's Service marker must be in box
>= 2, and the shift is clamped to keep the marker at box >= 1.
"""
from __future__ import annotations

import pytest

from nevsky.actions import IllegalAction
from nevsky.events import _ev_osilian_revolt
from nevsky.scenarios import load_scenario


def _put_service(state, lord_id, box):
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


def test_r9_rejects_box_1_target():
    s = load_scenario("crusade_on_novgorod", seed=1)
    _put_service(s, "andreas", 1)
    with pytest.raises(IllegalAction) as e:
        _ev_osilian_revolt(s, {"target": "andreas"})
    assert e.value.code == "ineligible_target"


def test_r9_rejects_off_left_target():
    s = load_scenario("crusade_on_novgorod", seed=1)
    _put_service(s, "andreas", 0)
    with pytest.raises(IllegalAction) as e:
        _ev_osilian_revolt(s, {"target": "andreas"})
    assert e.value.code == "ineligible_target"


def test_r9_rejects_no_marker_target():
    """Lord with no Service marker on Calendar (e.g. permanently removed)."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    cal = s.calendar
    for cb in cal.boxes:
        if "andreas" in cb.service_markers:
            cb.service_markers.remove("andreas")
    if "andreas" in cal.off_left_service:
        cal.off_left_service.remove("andreas")
    if "andreas" in cal.off_right_service:
        cal.off_right_service.remove("andreas")
    with pytest.raises(IllegalAction) as e:
        _ev_osilian_revolt(s, {"target": "andreas"})
    assert e.value.code == "ineligible_target"


def test_r9_clamps_at_box_1_from_box_2():
    """From box 2, shift 2 left clamps at box 1 (no off-Calendar allowance for R9)."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    _put_service(s, "andreas", 2)
    r = _ev_osilian_revolt(s, {"target": "andreas"})
    assert r["new_box"] == 1
    assert "andreas" in s.calendar.boxes[0].service_markers
    assert "andreas" not in s.calendar.off_left_service


def test_r9_full_shift_from_box_3():
    s = load_scenario("crusade_on_novgorod", seed=1)
    _put_service(s, "andreas", 3)
    r = _ev_osilian_revolt(s, {"target": "andreas"})
    assert r["new_box"] == 1


def test_r9_full_shift_from_box_5():
    s = load_scenario("crusade_on_novgorod", seed=1)
    _put_service(s, "andreas", 5)
    r = _ev_osilian_revolt(s, {"target": "andreas"})
    assert r["new_box"] == 3


def test_r9_rejects_invalid_target_id():
    s = load_scenario("crusade_on_novgorod", seed=1)
    with pytest.raises(IllegalAction) as e:
        _ev_osilian_revolt(s, {"target": "hermann"})
    assert e.value.code == "missing_arg"
