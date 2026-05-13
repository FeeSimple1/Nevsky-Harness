"""Round 65 — SMOKE-057 regression tests.

apply_retreat_service_shift looks for the Lord's Service marker in
cal.boxes[*].service_markers, then falls back to a list for "past the
right edge." Previously the fallback consulted cal.off_right (the
CYLINDER list) instead of cal.off_right_service (the SERVICE MARKER
list). A Lord with Service at off_right_service skipped the shift.
"""

import nevsky.actions  # noqa
from nevsky.scenarios import load_scenario
from nevsky.battle import apply_retreat_service_shift


def test_retreat_shift_from_off_right_service():
    """Service at off_right_service shifts back onto Calendar."""
    st = load_scenario("pleskau", seed=1)
    # Move hermann's Service marker to off_right_service
    for cb in st.calendar.boxes:
        if "hermann" in cb.service_markers:
            cb.service_markers.remove("hermann")
    st.calendar.off_right_service.append("hermann")
    shift = apply_retreat_service_shift(st, "hermann")
    # Per the SERVICE_SHIFT_TABLE (die_to_boxes), the shift is 1..3.
    # After shift, hermann should be ON Calendar (no longer off_right_service).
    assert shift in (1, 2, 3)
    assert "hermann" not in st.calendar.off_right_service
    # Lord should be at some box now (17 - shift = 14..16)
    found = False
    for cb in st.calendar.boxes:
        if "hermann" in cb.service_markers:
            found = True
            assert cb.box == 17 - shift
    assert found


def test_retreat_shift_does_not_consult_cylinder_off_right():
    """Cylinder at off_right (different list) doesn't interfere with shift."""
    st = load_scenario("pleskau", seed=1)
    # Pretend hermann's CYLINDER is at off_right (unusual but possible)
    if "hermann" in st.calendar.off_right:
        pass  # already there
    else:
        st.calendar.off_right.append("hermann")
    # Service marker is at box 4
    for cb in st.calendar.boxes:
        if "hermann" in cb.service_markers:
            cb.service_markers.remove("hermann")
    st.calendar.boxes[3].service_markers.append("hermann")
    shift = apply_retreat_service_shift(st, "hermann")
    # Service shift should still fire (not be confused by cylinder location)
    assert shift in (1, 2, 3)
    # Cylinder still at off_right (untouched)
    assert "hermann" in st.calendar.off_right


def test_retreat_shift_returns_zero_when_no_service_marker():
    """Lord with no Service marker on Calendar → shift returns 0."""
    st = load_scenario("pleskau", seed=1)
    # Remove hermann's Service marker entirely
    for cb in st.calendar.boxes:
        if "hermann" in cb.service_markers:
            cb.service_markers.remove("hermann")
    # not in off_right_service either
    if "hermann" in st.calendar.off_right_service:
        st.calendar.off_right_service.remove("hermann")
    shift = apply_retreat_service_shift(st, "hermann")
    assert shift == 0
