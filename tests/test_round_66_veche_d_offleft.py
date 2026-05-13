"""Round 66 — SMOKE-058 regression tests.

Veche option D (Decline) slides Aleksandr / Andrey 1 box right and
adds 1 VP. The cylinder-position iteration didn't handle off_left
(cyl_box=0): the `cyl_box <= 16` branch tried `boxes[-1]` and crashed
with ValueError because the Lord was in cal.off_left.
"""

import nevsky.actions  # noqa
from nevsky.scenarios import load_scenario
from nevsky.actions import apply_action, _find_cylinder_box


def test_veche_d_aleksandr_at_off_left():
    """Aleksandr cylinder at off_left should be moved to box 1 (levy+1)."""
    st = load_scenario("watland", seed=1)
    # Move aleksandr to off_left
    for cb in st.calendar.boxes:
        if "aleksandr" in cb.cylinders:
            cb.cylinders.remove("aleksandr")
    st.calendar.off_left.append("aleksandr")
    st.lords["aleksandr"].state = "ready"
    # Disable andrey so D fires for aleksandr only
    st.lords["andrey"].state = "removed"
    st.meta.phase = "levy"
    st.meta.levy_step = "call_to_arms"
    st.meta.active_player = "russian"
    res = apply_action(st, {"type": "veche_action", "side": "russian",
                           "args": {"option": "D"}})
    assert "aleksandr" in res["slid"]
    # Aleksandr no longer at off_left
    assert "aleksandr" not in st.calendar.off_left
    # Aleksandr now at levy_box + 1
    cb_new = _find_cylinder_box(st, "aleksandr")
    assert cb_new == st.meta.box + 1


def test_veche_d_at_box_keeps_working():
    """Sanity: non-off_left case still works."""
    st = load_scenario("watland", seed=1)
    # Move andrey cylinder to box 1 (Levy at 4) so andrey is Ready
    for cb in st.calendar.boxes:
        if "andrey" in cb.cylinders:
            cb.cylinders.remove("andrey")
    st.calendar.boxes[0].cylinders.append("andrey")
    st.lords["aleksandr"].state = "removed"
    st.meta.phase = "levy"
    st.meta.levy_step = "call_to_arms"
    st.meta.active_player = "russian"
    res = apply_action(st, {"type": "veche_action", "side": "russian",
                           "args": {"option": "D"}})
    assert "andrey" in res["slid"]
