"""Round 32 — defensive bounds check on _disband_at_limit cylinder
placement.

SMOKE-018: prior to Round 32, `_disband_at_limit(state, lord_id, 0)`
silently placed the cylinder at box 16 via Python's negative indexing
(`cal.boxes[-1]`). Production paths today never compute a non-positive
target, so this never surfaced in normal play. Round 32 adds an
explicit clamp: target <= 0 -> off_left; target > 16 -> off_right.

These tests pin the new behavior so a future regression that allows
0/negative targets through still produces a sane state (cylinder
off-board to the left) rather than wrapping around.
"""
from __future__ import annotations

from nevsky.actions import _disband_at_limit
from nevsky.scenarios import load_scenario


def _setup_and_target():
    s = load_scenario("crusade_on_novgorod", seed=1)
    teu = next(
        lid for lid, l in s.lords.items()
        if l.side == "teutonic" and l.state == "mustered"
    )
    return s, teu


def _find_cyl_box(s, lid):
    if lid in s.calendar.off_left:
        return 0
    if lid in s.calendar.off_right:
        return 17
    for i, box in enumerate(s.calendar.boxes):
        if lid in box.cylinders:
            return i + 1
    return None


def test_disband_at_limit_box_zero_goes_to_off_left():
    s, teu = _setup_and_target()
    _disband_at_limit(s, teu, 0)
    assert teu in s.calendar.off_left
    # Must NOT have wrapped to box 16 via boxes[-1].
    assert teu not in s.calendar.boxes[15].cylinders


def test_disband_at_limit_negative_box_goes_to_off_left():
    s, teu = _setup_and_target()
    _disband_at_limit(s, teu, -5)
    assert teu in s.calendar.off_left
    # boxes[-6] would have been box 11; ensure not there.
    assert teu not in s.calendar.boxes[10].cylinders


def test_disband_at_limit_box_17_goes_to_off_right():
    s, teu = _setup_and_target()
    _disband_at_limit(s, teu, 17)
    assert teu in s.calendar.off_right


def test_disband_at_limit_box_in_range_works_normally():
    s, teu = _setup_and_target()
    _disband_at_limit(s, teu, 5)
    assert _find_cyl_box(s, teu) == 5


def test_disband_at_limit_box_16_max_in_range():
    s, teu = _setup_and_target()
    _disband_at_limit(s, teu, 16)
    assert _find_cyl_box(s, teu) == 16
