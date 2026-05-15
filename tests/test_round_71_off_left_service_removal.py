"""Round 71 — regression coverage for the off_left_service permanent-
removal path opened by SMOKE-062 (Round 68).

Per rule 3.3.1: any Lord whose Service marker is LEFT of the Levy
marker box must be permanently removed. SMOKE-062 (Round 68) made
off_left_service reachable via _shift_service. Prior to that fix,
Service markers couldn't actually leave box 1 to the left. Now both
3.3.1 (Levy Disband) and 4.8.2 (Campaign FPD Disband) must cleanly
permanently-remove a Lord whose marker is at off_left_service (box 0).
"""
from __future__ import annotations

import nevsky.actions  # noqa: F401 — handler registration

from nevsky.actions import apply_action
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


def test_levy_disband_permanent_remove_from_off_left_service():
    """3.3.1: Lord whose Service marker is at off_left_service is
    permanently removed when the Disband step resolves."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    # Ensure hermann is Mustered and his service marker is off_left.
    hermann = s.lords["hermann"]
    hermann.state = "mustered"
    hermann.location = "dorpat"
    _put_service(s, "hermann", "off_left")

    # Advance to Disband step (arts_of_war -> pay -> disband)
    for _ in range(2):
        apply_action(s, {"type": "advance_step", "side": "teutonic"})
        apply_action(s, {"type": "advance_step", "side": "russian"})
    assert s.meta.levy_step == "disband"

    r = apply_action(s, {"type": "disband_resolve", "side": "teutonic"})
    assert "hermann" in r["permanently_removed"]
    assert s.lords["hermann"].state == "removed"
    # off_left_service cleared on permanent removal
    assert "hermann" not in s.calendar.off_left_service


def test_levy_disband_at_levy_box_disbands_not_removes():
    """3.3.2 contrast: marker AT the Levy box -> at-limit Disband
    (not permanent remove)."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    hermann = s.lords["hermann"]
    hermann.state = "mustered"
    hermann.location = "dorpat"
    # Levy is at box 1; place marker AT box 1.
    _put_service(s, "hermann", 1)

    for _ in range(2):
        apply_action(s, {"type": "advance_step", "side": "teutonic"})
        apply_action(s, {"type": "advance_step", "side": "russian"})
    assert s.meta.levy_step == "disband"

    r = apply_action(s, {"type": "disband_resolve", "side": "teutonic"})
    assert "hermann" not in r["permanently_removed"]
    assert any(d["lord_id"] == "hermann" for d in r["disbanded"])
    assert s.lords["hermann"].state == "disbanded"
