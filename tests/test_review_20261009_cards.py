"""Rules regressions from the October 2026 review: SoP 3.1 and AoW Events."""
import pytest

from nevsky.actions import IllegalAction, apply_action
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import load_scenario
from nevsky.state import GameState


def event_state(card):
    state = load_scenario('crusade_on_novgorod', seed=1)
    state.pending_decisions = []
    state.meta.first_levy_done = True
    state.meta.active_player = 'russian' if card.startswith('R') else 'teutonic'
    state.meta.aow_drawn_t = state.meta.aow_drawn_r = True
    deck = getattr(state.decks, state.meta.active_player)
    deck.deck = [cid for cid in deck.deck if cid != card]
    deck.pending_draw = [card]
    return state


def implement(state, **args):
    return apply_action(state, {'type': 'aow_implement_card',
                               'side': state.meta.active_player, 'args': args})


def marker(state, lord, kind, box):
    for cb in state.calendar.boxes:
        cb.cylinders = [lid for lid in cb.cylinders if lid != lord]
        cb.service_markers = [lid for lid in cb.service_markers if lid != lord]
    for name in ('off_left', 'off_right', 'off_left_service', 'off_right_service'):
        values = getattr(state.calendar, name)
        values[:] = [lid for lid in values if lid != lord]
    getattr(state.calendar.boxes[box - 1], kind).append(lord)


def test_cannot_skip_mandatory_aow_draw():
    """SoP 3.1: a fresh side must draw, then implement before advancing."""
    state = load_scenario('watland', seed=1)
    assert 'advance_step' not in {m['type'] for m in legal_moves(state, with_previews=False)}
    with pytest.raises(IllegalAction, match='must_draw_aow'):
        apply_action(state, {'type': 'advance_step', 'side': 'teutonic'})
    apply_action(state, {'type': 'aow_draw', 'side': 'teutonic'})
    with pytest.raises(IllegalAction, match='pending_draw_nonempty'):
        apply_action(state, {'type': 'advance_step', 'side': 'teutonic'})
    while state.decks.teutonic.pending_draw:
        action = next(m for m in legal_moves(state, with_previews=False)
                      if m['type'] == 'aow_implement_card')
        apply_action(state, action)
    apply_action(state, {'type': 'advance_step', 'side': 'teutonic'})
    assert state.meta.active_player == 'russian'
    with pytest.raises(IllegalAction, match='must_draw_aow'):
        apply_action(state, {'type': 'advance_step', 'side': 'russian'})


@pytest.mark.parametrize('remaining', [0, 1])
def test_short_deck_still_completes_draw_without_deadlock(remaining):
    """3.1: draw remaining cards; an exhausted deck must still allow advance."""
    state = load_scenario('watland', seed=1)
    deck = state.decks.teutonic
    deck.removed.extend(deck.deck[remaining:] + deck.discard)
    deck.deck = deck.deck[:remaining]
    deck.discard = []
    assert any(m['type'] == 'aow_draw' for m in legal_moves(state, with_previews=False))
    apply_action(state, {'type': 'aow_draw', 'side': 'teutonic'})
    assert len(deck.pending_draw) == remaining
    while deck.pending_draw:
        apply_action(state, next(m for m in legal_moves(state, with_previews=False)
                                 if m['type'] == 'aow_implement_card'))
    apply_action(state, {'type': 'advance_step', 'side': 'teutonic'})
    assert state.meta.active_player == 'russian'


@pytest.mark.parametrize('ships,removed', [(1, 1), (3, 2), (4, 2)])
def test_tempest_removes_half_rounded_up(ships, removed):
    """AoW R16: Cogs halves removed Ships, rounded UP."""
    state = event_state('R16')
    state.decks.teutonic.deck.remove('T18')
    state.lords['andreas'].this_lord_capabilities = ['T18']
    state.lords['andreas'].assets = {'ship': ships}
    result = implement(state, card_id='R16', target='andreas')
    assert result['effect']['ships_removed'] == removed
    assert state.lords['andreas'].assets.get('ship', 0) == ships - removed


def test_batu_khan_zero_shift_is_offered_and_legal():
    """AoW R10 / Q-R201-A: 'up to 2' includes an explicit zero shift."""
    state = event_state('R10')
    before = state.calendar.model_dump()
    action = next(m for m in legal_moves(state, with_previews=False)
                  if m['type'] == 'aow_implement_card' and m['args'].get('boxes') == 0)
    apply_action(state, action)
    assert state.calendar.model_dump() == before
    assert state.decks.russian.pending_draw == []
    assert 'R10' in state.decks.russian.discard


def mixed_swedish_state():
    state = event_state('T18')
    marker(state, 'vladislav', 'service_markers', 6)
    marker(state, 'karelians', 'cylinders', 6)
    state.lords['vladislav'].state = 'mustered'
    state.lords['vladislav'].location = 'ladoga'
    state.lords['karelians'].state = 'ready'
    state.lords['karelians'].location = None
    return state


def test_swedish_crusade_offers_complete_mixed_marker_shifts():
    """AoW T18: shift BOTH Lords, regardless of cylinder vs Service."""
    state = mixed_swedish_state()
    actions = [m for m in legal_moves(state, with_previews=False)
               if m['type'] == 'aow_implement_card']
    assert {m['args']['direction'] for m in actions} == {'left', 'right'}
    for action in actions:
        result = apply_action(state.model_copy(deep=True), action)
        assert set(result['effect']['shifted']) == {'service:vladislav', 'karelians'}


@pytest.mark.parametrize('targets', [{}, {'karelians': 'cylinder'},
                                     {'vladislav': 'cylinder', 'karelians': 'cylinder'}])
def test_swedish_crusade_cannot_omit_reachable_target(targets):
    """AoW T18 / 3.1.4: wrong or omitted marker cannot silently avoid the Event."""
    state = mixed_swedish_state()
    before = state.calendar.model_dump()
    with pytest.raises(IllegalAction, match='missing_target'):
        implement(state, card_id='T18', targets=targets)
    assert state.calendar.model_dump() == before
    assert state.decks.teutonic.pending_draw == ['T18']


def test_osilian_revolt_waits_for_teutonic_choice_and_resumes_russians():
    """AoW R9 explicitly makes Teutons choose; preserve this across save/load."""
    state = event_state('R9')
    marker(state, 'andreas', 'service_markers', 6)
    marker(state, 'heinrich', 'service_markers', 6)
    state.decks.russian.pending_draw.append('R1')
    state.decks.russian.deck.remove('R1')
    with pytest.raises(IllegalAction, match='wrong_chooser'):
        implement(state, card_id='R9', target='heinrich')
    result = implement(state, card_id='R9')
    assert result['outcome'] == 'awaiting_event_choice'
    assert state.meta.active_player == 'teutonic'
    assert state.pending_decisions[0].owed_by == 'teutonic'
    assert state.decks.russian.pending_draw == ['R9', 'R1']
    state = GameState.model_validate_json(state.model_dump_json())
    actions = legal_moves(state, with_previews=False)
    assert len(actions) == 2
    assert {m['args']['target'] for m in actions} == {'andreas', 'heinrich'}
    assert {m['side'] for m in actions} == {'teutonic'}
    for action_type in ('advance_step', 'aow_draw', 'aow_shuffle'):
        with pytest.raises(IllegalAction, match='pending_event_choice'):
            apply_action(state, {'type': action_type, 'side': 'teutonic'})
    with pytest.raises(IllegalAction, match='wrong_actor'):
        apply_action(state, {'type': 'aow_implement_card', 'side': 'russian',
                             'args': {'card_id': 'R9', 'target': 'heinrich'}})
    result = implement(state, card_id='R9', target='heinrich')
    assert result['effect']['new_box'] == 4
    assert state.meta.active_player == 'russian'
    assert not state.pending_decisions
    assert state.decks.russian.pending_draw == ['R1']
    assert 'R9' in state.decks.russian.discard
    implement(state, card_id='R1')
    assert 'R1' in state.decks.russian.holds


def test_osilian_no_target_discards_without_choice():
    """AoW R9: unavailable Service targets need no opponent response."""
    state = event_state('R9')
    marker(state, 'andreas', 'service_markers', 1)
    marker(state, 'heinrich', 'service_markers', 1)
    result = implement(state, card_id='R9')
    assert result['effect']['no_op']
    assert state.meta.active_player == 'russian'
    assert not state.pending_decisions


def test_osilian_driver_expansion_validated_palette_and_fallback():
    """AoW R9: driver argument expansion preserves reveal vs opponent choice."""
    import importlib.util
    from pathlib import Path

    from nevsky.event_args import _expand_event_variants, _populate_event_args
    from nevsky.llm.tools import safe_fallback_for_side
    script = Path(__file__).resolve().parents[1] / 'scripts' / 'llm_self_play.py'
    spec = importlib.util.spec_from_file_location('cards_review_llm_self_play', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    state = event_state('R9')
    marker(state, 'andreas', 'service_markers', 6)
    marker(state, 'heinrich', 'service_markers', 6)
    reveal = safe_fallback_for_side(state, 'russian')
    assert reveal['args'] == {'card_id': 'R9'}
    assert _populate_event_args(state, 'R9', reveal['args']) == reveal['args']
    assert _expand_event_variants(state, reveal) == [reveal]
    actions, rejected = module.concrete_actions_validated(state, 'russian')
    assert not rejected and len(actions) == 1
    assert actions[0]['args'] == {'card_id': 'R9'}
    apply_action(state, reveal)
    actions, rejected = module.concrete_actions_validated(state, 'teutonic')
    assert not rejected and {a['args']['target'] for a in actions} == {'andreas', 'heinrich'}
    response = safe_fallback_for_side(state, 'teutonic')
    apply_action(state, response)
    assert state.meta.active_player == 'russian'
    assert state.decks.russian.pending_draw == []


@pytest.mark.parametrize('order', [[], ['coin']])
def test_torzhok_requires_three_assets_when_available(order):
    """AoW T2: select target freely; remove three from it to the degree able."""
    state = event_state('T2')
    state.lords['domash'].assets = {'coin': 1, 'provender': 3}
    with pytest.raises(IllegalAction, match='insufficient_asset_selection'):
        implement(state, card_id='T2', target='domash', asset_order=order)
    assert state.lords['domash'].assets == {'coin': 1, 'provender': 3}
    result = implement(state, card_id='T2', target='domash', asset_order=['coin', 'provender'])
    assert result['effect']['removed'] == {'coin': 1, 'provender': 2}


def test_torzhok_allows_poor_target_and_custom_priority():
    """AoW T2 Tips permits selecting Domash even if he has fewer than three."""
    state = event_state('T2')
    state.lords['domash'].assets = {'ship': 1, 'provender': 1}
    result = implement(state, card_id='T2', target='domash', asset_order=['ship', 'provender'])
    assert result['effect']['removed'] == {'ship': 1, 'provender': 1}
    assert not state.lords['domash'].assets
