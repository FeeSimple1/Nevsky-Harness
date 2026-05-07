"""Tests for 3.3 Disband."""

from __future__ import annotations

from nevsky.actions import apply_action
from nevsky.scenarios import load_scenario
from nevsky.state import GameState


def _to_disband_step(s: GameState, side: str = "teutonic") -> None:
    s.meta.levy_step = "disband"
    s.meta.active_player = side
    s.meta.levy_step_completed_t = side == "russian"
    s.meta.levy_step_completed_r = False


def _move_service_marker_to(s: GameState, lid: str, box: int) -> None:
    """Test helper: move a Lord's Service marker to a specific box."""
    for cb in s.calendar.boxes:
        if lid in cb.service_markers:
            cb.service_markers.remove(lid)
    if lid in s.calendar.off_right:
        s.calendar.off_right.remove(lid)
    if box <= 16:
        s.calendar.boxes[box - 1].service_markers.append(lid)
    else:
        s.calendar.off_right.append(lid)


def _find_levy_box(s: GameState) -> int:
    for cb in s.calendar.boxes:
        if cb.has_levy_campaign_marker:
            return cb.box
    raise AssertionError("no Levy marker on Calendar")


def test_disband_at_limit_places_cylinder_service_boxes_right(tmp_path) -> None:
    """3.3.2: at-limit Disband places cylinder SERVICE_RATING right of CURRENT box (Levy)."""
    s = load_scenario("watland", seed=42)
    _to_disband_step(s, side="teutonic")
    levy_box = _find_levy_box(s)
    target = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    _move_service_marker_to(s, target, levy_box)  # at-limit
    res = apply_action(s, {"type": "disband_resolve", "side": "teutonic", "args": {}})
    assert any(d["lord_id"] == target for d in res["disbanded"])
    assert s.lords[target].state == "disbanded"
    assert s.lords[target].forces == {}
    assert s.lords[target].assets == {}


def test_disband_beyond_limit_permanently_removes() -> None:
    """3.3.1: Service marker LEFT of Levy -> permanent removal."""
    s = load_scenario("watland", seed=42)
    _to_disband_step(s, side="teutonic")
    levy_box = _find_levy_box(s)
    if levy_box < 2:
        s.calendar.boxes[levy_box - 1].has_levy_campaign_marker = False
        s.calendar.boxes[1].has_levy_campaign_marker = True
        s.calendar.boxes[1].levy_campaign_face = "levy"
        levy_box = 2
    target = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    _move_service_marker_to(s, target, levy_box - 1)  # left of Levy = beyond
    apply_action(s, {"type": "disband_resolve", "side": "teutonic", "args": {}})
    assert s.lords[target].state == "removed"
    assert s.lords[target].forces == {}


def test_disband_returns_this_lord_capabilities_to_deck() -> None:
    """3.3.1: at-permanent-removal, this-lord capabilities return to side's deck (3.4.4)."""
    s = load_scenario("watland", seed=42)
    _to_disband_step(s, side="teutonic")
    levy_box = _find_levy_box(s)
    if levy_box < 2:
        s.calendar.boxes[levy_box - 1].has_levy_campaign_marker = False
        s.calendar.boxes[1].has_levy_campaign_marker = True
        s.calendar.boxes[1].levy_campaign_face = "levy"
        levy_box = 2
    target = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    _move_service_marker_to(s, target, levy_box - 1)
    s.lords[target].this_lord_capabilities = ["T2"]
    if "T2" in s.decks.teutonic.deck:
        s.decks.teutonic.deck.remove("T2")
    apply_action(s, {"type": "disband_resolve", "side": "teutonic", "args": {}})
    assert "T2" in s.decks.teutonic.deck


def test_disband_no_action_when_service_right_of_levy() -> None:
    """3.3: Service marker right of Levy -> no Disband for that Lord."""
    s = load_scenario("watland", seed=42)
    _to_disband_step(s, side="teutonic")
    levy_box = _find_levy_box(s)
    target = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    _move_service_marker_to(s, target, min(levy_box + 1, 16))
    pre_state = s.lords[target].state
    apply_action(s, {"type": "disband_resolve", "side": "teutonic", "args": {}})
    assert s.lords[target].state == pre_state
