"""Round 50 — SMOKE-038 regression tests.

When a Lord is permanently removed (3.3.1) or Disbanded at limit
(3.3.2), any Vassal Service markers belonging to that Lord must be
removed from the Calendar's per-box vassal_service_markers lists.
The harness previously cleared the per-vassal flags
(VassalState.on_calendar / calendar_box) but left the Calendar's
list pointing at stale ids — a desync bug only surfaced under the
Advanced Vassal Service optional rule.
"""

from nevsky.scenarios import load_scenario
from nevsky.actions import _disband_at_limit, _remove_lord_permanently
from nevsky.static_data import load_lords


def _place_vassal_on_calendar(st, lord_id, vid, box):
    """Test helper: place a Lord's vassal at a Calendar box."""
    L = st.lords[lord_id]
    v = L.vassals[vid]
    v.mustered = True
    v.on_calendar = True
    v.calendar_box = box
    st.calendar.boxes[box - 1].vassal_service_markers.append(vid)


def test_disband_clears_vassal_calendar_marker():
    """_disband_at_limit must remove the vassal from the Calendar list."""
    st = load_scenario("pleskau", seed=1)
    st.meta.optional_rules["advanced_vassal_service"] = True
    vid = next(iter(st.lords["hermann"].vassals))
    _place_vassal_on_calendar(st, "hermann", vid, 8)
    _disband_at_limit(st, "hermann", 4)
    assert vid not in st.calendar.boxes[7].vassal_service_markers
    assert st.lords["hermann"].vassals[vid].on_calendar is False
    assert st.lords["hermann"].vassals[vid].calendar_box is None


def test_remove_lord_permanently_clears_vassal_calendar_marker():
    """_remove_lord_permanently must remove the vassal from the Calendar."""
    st = load_scenario("pleskau", seed=1)
    st.meta.optional_rules["advanced_vassal_service"] = True
    vid = next(iter(st.lords["hermann"].vassals))
    _place_vassal_on_calendar(st, "hermann", vid, 8)
    _remove_lord_permanently(st, "hermann", load_lords()["hermann"])
    assert vid not in st.calendar.boxes[7].vassal_service_markers


def test_disband_with_multiple_vassals_on_calendar():
    """Two vassals at different boxes both get cleaned up."""
    st = load_scenario("pleskau", seed=1)
    st.meta.optional_rules["advanced_vassal_service"] = True
    vids = list(st.lords["hermann"].vassals)
    if len(vids) < 2:
        return  # scenario doesn't have enough vassals; OK
    _place_vassal_on_calendar(st, "hermann", vids[0], 4)
    _place_vassal_on_calendar(st, "hermann", vids[1], 12)
    _disband_at_limit(st, "hermann", 4)
    assert vids[0] not in st.calendar.boxes[3].vassal_service_markers
    assert vids[1] not in st.calendar.boxes[11].vassal_service_markers


def test_disband_with_no_vassals_on_calendar_no_crash():
    """Lords without vassals on the Calendar disband cleanly."""
    st = load_scenario("pleskau", seed=1)
    st.meta.optional_rules["advanced_vassal_service"] = True
    # Make sure no vassals are on Calendar (the default state)
    for v in st.lords["hermann"].vassals.values():
        assert not v.on_calendar  # default
    # Should not raise
    _disband_at_limit(st, "hermann", 4)
    assert st.lords["hermann"].state == "disbanded"
