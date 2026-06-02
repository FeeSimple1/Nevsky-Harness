"""Off-Calendar Vassal Service markers are rostered (rule 2.2.3 parity
with Lord off_*_service), not encoded as an out-of-range calendar_box.

Previously a Vassal shifted past the right (or left) edge was stored as
calendar_box = 17 (or 0) -- values outside the field's declared 1..16
range (they slipped past validation only because pydantic does not
re-validate on attribute assignment), and the marker appeared in no
Calendar-level roster. Now off-edge markers set calendar_box=None and
join calendar.off_right_vassal / off_left_vassal, and the effective
position is read via vassal_marker_box (1..16 / 17 / 0).
"""
from __future__ import annotations

from nevsky.actions import _disband_at_limit, _shift_service_right
from nevsky.scenarios import load_scenario
from nevsky.state import (
    clear_vassal_marker,
    move_vassal_marker,
    vassal_marker_box,
)


def _place_vassal(st, lord_id, vid, box):
    v = st.lords[lord_id].vassals[vid]
    v.mustered = True
    v.on_calendar = True
    v.calendar_box = box
    st.calendar.boxes[box - 1].vassal_service_markers.append(vid)


def test_move_vassal_marker_off_right_and_back():
    st = load_scenario("pleskau", seed=1)
    cal = st.calendar
    vid = next(iter(st.lords["hermann"].vassals))
    vstate = st.lords["hermann"].vassals[vid]
    _place_vassal(st, "hermann", vid, 15)

    # Shift off the right edge.
    eff = move_vassal_marker(cal, vid, vstate, 18)
    assert eff == 17
    assert vid in cal.off_right_vassal
    assert vstate.calendar_box is None          # valid (1..16) constraint kept
    assert vstate.on_calendar is True
    assert vassal_marker_box(cal, vid, vstate) == 17
    assert vid not in cal.boxes[14].vassal_service_markers

    # Shift back onto the track (17 - 4 = 13).
    eff2 = move_vassal_marker(cal, vid, vstate, vassal_marker_box(cal, vid, vstate) - 4)
    assert eff2 == 13
    assert vid not in cal.off_right_vassal
    assert vstate.calendar_box == 13
    assert vid in cal.boxes[12].vassal_service_markers


def test_move_vassal_marker_off_left():
    st = load_scenario("pleskau", seed=1)
    cal = st.calendar
    vid = next(iter(st.lords["hermann"].vassals))
    vstate = st.lords["hermann"].vassals[vid]
    _place_vassal(st, "hermann", vid, 2)
    eff = move_vassal_marker(cal, vid, vstate, 0)
    assert eff == 0
    assert vid in cal.off_left_vassal
    assert vstate.calendar_box is None
    assert vassal_marker_box(cal, vid, vstate) == 0


def test_clear_and_detach_remove_from_roster():
    st = load_scenario("pleskau", seed=1)
    cal = st.calendar
    vid = next(iter(st.lords["hermann"].vassals))
    vstate = st.lords["hermann"].vassals[vid]
    _place_vassal(st, "hermann", vid, 16)
    move_vassal_marker(cal, vid, vstate, 20)        # off-right
    assert vid in cal.off_right_vassal
    clear_vassal_marker(cal, vid, vstate)
    assert vid not in cal.off_right_vassal
    assert vstate.on_calendar is False
    assert vstate.calendar_box is None


def test_shift_service_right_carries_vassal_off_right_into_roster():
    st = load_scenario("pleskau", seed=1)
    st.meta.optional_rules["advanced_vassal_service"] = True
    cal = st.calendar
    # Lord service marker on the track so _shift_service_right can act.
    cal.boxes[13].service_markers.append("hermann")  # box 14
    vid = next(iter(st.lords["hermann"].vassals))
    vstate = st.lords["hermann"].vassals[vid]
    _place_vassal(st, "hermann", vid, 14)

    _shift_service_right(st, "hermann", 5)            # 14 + 5 = 19 -> off-right
    assert vid in cal.off_right_vassal
    assert vstate.calendar_box is None                # constraint (1..16) intact
    assert vstate.on_calendar is True
    assert vassal_marker_box(cal, vid, vstate) == 17


def test_disband_clears_off_right_vassal_roster():
    st = load_scenario("pleskau", seed=1)
    st.meta.optional_rules["advanced_vassal_service"] = True
    cal = st.calendar
    vid = next(iter(st.lords["hermann"].vassals))
    vstate = st.lords["hermann"].vassals[vid]
    _place_vassal(st, "hermann", vid, 16)
    move_vassal_marker(cal, vid, vstate, 19)          # off-right
    assert vid in cal.off_right_vassal
    _disband_at_limit(st, "hermann", 1)
    assert vid not in cal.off_right_vassal             # roster cleaned up
