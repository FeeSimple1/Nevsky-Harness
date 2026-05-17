"""SMOKE-103 (Round 139): apply_retreat_service_shift didn't shift
Vassal Service markers under advanced_vassal_service.

Per Battle and Storm reference service_shift_on_retreat block:
  "vassals_shift": "only under advanced Vassal Service rule (3.4.2)"
  "shift each Vassal's marker the same number, ONLY under advanced
   Vassal Service rule"

Pre-fix the Pay-step shift (`_shift_service_right` in actions.py)
already cascaded the same shift onto on-Calendar vassal markers, but
the Retreat-shift in battle.py was missing this cascade.

Same audit pattern as SMOKE-098/099/101 (mirror gap between sibling
service-shift paths).

Fix applies the same direction (LEFT) and magnitude to every on-
Calendar vassal marker of the retreating Lord.
"""
from __future__ import annotations

import inspect

import nevsky.actions  # noqa: F401
import nevsky.battle as battle


def test_smoke_103_marker_present():
    src = inspect.getsource(battle.apply_retreat_service_shift)
    assert "SMOKE-103" in src
    assert "advanced_vassal_service" in src


def test_smoke_103_no_shift_when_optional_rule_off():
    """Without advanced_vassal_service, vassal markers are NOT touched."""
    from nevsky.scenarios import load_scenario
    s = load_scenario("watland", seed=1)
    s.meta.optional_rules["advanced_vassal_service"] = False

    # Find a Lord with vassals and put a vassal marker on Calendar.
    teu = next(lid for lid, l in s.lords.items()
               if l.side == "teutonic" and l.vassals)
    vid = next(iter(s.lords[teu].vassals))
    s.lords[teu].vassals[vid].on_calendar = True
    s.lords[teu].vassals[vid].calendar_box = 8
    # Clear any existing marker
    for cb in s.calendar.boxes:
        if vid in cb.vassal_service_markers:
            cb.vassal_service_markers.remove(vid)
    s.calendar.boxes[7].vassal_service_markers.append(vid)

    # Put Lord's Service marker at box 8.
    for cb in s.calendar.boxes:
        if teu in cb.service_markers:
            cb.service_markers.remove(teu)
    s.calendar.boxes[7].service_markers.append(teu)

    battle.apply_retreat_service_shift(s, teu)

    # With optional rule OFF, vassal stays at box 8.
    assert s.lords[teu].vassals[vid].calendar_box == 8
    assert vid in s.calendar.boxes[7].vassal_service_markers


def test_smoke_103_shifts_vassal_marker_left_when_optional_rule_on():
    """With advanced_vassal_service on, vassal marker shifts left
    by the same boxes as the Lord's service shift."""
    from nevsky.scenarios import load_scenario
    s = load_scenario("watland", seed=1)
    s.meta.optional_rules["advanced_vassal_service"] = True

    teu = next(lid for lid, l in s.lords.items()
               if l.side == "teutonic" and l.vassals)
    vid = next(iter(s.lords[teu].vassals))
    s.lords[teu].vassals[vid].on_calendar = True
    s.lords[teu].vassals[vid].calendar_box = 10
    for cb in s.calendar.boxes:
        if vid in cb.vassal_service_markers:
            cb.vassal_service_markers.remove(vid)
    s.calendar.boxes[9].vassal_service_markers.append(vid)

    for cb in s.calendar.boxes:
        if teu in cb.service_markers:
            cb.service_markers.remove(teu)
    s.calendar.boxes[9].service_markers.append(teu)  # box 10

    shift = battle.apply_retreat_service_shift(s, teu)

    expected_v_box = 10 - shift
    assert s.lords[teu].vassals[vid].calendar_box == expected_v_box
    assert vid in s.calendar.boxes[expected_v_box - 1].vassal_service_markers


def test_smoke_103_vassal_off_calendar_left_sentinel():
    """If shift takes vassal past box 1, calendar_box is set to 0
    sentinel (matching _shift_service_right convention)."""
    from nevsky.scenarios import load_scenario
    s = load_scenario("watland", seed=1)
    s.meta.optional_rules["advanced_vassal_service"] = True

    teu = next(lid for lid, l in s.lords.items()
               if l.side == "teutonic" and l.vassals)
    vid = next(iter(s.lords[teu].vassals))
    s.lords[teu].vassals[vid].on_calendar = True
    s.lords[teu].vassals[vid].calendar_box = 2
    for cb in s.calendar.boxes:
        if vid in cb.vassal_service_markers:
            cb.vassal_service_markers.remove(vid)
    s.calendar.boxes[1].vassal_service_markers.append(vid)

    for cb in s.calendar.boxes:
        if teu in cb.service_markers:
            cb.service_markers.remove(teu)
    s.calendar.boxes[1].service_markers.append(teu)  # box 2

    # Force a seed where dice roll lands shift >= 2 to push vassal off-left.
    # The seed-controlled rng is deterministic; using a few seeds
    # exercises shifts 1-3. With box 2 + shift >= 2 we land at <=0.
    # Try several attempts to find a shift >= 2.
    import random
    base_rng_state = s.meta.rng_state
    for attempt in range(20):
        s.meta.rng_state = base_rng_state + attempt
        # Restore positions
        for cb in s.calendar.boxes:
            if vid in cb.vassal_service_markers:
                cb.vassal_service_markers.remove(vid)
            if teu in cb.service_markers:
                cb.service_markers.remove(teu)
        s.lords[teu].vassals[vid].on_calendar = True
        s.lords[teu].vassals[vid].calendar_box = 2
        s.calendar.boxes[1].vassal_service_markers.append(vid)
        s.calendar.boxes[1].service_markers.append(teu)
        shift = battle.apply_retreat_service_shift(s, teu)
        if shift >= 2:
            assert s.lords[teu].vassals[vid].calendar_box == 0
            return
    # If we never get shift >= 2 in 20 attempts the test setup is broken.
    raise AssertionError("did not find a seed with shift >= 2")


def test_smoke_103_vassal_not_on_calendar_skipped():
    """Vassals with on_calendar=False are not modified."""
    from nevsky.scenarios import load_scenario
    s = load_scenario("watland", seed=1)
    s.meta.optional_rules["advanced_vassal_service"] = True

    teu = next(lid for lid, l in s.lords.items()
               if l.side == "teutonic" and l.vassals)
    vid = next(iter(s.lords[teu].vassals))
    s.lords[teu].vassals[vid].on_calendar = False
    s.lords[teu].vassals[vid].calendar_box = None

    for cb in s.calendar.boxes:
        if teu in cb.service_markers:
            cb.service_markers.remove(teu)
    s.calendar.boxes[7].service_markers.append(teu)

    battle.apply_retreat_service_shift(s, teu)

    # Still off Calendar with no box.
    assert s.lords[teu].vassals[vid].on_calendar is False
    assert s.lords[teu].vassals[vid].calendar_box is None
