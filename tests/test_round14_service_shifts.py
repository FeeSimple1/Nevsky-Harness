"""Event and Feed/Pay shifts use both Calendar edges and keep Vassal Service."""

import pytest

from nevsky.actions import (
    IllegalAction,
    _find_cylinder_box,
    _find_service_marker_box,
    _place_lord_on_map,
    apply_action,
)
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import load_scenario
from nevsky.state import GameState, vassal_marker_box
from nevsky.static_data import load_lords


def _act(state, kind, side="teutonic", **args):
    return apply_action(state, {"type": kind, "side": side, "args": args})


def _stage(state, box, phase, step, side="teutonic"):
    state.meta.box = box
    state.meta.phase = phase
    state.meta.active_player = side
    state.meta.levy_step = step if phase == "levy" else "done"
    state.meta.campaign_step = "command"
    state.meta.first_levy_done = True
    for entry in state.calendar.boxes:
        entry.has_levy_campaign_marker = entry.box == box
        entry.levy_campaign_face = phase if entry.box == box else None


def _native(name="crusade_on_novgorod"):
    state = load_scenario(name, seed=14)
    for side in ("teutonic", "russian"):
        _act(state, "confirm_all_setup_transports", side)
    return state


def _set_service(state, lid, box):
    calendar = state.calendar
    for markers in [calendar.off_left_service, calendar.off_right_service,
                    *(b.service_markers for b in calendar.boxes)]:
        if lid in markers:
            markers.remove(lid)
    if box == 0:
        calendar.off_left_service.append(lid)
    elif box == 17:
        calendar.off_right_service.append(lid)
    else:
        calendar.boxes[box - 1].service_markers.append(lid)


def _replay(state, transition):
    restored = GameState.model_validate_json(state.model_dump_json())
    result = transition(state)
    assert transition(restored) == result
    assert restored.model_dump() == state.model_dump()
    return result


@pytest.mark.parametrize("direction, advanced, late, lord_box, vassal_box", [
    ("right", True, False, 8, 6),
    ("left", True, False, 6, 4),
    ("right", False, False, 8, None),
    ("left", False, False, 6, None),
    ("right", True, True, 17, 16),
])
def test_dietrich_shifts_all_calendar_service_markers(direction, advanced, late, lord_box, vassal_box):
    state = _native("crusade_on_novgorod" if late else "watland")
    muster_box = 14 if late else 4
    _stage(state, muster_box, "levy", "muster")
    if late:
        # Stage Andreas's earlier native Muster and continued Service.
        _place_lord_on_map(state, "andreas", "fellin", 13)
        for lid, lord in state.lords.items():
            if lord.state == "mustered":
                _set_service(state, lid, 17)
    state.meta.optional_rules["advanced_vassal_service"] = advanced
    state.lords["andreas"].just_arrived_this_levy = False
    vid = "andreas_lettgallian_aux"
    _act(state, "muster_vassal", by_lord="andreas", vassal_id=vid)
    assert vassal_marker_box(state.calendar, vid, state.lords["andreas"].vassals[vid]) == (
        muster_box + 1 if advanced else None)

    # Stage the following Arts of War draw with only Dietrich to resolve.
    _stage(state, muster_box + 1, "levy", "arts_of_war", "russian")
    state.meta.aow_drawn_t = state.meta.aow_drawn_r = True
    state.meta.levy_step_completed_t = True
    deck = state.decks.russian
    deck.deck.remove("R17")
    deck.pending_draw = ["R17"]
    rng = state.meta.rng_state

    def event_then_disband(position):
        result = _act(position, "aow_implement_card", "russian",
                      target="service:andreas", direction=direction)
        assert _find_service_marker_box(position, "andreas") == lord_box
        vassal = position.lords["andreas"].vassals[vid]
        assert vassal_marker_box(position.calendar, vid, vassal) == vassal_box
        _act(position, "advance_step", "russian")
        _act(position, "advance_step", "teutonic")
        _act(position, "advance_step", "russian")
        disband = _act(position, "disband_resolve")
        return result, disband

    _replay(state, event_then_disband)
    andreas = state.lords["andreas"]
    removed = advanced and direction == "left"
    assert andreas.vassals[vid].mustered != removed
    assert andreas.forces.get("light_horse", 0) == (0 if removed else 1)
    assert state.meta.rng_state == rng


def _before_feed(lid="hermann", box=1, service=1, food=False, advanced=False):
    state = _native()
    _stage(state, box, "campaign", "command")
    for lord_id, lord in state.lords.items():
        lord.moved_fought = lord_id == lid
        if box > 1 and lord.state == "mustered":
            _set_service(state, lord_id, 17)
    _set_service(state, lid, service)
    assets = state.lords[lid].assets
    assets.pop("provender", None)
    assets.pop("loot", None)
    if food:
        assets["provender"] = 1
    state.campaign_turn.active_lord = state.campaign_turn.active_card = lid
    state.campaign_turn.actions_remaining = 0
    state.campaign_turn.in_feed_pay_disband = True
    state.meta.optional_rules["advanced_vassal_service"] = advanced
    return state


@pytest.mark.parametrize("source", ["coin", "loot", "veche", "decline"])
def test_pay_from_off_left_before_campaign_disband(source):
    lid = "gavrilo" if source == "veche" else "hermann"
    fed = source in ("loot", "veche")
    # In the fed cases the Lord already reached the edge during Retreat.
    state = _before_feed(lid, service=0 if fed else 1, food=fed)
    side = state.lords[lid].side
    if source == "veche":
        state.veche.coin = 1  # Coin acquired earlier in Levy.
        _act(state, "fpd_resolve", decline_pay=True)
    if source == "loot":
        state.lords[lid].assets["loot"] = 1
    feed = _act(state, "fpd_resolve", side)
    assert feed["pay_window"]
    assert feed["feed"][0]["unfed"] != fed
    assert _find_service_marker_box(state, lid) == 0

    def pay_then_disband(position):
        if source != "decline":
            action = "pay_with_loot" if source == "loot" else "pay_with_coin"
            payer = ({"from_lord": lid} if source == "loot" else
                     {"from": "veche" if source == "veche" else f"lord:{lid}"})
            assert any(move["type"] == action and lid in move["candidates"]["targets"]
                       for move in legal_moves(position, with_previews=False))
            before = position.model_dump_json()
            with pytest.raises(IllegalAction) as rejected:
                _act(position, action, side, target_lord=lid, units=2, **payer)
            assert rejected.value.code == "insufficient_funds"
            assert position.model_dump_json() == before
            result = _act(position, action, side, target_lord=lid, units=1, **payer)
            assert result["new_box"] == 1
            assert lid not in position.calendar.off_left_service
            assert _find_service_marker_box(position, lid) == 1
        return _act(position, "fpd_resolve", side)

    result = _replay(state, pay_then_disband)
    if source == "decline":
        assert state.lords[lid].state == "removed"
        assert lid in result["permanently_removed"]
    else:
        assert state.lords[lid].state == "disbanded"
        assert _find_cylinder_box(state, lid) == 2 + load_lords()[lid]["ratings"]["service"]


@pytest.mark.parametrize("service, food, after, fate", [
    (17, False, 16, "disbanded"), (17, True, 17, "mustered"), (16, False, 15, "removed"),
])
def test_unfed_service_reenters_from_off_right(service, food, after, fate):
    state = _before_feed(box=16, service=service, food=food)

    def feed_then_disband(position):
        feed = _act(position, "fpd_resolve")
        assert feed["feed"][0]["unfed"] != food
        assert _find_service_marker_box(position, "hermann") == after
        if after == 17:
            # Every Teutonic Service marker is off-right, so there is no Pay pause.
            assert "pay_window" not in feed
            assert position.campaign_turn.fpd_completed_t
            return feed
        assert feed["pay_window"]
        return _act(position, "fpd_resolve")

    _replay(state, feed_then_disband)
    assert state.lords["hermann"].state == fate


def test_unfed_off_right_also_expires_the_vassal_at_its_limit():
    state = _before_feed(box=14, service=17, advanced=True)
    _stage(state, 14, "levy", "muster")
    state.campaign_turn.in_feed_pay_disband = False
    state.lords["hermann"].just_arrived_this_levy = False
    vid = "hermann_ugaunian_aux"
    _act(state, "muster_vassal", by_lord="hermann", vassal_id=vid)
    vassal = state.lords["hermann"].vassals[vid]
    assert vassal_marker_box(state.calendar, vid, vassal) == 15
    _stage(state, 14, "campaign", "command")
    state.campaign_turn.in_feed_pay_disband = True

    def feed_then_disband(position):
        _act(position, "fpd_resolve")
        assert _find_service_marker_box(position, "hermann") == 16
        assert vassal_marker_box(position.calendar, vid, position.lords["hermann"].vassals[vid]) == 14
        return _act(position, "fpd_resolve")

    _replay(state, feed_then_disband)
    assert state.lords["hermann"].state == "mustered"
    assert not state.lords["hermann"].vassals[vid].mustered
