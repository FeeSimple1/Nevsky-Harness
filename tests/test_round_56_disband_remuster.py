"""Round 56 — SMOKE-044 regression tests.

A Lord Disbanded at limit (3.3.2) has their cylinder placed on a
future Calendar box. In subsequent Levies, when the Levy marker
reaches or passes that box, the Lord should be Ready to re-Muster.
The harness was leaving state='disbanded' forever, so _h_muster_lord
rejected the Lord with "state is disbanded (not 'ready')".

Fix: at start of each Muster step (in _h_advance_step's next_step ==
"muster" branch), transition state='disbanded' -> 'ready' for any
Lord whose cylinder is on the Calendar at or before the Levy marker.
"""

import nevsky.actions  # noqa
from nevsky.scenarios import load_scenario
from nevsky.actions import _disband_at_limit, apply_action


def _advance_to_muster_step(st):
    st.meta.phase = "levy"
    st.meta.levy_step = "disband"
    st.meta.active_player = "russian"
    st.meta.levy_step_completed_t = True
    st.meta.levy_step_completed_r = False
    apply_action(st, {"type": "advance_step", "side": "russian", "args": {}})


def _set_levy_marker(st, box):
    for cb in st.calendar.boxes:
        cb.has_levy_campaign_marker = False
        cb.levy_campaign_face = None
    st.calendar.boxes[box - 1].has_levy_campaign_marker = True
    st.calendar.boxes[box - 1].levy_campaign_face = "levy"
    st.meta.box = box


def test_disbanded_becomes_ready_when_levy_catches_up():
    st = load_scenario("pleskau", seed=1)
    _disband_at_limit(st, "hermann", 4)
    assert st.lords["hermann"].state == "disbanded"
    _set_levy_marker(st, 5)  # Levy now at 5, hermann cyl at 4
    _advance_to_muster_step(st)
    assert st.lords["hermann"].state == "ready"


def test_disbanded_stays_disbanded_when_in_future():
    """If the Lord's cylinder is past the Levy marker, they're not yet
    Ready and stay 'disbanded'."""
    st = load_scenario("pleskau", seed=1)
    _disband_at_limit(st, "hermann", 8)  # cylinder at box 8
    _set_levy_marker(st, 3)  # Levy at 3, hermann cyl at 8 (in future)
    _advance_to_muster_step(st)
    assert st.lords["hermann"].state == "disbanded"


def test_disbanded_at_off_left_becomes_ready():
    """A disbanded Lord with cylinder at off_left (0) is Ready (cylinder
    is BEFORE the marker)."""
    st = load_scenario("pleskau", seed=1)
    _disband_at_limit(st, "hermann", 4)
    # Manually move cylinder to off_left
    cal = st.calendar
    cal.boxes[3].cylinders.remove("hermann")
    cal.off_left.append("hermann")
    _set_levy_marker(st, 1)
    _advance_to_muster_step(st)
    assert st.lords["hermann"].state == "ready"


def test_mustered_lord_unchanged_by_muster_step_transition():
    """Already-Mustered Lords aren't affected by the disbanded->ready transition."""
    st = load_scenario("pleskau", seed=1)
    _set_levy_marker(st, 3)
    _advance_to_muster_step(st)
    # All initial Mustered Lords stay Mustered
    for lid, L in st.lords.items():
        if lid in ("hermann", "yaroslav", "knud_and_abel", "gavrilo", "vladislav"):
            assert L.state == "mustered"


def test_ready_lord_unchanged_by_transition():
    """Already-Ready Lords stay Ready (the transition is disbanded-specific)."""
    st = load_scenario("pleskau", seed=1)
    # Find a Ready Lord
    ready = next((lid for lid, L in st.lords.items() if L.state == "ready"), None)
    if ready is None:
        return
    _set_levy_marker(st, 3)
    _advance_to_muster_step(st)
    assert st.lords[ready].state == "ready"


def test_disbanded_lord_can_remuster_end_to_end():
    """Full integration: disband, advance Levy, then successfully Muster."""
    st = load_scenario("pleskau", seed=1)
    _disband_at_limit(st, "hermann", 4)
    _set_levy_marker(st, 5)
    _advance_to_muster_step(st)
    # Now Muster hermann via yaroslav
    st.meta.active_player = "teutonic"
    st.meta.levy_step_completed_t = False
    st.meta.levy_step_completed_r = False
    # Reset hermann's just_arrived flag so by_lord can act
    for L in st.lords.values():
        L.just_arrived_this_levy = False
    # Find a hermann seat
    from nevsky.actions import _free_seats_for
    free = _free_seats_for(st, "hermann")
    if not free:
        return  # scenario doesn't have free seats for hermann
    seat = free[0]
    # Use yaroslav as by_lord
    res = apply_action(st, {"type": "muster_lord", "side": "teutonic",
                           "args": {"by_lord": "yaroslav",
                                    "target_lord": "hermann",
                                    "seat": seat}})
    assert "outcome" in res or "target_lord" in res
