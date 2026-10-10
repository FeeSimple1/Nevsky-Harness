"""Focused rule probes branching from the two recorded Crusade games.

Never alter the primary transcripts or the rules engine. Each finding retains
its real-game starting snapshot, exact legal actions, and before/after evidence.
"""
from __future__ import annotations
import copy
import inspect
import itertools
import json
import sys
from collections import Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'scripts')]
from nevsky.actions import apply_action, IllegalAction
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import load_scenario
from nevsky.static_data import load_cards, load_lords
from nevsky.events import _LORDSHIP_PLUS_2_TARGETS
import nevsky.actions as am
import nevsky.events as em
import nevsky.legal_moves as lm
from crusade_diagnostic import clone, fingerprint

OUT = ROOT / 'reports' / 'crusade_20261010'
EVIDENCE = OUT / 'reproductions'
EVIDENCE.mkdir(exist_ok=True)
results = {}
LORDS, CARDS = load_lords(), load_cards()


def menu_for(s):
    return legal_moves(s, with_previews=False)


def probe(s, a):
    p = clone(s)
    try:
        result = apply_action(p, copy.deepcopy(a))
        return p, result
    except IllegalAction:
        return None, None


def add(key, s, game, index, data):
    if key in results:
        return
    file = f'{key}.state.json'
    (EVIDENCE / file).write_text(s.model_dump_json())
    results[key] = {'game': game, 'before_action_index': index, 'calendar_box': s.meta.box,
                    'phase': s.meta.phase, 'step': s.meta.levy_step if s.meta.phase == 'levy' else s.meta.campaign_step,
                    'active_side': s.meta.active_player, 'state_file': file, **data}
    print('REPRO', key, json.dumps(results[key]), flush=True)


for folder in (OUT, OUT / 'reserve_game'):
    game = 'first' if folder == OUT else 'reserve_game'
    s = load_scenario('crusade_on_novgorod', seed=20261010)
    transcript = json.loads((folder / 'transcript.json').read_text())
    for i, row in enumerate(transcript):
        side = s.meta.active_player or 'teutonic'
        raw = menu_for(s)
        types = {a['type'] for a in raw}
        own = [lid for lid, l in s.lords.items() if l.side == side and l.state == 'mustered' and l.location]
        held = list(getattr(s.decks, side).holds)
        # Free-standing Hold events. These tests require actual held cards.
        if s.meta.phase == 'campaign' and s.meta.campaign_step == 'command':
            requests = []
            if 'R3' in held:
                requests += [{'type': 'aow_play_hold', 'side': side, 'args': {'card_id': 'R3', 'target': lid}}
                             for lid in own if s.lords[lid].assets.get('provender', 0) < 8]
            if 'T3' in held:
                requests += [{'type': 'aow_play_hold', 'side': side, 'args': {'card_id': 'T3', 'target': fort}}
                             for fort in ('kaibolovo', 'koporye')]
            if 'T13' in held and 'heinrich' in own:
                recipients = [lid for lid in own if lid != 'heinrich']
                if len(recipients) >= 2:
                    requests.append({'type': 'aow_play_hold', 'side': side,
                                     'args': {'card_id': 'T13', 'recipients': recipients[:2]}})
            for a in requests:
                cid = a['args']['card_id']
                # Continue T3 search until an already-Conquered natural state is found.
                if f'hidden_hold_{cid}' in results and (cid != 'T3' or 'T3_double_conquest' in results):
                    continue
                p, result = probe(s, a)
                if p is None:
                    continue
                if 'aow_play_hold' not in types:
                    target = a['args'].get('target')
                    assets_before = s.lords[target].assets if target in s.lords else None
                    assets_after = p.lords[target].assets if target in p.lords else None
                    add(f'hidden_hold_{cid}', s, game, i,
                        {'actions': [a], 'menu_types': sorted(types), 'accepted_result': result,
                         'assets_before': assets_before, 'assets_after': assets_after,
                         'card': CARDS[cid]})
                if cid == 'T3':
                    fort = a['args']['target']
                    before, after = s.locales[fort].teutonic_conquered, p.locales[fort].teutonic_conquered
                    if before > 0 and after > before:
                        add('T3_double_conquest', s, game, i,
                            {'actions': [a], 'fort': fort, 'markers_before': before, 'markers_after': after,
                             'vp_before': s.calendar.teutonic_vp, 'vp_after': p.calendar.teutonic_vp,
                             'accepted_result': result, 'card': CARDS[cid]})
        # Lordship+2 holds are real choices; bonus expenditures must be exposed.
        if s.meta.phase == 'levy' and s.meta.levy_step == 'muster':
            for cid in held:
                spec = _LORDSHIP_PLUS_2_TARGETS.get(cid)
                if not spec:
                    continue
                eligible = spec['lords']
                for lid in own:
                    l = s.lords[lid]
                    if eligible != 'any_russian' and lid not in eligible:
                        continue
                    if l.just_arrived_this_levy:
                        continue
                    a = {'type': 'aow_lordship_plus_2', 'side': side,
                         'args': {'card_id': cid, 'lord_id': lid, 'mode': 'lordship'}}
                    p, result = probe(s, a)
                    if p is None:
                        continue
                    if 'aow_lordship_plus_2' not in types:
                        add(f'hidden_lordship_{side}', s, game, i,
                            {'actions': [a], 'menu_types': sorted(types), 'accepted_result': result,
                             'card': CARDS[cid]})
                    if f'bonus_budget_hidden_{side}' in results:
                        continue
                    # Spend only legal actions until printed Lordship is used.
                    base = LORDS[lid]['ratings']['lordship']
                    seq = [a]
                    spent = []
                    for _ in range(12):
                        if p.lords[lid].lordship_used >= base:
                            break
                        options = [m for m in menu_for(p) if m['type'] == 'levy_transport' and m.get('args', {}).get('by_lord') == lid]
                        acted = False
                        for option in options:
                            clean = {k:v for k,v in option.items() if k in ('type','side','args')}
                            q, _ = probe(p, clean)
                            if q is not None:
                                p = q
                                seq.append(clean)
                                acted = True
                                break
                        if not acted:
                            break
                    if p.lords[lid].lordship_used != base:
                        continue
                    exposed = [m for m in menu_for(p) if m.get('args', {}).get('by_lord') == lid]
                    before_used = p.lords[lid].lordship_used
                    for _ in range(2):
                        for tr in ('cart', 'sled', 'boat', 'ship'):
                            spend = {'type': 'levy_transport', 'side': side, 'args': {'by_lord': lid, 'transport_type': tr}}
                            q, _ = probe(p, spend)
                            if q is not None:
                                p = q
                                seq.append(spend)
                                spent.append(spend)
                                break
                    if len(spent) == 2 and not exposed:
                        add(f'bonus_budget_hidden_{side}', s, game, i,
                            {'actions': seq, 'lord': lid, 'card_id': cid, 'printed_lordship': base,
                             'spent_before_hidden_moves': before_used,
                             'bonus': p.meta.lordship_bonus.get(lid), 'spent_after': p.lords[lid].lordship_used,
                             'offered_actions_for_lord_at_base_budget': exposed,
                             'accepted_extra_moves': spent})
        # Branch at a naturally offered extra-Muster choice; inspect continuation.
        if s.meta.phase == 'levy' and s.meta.levy_step == 'call_to_arms':
            for a0 in raw:
                typ, args = a0['type'], a0.get('args', {})
                extra_choice = (typ == 'veche_action' and args.get('option') == 'C') or (typ == 'legate_use' and args.get('sub_option') == '2c')
                if not extra_choice:
                    continue
                key = f'extra_muster_hidden_{typ}'
                if key in results:
                    continue
                a = {k:v for k,v in a0.items() if k in ('type','side','args')}
                p, result = probe(s, a)
                if p is None:
                    continue
                lid = args['target_lord']
                menu_after = menu_for(p)
                offered = [m for m in menu_after if m.get('args', {}).get('by_lord') == lid]
                for tr in ('cart', 'sled', 'boat', 'ship'):
                    spend = {'type': 'levy_transport', 'side': side, 'args': {'by_lord': lid, 'transport_type': tr}}
                    q, spend_result = probe(p, spend)
                    if q is not None and not offered:
                        add(key, s, game, i,
                            {'actions': [a, spend], 'extra_muster_result': result,
                             'next_menu_types': sorted({m['type'] for m in menu_after}),
                             'accepted_spend_result': spend_result,
                             'lord': lid, 'vp_before': s.calendar.russian_vp, 'vp_after_choice': p.calendar.russian_vp})
                        break
        apply_action(s, copy.deepcopy(row['action']))
    # Check final-state stability and complete card accounting independently.
    terminal_before = fingerprint(s)
    try:
        apply_action(s, {'type':'command_reveal','side':s.meta.active_player,'args':{}})
        terminal_guard = False
    except IllegalAction as exc:
        terminal_guard = exc.code == 'game_over' and fingerprint(s) == terminal_before
    cards_summary = {}
    for sd in ('teutonic', 'russian'):
        d = getattr(s.decks, sd)
        names = ('deck', 'discard', 'removed', 'holds', 'pending_draw', 'capabilities_in_play', 'this_levy_events', 'this_campaign_events')
        c = Counter(cid for zone in names for cid in getattr(d, zone, []))
        c.update(cid for l in s.lords.values() if l.side == sd for cid in l.this_lord_capabilities)
        cards_summary[sd] = {'counts': dict(c), 'missing_or_duplicate': {cid:c[cid] for cid in CARDS if CARDS[cid]['side'] == sd and c[cid] != 1},
                             'removed': list(d.removed), 'held': list(d.holds)}
    (EVIDENCE / f'{game}_checks.json').write_text(json.dumps({'terminal_guard': terminal_guard, 'cards': cards_summary}, indent=2))

sources = []
for fn in (am._h_aow_play_hold, am._h_aow_lordship_plus_2, am._spend_lordship,
           em._ev_vodian_treachery, em.apply_lordship_plus_2):
    text, first = inspect.getsourcelines(fn)
    sources.append(f'### {inspect.getsourcefile(fn)}:{first}\n'+''.join(text))
(EVIDENCE / 'sources.txt').write_text('\n\n'.join(sources))
(EVIDENCE / 'results.json').write_text(json.dumps(results, indent=2))
# Each record is mechanically re-runnable from its untouched game checkpoint.
verification = {}
for key, info in results.items():
    from nevsky.state import GameState
    p = GameState.model_validate_json((EVIDENCE / info['state_file']).read_text())
    for a in info['actions']:
        apply_action(p, copy.deepcopy(a))
    verification[key] = {'reproduced': True, 'action_count': len(info['actions'])}
(EVIDENCE / 'verification.json').write_text(json.dumps(verification, indent=2))
print('CONFIRMED_REPRODUCTIONS', json.dumps(verification), flush=True)
