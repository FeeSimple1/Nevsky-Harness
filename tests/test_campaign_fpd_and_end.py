"""Tests for 4.8 Feed/Pay/Disband cycle and 4.9 End Campaign."""

from __future__ import annotations

from nevsky.actions import apply_action
from nevsky.campaign import _plan_target_size
from nevsky.scenarios import load_scenario
from nevsky.state import GameState


def _set_levy_marker_box(s: GameState, box: int) -> None:
    for cb in s.calendar.boxes:
        if cb.has_levy_campaign_marker:
            cb.has_levy_campaign_marker = False
            cb.levy_campaign_face = None
    s.calendar.boxes[box - 1].has_levy_campaign_marker = True
    s.calendar.boxes[box - 1].levy_campaign_face = "campaign"


def _put_service_at(s: GameState, lord_id: str, box: int) -> None:
    for cb in s.calendar.boxes:
        if lord_id in cb.service_markers:
            cb.service_markers.remove(lord_id)
    if lord_id in s.calendar.off_right:
        s.calendar.off_right.remove(lord_id)
    if 1 <= box <= 16:
        s.calendar.boxes[box - 1].service_markers.append(lord_id)
    elif box >= 17:
        s.calendar.off_right.append(lord_id)


def _enter_fpd(s: GameState) -> None:
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "teutonic"
    s.campaign_turn.in_feed_pay_disband = True
    s.campaign_turn.fpd_completed_t = False
    s.campaign_turn.fpd_completed_r = False


def test_feed_consumes_provender_for_moved_fought_lord() -> None:
    """4.8.1: Feed costs 1 P/L for 1-6 units; consume own first."""
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].moved_fought = True
    s.lords[teu].assets["provender"] = 3
    _enter_fpd(s)
    res = apply_action(s, {"type": "fpd_resolve", "side": "teutonic", "args": {}})
    feed = next(f for f in res["feed"] if f["lord_id"] == teu)
    assert feed["consumed"]["provender"] >= 1
    assert s.lords[teu].assets.get("provender", 0) <= 2  # consumed at least 1


def test_feed_unfed_shifts_service_left() -> None:
    """4.8.1: Lord without enough Provender/Loot loses 1 box of Service."""
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].moved_fought = True
    s.lords[teu].assets.pop("provender", None)
    s.lords[teu].assets.pop("loot", None)
    # Place service marker far enough right that shift-left doesn't trigger Disband.
    _set_levy_marker_box(s, 4)
    _put_service_at(s, teu, 10)
    _enter_fpd(s)
    apply_action(s, {"type": "fpd_resolve", "side": "teutonic", "args": {}})
    # Service marker now at box 9.
    found = any(teu in cb.service_markers for cb in s.calendar.boxes if cb.box == 9)
    assert found


def test_fpd_at_limit_disband_counts_from_next_box_during_campaign() -> None:
    """4.8.2 + 3.3.2 (2E): at-limit Disband during Campaign places cylinder
    SERVICE_RATING boxes right of NEXT box."""
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    _set_levy_marker_box(s, 5)
    _put_service_at(s, teu, 5)  # at limit
    s.lords[teu].moved_fought = False  # only Disband path matters
    s.lords[teu].assets.pop("provender", None)
    s.lords[teu].assets.pop("loot", None)
    _enter_fpd(s)
    res = apply_action(s, {"type": "fpd_resolve", "side": "teutonic", "args": {}})
    from nevsky.static_data import load_lords
    srating = int(load_lords()[teu]["ratings"]["service"])
    expected = 5 + 1 + srating  # current 5 + count from NEXT (6) + service rating
    matched = next(d for d in res["disbanded"] if d["lord_id"] == teu)
    assert matched["new_box"] == min(expected, 17)


def test_fpd_remove_moved_fought_markers() -> None:
    """4.8.3: end-of-card removes MOVED_FOUGHT markers."""
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].moved_fought = True
    s.lords[teu].assets["provender"] = 5
    _enter_fpd(s)
    apply_action(s, {"type": "fpd_resolve", "side": "teutonic", "args": {}})
    assert s.lords[teu].moved_fought is False


def _enter_end_campaign(s: GameState) -> None:
    s.meta.phase = "campaign"
    s.meta.campaign_step = "end_campaign"
    s.meta.active_player = "teutonic"
    s.meta.end_campaign_completed_t = False
    s.meta.end_campaign_completed_r = False
    # Empty plans.
    s.decks.teutonic.plan = []
    s.decks.russian.plan = []


def test_end_campaign_advance_box_and_flip_to_levy() -> None:
    """4.9.5 (simplified): both sides resolve End Campaign; advance to next box
    and flip Levy/Campaign marker; meta.phase returns to 'levy'."""
    s = load_scenario("watland", seed=1)
    pre_box = s.meta.box
    _enter_end_campaign(s)
    apply_action(s, {"type": "end_campaign_resolve", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "end_campaign_resolve", "side": "russian", "args": {}})
    assert s.meta.box == pre_box + 1
    assert s.meta.phase == "levy"
    assert s.meta.levy_step == "arts_of_war"
    # Levy/Campaign marker on the new box.
    assert s.calendar.boxes[pre_box].has_levy_campaign_marker is True


def test_end_campaign_wastage_discards_excess_assets() -> None:
    """4.9.4: Lord with >1 of any asset type discards 1."""
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].assets["provender"] = 4
    pre = 4
    _enter_end_campaign(s)
    res = apply_action(s, {"type": "end_campaign_resolve", "side": "teutonic", "args": {}})
    assert s.lords[teu].assets.get("provender", 0) == pre - 1
    assert any(w["lord_id"] == teu for w in res["wastage"])
