"""Rules regressions from the complete Crusade game with seed 20261011.

Six source positions are real, captured game states (history omitted only).
The additional synthetic edge cases and complete legal replay are separate.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from nevsky.actions import (
    IllegalAction,
    _find_cylinder_box,
    _is_ready,
    _lordship_budget,
    _spend_lordship,
    apply_action,
)
from nevsky.held_actions import held_actions_for_side
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import determine_scenario_winner, load_scenario, refresh_victory_markers
from nevsky.state import GameState
from nevsky.static_data import load_cards

DATA = Path(__file__).parent / 'data' / 'crusade_seed_20261011'
INDEX = json.loads((DATA / 'index.json').read_text())


def position(name):
    return GameState.model_validate_json((DATA / INDEX[name]['file']).read_text())


def envelope(move):
    return {k: move[k] for k in ('type', 'side', 'args')}


def offered(state, action):
    before = state.model_dump_json()
    menu = legal_moves(state, with_previews=False)
    assert state.model_dump_json() == before, 'Menu mutated the live game'
    return any(envelope(m) == action for m in menu if isinstance(m.get('args'), dict))


def transport(lid, side, kind='cart'):
    return {'type': 'levy_transport', 'side': side,
            'args': {'by_lord': lid, 'transport_type': kind}}


def synthetic_muster(side):
    state = load_scenario('crusade_on_novgorod', seed=20261011)
    for owner in ('teutonic', 'russian'):
        apply_action(state, {'type': 'confirm_all_setup_transports', 'side': owner, 'args': {}})
    state.meta.levy_step = 'muster'
    state.meta.active_player = side
    return state


def test_recorded_muster_return_is_not_offered_or_accepted():
    name = 'muster_interleaving'
    state = position(name)
    actions = INDEX[name]['actions']
    for action in actions[:-1]:
        apply_action(state, action)
    state = GameState.model_validate_json(state.model_dump_json())
    before = state.model_dump_json()
    assert not offered(state, actions[-1])
    with pytest.raises(IllegalAction, match='muster_finished'):
        apply_action(state, actions[-1])
    assert state.model_dump_json() == before


@pytest.mark.parametrize('side,first,second', [
    ('teutonic', 'hermann', 'knud_and_abel'),
    ('russian', 'gavrilo', 'vladislav'),
])
def test_each_side_may_finish_one_lord_but_may_not_return(side, first, second):
    state = synthetic_muster(side)
    apply_action(state, transport(first, side))
    apply_action(state, transport(first, side, 'boat'))
    assert state.meta.muster_lord_order == [first]
    apply_action(state, transport(second, side))
    assert state.meta.muster_lord_order == [first, second]
    before = state.model_dump_json()
    # The shared spender covers recruitment, Vassals, Transport, Capability.
    with pytest.raises(IllegalAction, match='muster_finished'):
        _spend_lordship(state, first)
    assert state.model_dump_json() == before
    assert not any(m.get('args', m.get('args_template', {})).get('by_lord') == first
                   for m in legal_moves(state, with_previews=False))


def test_invalid_attempt_by_next_lord_does_not_close_current_lord():
    state = synthetic_muster('teutonic')
    apply_action(state, transport('hermann', 'teutonic'))
    before = state.model_dump_json()
    with pytest.raises(IllegalAction):
        apply_action(state, transport('knud_and_abel', 'teutonic', 'invalid'))
    assert state.model_dump_json() == before
    apply_action(state, transport('hermann', 'teutonic', 'boat'))
    assert state.meta.muster_lord_order == ['hermann']


def test_failed_fealty_roll_still_starts_lords_muster(monkeypatch):
    import nevsky.rng as rng

    state = synthetic_muster('teutonic')
    monkeypatch.setattr(rng, 'roll_d6', lambda s: 6)
    action = {'type': 'muster_lord', 'side': 'teutonic',
              'args': {'by_lord': 'hermann', 'target_lord': 'rudolf', 'seat': 'wenden'}}
    assert apply_action(state, action)['outcome'] == 'fealty_failed'
    assert state.meta.muster_lord_order == ['hermann']
    apply_action(state, transport('knud_and_abel', 'teutonic'))
    with pytest.raises(IllegalAction, match='muster_finished'):
        apply_action(state, action)


def test_lordship_hold_does_not_reopen_finished_lord():
    state = synthetic_muster('teutonic')
    for lid in ('hermann', 'knud_and_abel'):
        apply_action(state, transport(lid, 'teutonic'))
    deck = state.decks.teutonic
    deck.deck.remove('T7')
    deck.holds.append('T7')
    assert not any(m['args'].get('mode') == 'lordship' and m['args'].get('lord_id') == 'hermann'
                   for m in held_actions_for_side(state, 'teutonic'))
    # Even explicit play of a wasted bonus cannot reopen ordinary Muster.
    apply_action(state, {'type': 'aow_lordship_plus_2', 'side': 'teutonic',
                         'args': {'card_id': 'T7', 'lord_id': 'hermann', 'mode': 'lordship'}})
    with pytest.raises(IllegalAction, match='muster_finished'):
        apply_action(state, transport('hermann', 'teutonic'))


@pytest.mark.parametrize('side,lid', [('teutonic', 'hermann'), ('russian', 'gavrilo')])
def test_extra_muster_is_independent_of_closed_ordinary_muster(side, lid):
    state = synthetic_muster(side)
    state.meta.muster_lord_order = [lid, 'some_later_lord']
    state.meta.levy_step = 'call_to_arms'
    state.lords[lid].lordship_used = _lordship_budget(state, lid)
    if side == 'teutonic':
        state.legate.william_of_modena_in_play = True
        state.legate.location = 'locale'
        state.legate.locale_id = state.lords[lid].location
        action = {'type': 'legate_use', 'side': side,
                  'args': {'sub_option': '2c', 'target_lord': lid}}
    else:
        action = {'type': 'veche_action', 'side': side,
                  'args': {'option': 'C', 'target_lord': lid}}
    apply_action(state, action)
    assert offered(state, transport(lid, side))
    apply_action(state, transport(lid, side))


def test_muster_entry_resets_order_for_new_levy():
    state = synthetic_muster('russian')
    state.meta.levy_step = 'disband'
    state.meta.levy_step_completed_t = True
    state.meta.disband_resolved_r = True
    state.meta.muster_lord_order = ['hermann', 'knud_and_abel']
    apply_action(state, {'type': 'advance_step', 'side': 'russian', 'args': {}})
    assert state.meta.levy_step == 'muster'
    assert state.meta.muster_lord_order == []
    assert offered(state, transport('hermann', 'teutonic'))


def test_recorded_cylinder_shift_enables_remuster_and_updates_status():
    name = 'shifted_disbanded_not_ready'
    state = position(name)
    shift, recruit = INDEX[name]['actions']
    assert state.lords['hermann'].state == 'disbanded'
    apply_action(state, shift)
    assert _find_cylinder_box(state, 'hermann') == state.meta.box == 7
    assert state.lords['hermann'].state == 'ready'
    assert offered(state, recruit)
    apply_action(state, recruit)  # ordinary Fealty failure remains legal


@pytest.mark.parametrize('old_state,box,expected', [
    ('disbanded', 0, True), ('disbanded', 7, True), ('disbanded', 8, False),
    ('disbanded', 17, False), ('ready', 7, True), ('ready', 8, False),
    ('removed', 7, False), ('mustered', 7, False),
])
def test_readiness_uses_position_and_never_revives_removed_or_on_map_lord(old_state, box, expected):
    state = position('shifted_disbanded_not_ready')
    lid = 'hermann'
    for cb in state.calendar.boxes:
        cb.cylinders = [x for x in cb.cylinders if x != lid]
    state.calendar.off_left = [x for x in state.calendar.off_left if x != lid]
    state.calendar.off_right = [x for x in state.calendar.off_right if x != lid]
    if box == 0:
        state.calendar.off_left.append(lid)
    elif box == 17:
        state.calendar.off_right.append(lid)
    else:
        state.calendar.boxes[box - 1].cylinders.append(lid)
    state.lords[lid].state = old_state
    assert _is_ready(state, lid, 7) is expected


def test_shift_right_keeps_future_lord_ineligible():
    state = position('shifted_disbanded_not_ready')
    shift, recruit = INDEX['shifted_disbanded_not_ready']['actions']
    shift = {**shift, 'args': {**shift['args'], 'direction': 'right'}}
    apply_action(state, shift)
    assert not _is_ready(state, 'hermann', 7)
    assert not offered(state, recruit)
    before = state.model_dump_json()
    with pytest.raises(IllegalAction, match='not_ready'):
        apply_action(state, recruit)
    assert state.model_dump_json() == before


def mats(state):
    return {lid: lord.model_dump() for lid, lord in state.lords.items()}


@pytest.mark.parametrize('side', ['teutonic', 'russian'])
@pytest.mark.parametrize('explicit_cleanup', [False, True])
def test_final_campaign_preserves_mats_cards_and_only_performs_grow(side, explicit_cleanup):
    name = 'post_final_turn_cleanup_' + side
    state = position(name)
    action = INDEX[name]['actions'][0]
    if not explicit_cleanup:
        action = {**action, 'args': {}}
    before_mats, before_decks = mats(state), state.decks.model_dump()
    menu = next(m for m in legal_moves(state, with_previews=False)
                if m['type'] == 'end_campaign_resolve')
    assert not {'wastage', 'reset_discard'} & set(menu.get('candidates', {}))
    result = apply_action(state, action)
    assert not result['wastage'] and not result['reset_discard']
    assert not result['this_campaign_discarded'] and not result['serfs_returned']
    assert mats(state) == before_mats
    assert state.decks.model_dump() == before_decks
    assert state.meta.box == 16
    for owner in ('teutonic', 'russian'):
        vp = getattr(state.calendar, owner + '_vp')
        assert [b.box for b in state.calendar.boxes if getattr(b, owner + '_victory_marker')] == (
            [] if vp < 1 else [min(16, int(vp))])


def test_final_game_end_waits_for_both_grow_choices():
    state = position('post_final_turn_cleanup_teutonic')
    before_mats = mats(state)
    for side in ('teutonic', 'russian'):
        result = apply_action(state, {'type': 'end_campaign_resolve', 'side': side, 'args': {}})
        assert result['grew']
        assert state.meta.game_over is (side == 'russian')
    assert mats(state) == before_mats
    assert state.meta.winner == determine_scenario_winner(state)['winner']
    before = state.model_dump_json()
    with pytest.raises(IllegalAction, match='game_over'):
        apply_action(state, {'type': 'end_campaign_resolve', 'side': 'russian', 'args': {}})
    assert before == state.model_dump_json()


@pytest.mark.parametrize('box', [2, 6, 14])
def test_final_turn_in_any_season_skips_transport_flip_wastage_and_reset(box):
    state = position('post_final_turn_cleanup_teutonic')
    state.meta.box = box
    state.meta.span_end_box = box
    for cb in state.calendar.boxes:
        cb.has_levy_campaign_marker = cb.box == box
        cb.levy_campaign_face = 'campaign' if cb.box == box else None
    state.lords['domash'].forces['serfs'] = 2
    state.lords['hermann'].has_lower_lord = 'yaroslav'
    state.lords['yaroslav'].lieutenant_of = 'hermann'
    before_mats = mats(state)
    before_decks = state.decks.model_dump()
    for side in ('teutonic', 'russian'):
        apply_action(state, {'type': 'end_campaign_resolve', 'side': side,
                             'args': {'reset_discard': list(getattr(state.decks, side).holds)}})
    assert mats(state) == before_mats
    assert state.decks.model_dump() == before_decks
    assert state.meta.game_over and state.meta.box == box


@pytest.mark.parametrize('cid', ['T15', 'R12'])
@pytest.mark.parametrize('starting_vp', [0.0, 0.5, 16.5, 17.5])
def test_mindaugas_refreshes_marker_and_respects_half_points_and_cap(cid, starting_vp):
    name = 'victory_display_' + cid
    state = position(name)
    action = INDEX[name]['actions'][0]
    side = action['side']
    setattr(state.calendar, side + '_vp', starting_vp)
    refresh_victory_markers(state)
    assert offered(state, action)
    apply_action(state, action)
    vp = getattr(state.calendar, side + '_vp')
    assert vp == min(17.5, starting_vp + 0.5)
    actual = [b.box for b in state.calendar.boxes if getattr(b, side + '_victory_marker')]
    assert actual == ([] if vp < 1 else [min(16, int(vp))])
    assert getattr(state.locales[action['args']['locale']], side + '_ravaged')


def test_complete_1742_action_ordered_crusade_replay():
    payload = json.loads((DATA / 'ordered_replay.json').read_text())
    assert len(payload['actions']) == 1742
    state = load_scenario(payload['scenario'], seed=payload['seed'])
    save_checks = 0
    for number, action in enumerate(payload['actions'], 1):
        final_cleanup = (state.meta.box == 16 and action['type'] == 'end_campaign_resolve')
        before_mats = mats(state) if final_cleanup else None
        result = apply_action(state, action)
        if final_cleanup:
            assert not result['wastage']
            assert mats(state) == before_mats
        if number % 20 == 0:
            serialized = state.model_dump_json()
            state = GameState.model_validate_json(serialized)
            assert state.model_dump_json() == serialized
            save_checks += 1
    assert save_checks == 87
    assert state.meta.game_over and state.meta.box == payload['expected_box']
    assert determine_scenario_winner(state) == payload['expected_winner']
    for side in ('teutonic', 'russian'):
        deck = getattr(state.decks, side)
        cards = []
        for zone in ('deck', 'discard', 'removed', 'holds', 'capabilities_in_play',
                     'pending_draw', 'this_levy_events', 'this_campaign_events'):
            cards.extend(getattr(deck, zone))
        cards.extend(cid for lord in state.lords.values() if lord.side == side
                     for cid in lord.this_lord_capabilities)
        assert Counter(cards) == Counter({cid: 1 for cid, c in load_cards().items()
                                          if c['side'] == side})
    assert not legal_moves(state, with_previews=False)


@pytest.mark.parametrize('side,lid,seat', [
    ('teutonic', 'rudolf', 'wenden'), ('russian', 'domash', 'novgorod'),
])
def test_call_to_arms_recruitment_uses_cylinder_not_stale_disbanded_label(side, lid, seat):
    state = synthetic_muster(side)
    state.meta.levy_step = 'call_to_arms'
    state.lords[lid].state = 'disbanded'
    assert _find_cylinder_box(state, lid) == 1
    if side == 'teutonic':
        state.legate.william_of_modena_in_play = True
        state.legate.location = 'locale'
        state.legate.locale_id = seat
        request = {'type': 'legate_use', 'side': side,
                   'args': {'sub_option': '2a', 'target_lord': lid}}
    else:
        request = {'type': 'veche_action', 'side': side,
                   'args': {'option': 'B', 'target_lord': lid, 'seat': seat}}
    assert offered(state, request)
    apply_action(state, request)
    assert state.lords[lid].state == 'mustered'
    assert state.lords[lid].location == seat


@pytest.mark.parametrize('cid,side,target,locale', [
    ('T14', 'teutonic', 'russian', 'rositten'),
    ('R18', 'russian', 'teutonic', 'ostrov'),
])
@pytest.mark.parametrize('starting_vp', [0.5, 1.0, 2.0, 17.5])
def test_bountiful_harvest_refreshes_opponents_decreased_marker(
    cid, side, target, locale, starting_vp,
):
    state = synthetic_muster(side)
    state.meta.levy_step = 'arts_of_war'
    state.meta.first_levy_done = True
    deck = getattr(state.decks, side)
    deck.deck.remove(cid)
    deck.pending_draw = [cid]
    setattr(state.locales[locale], target + '_ravaged', True)
    setattr(state.calendar, target + '_vp', starting_vp)
    refresh_victory_markers(state)
    action = {'type': 'aow_implement_card', 'side': side,
              'args': {'card_id': cid, 'locale': locale}}
    assert offered(state, action)
    apply_action(state, action)
    vp = getattr(state.calendar, target + '_vp')
    assert vp == starting_vp - 0.5
    actual = [b.box for b in state.calendar.boxes if getattr(b, target + '_victory_marker')]
    assert actual == ([] if vp < 1 else [min(16, int(vp))])
    assert not getattr(state.locales[locale], target + '_ravaged')
