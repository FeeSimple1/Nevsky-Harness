"""Replay review and a second long-scenario policy; no engine modification."""
from __future__ import annotations
import copy
import inspect
import json
import sys
from collections import Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'scripts')]
import nevsky.actions as actions
import nevsky.campaign as campaign
from nevsky.actions import apply_action, IllegalAction, _HANDLERS, _find_service_marker_box
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import load_scenario
from nevsky.static_data import load_cards
import crusade_diagnostic as driver

OUT = ROOT / 'reports' / 'crusade_20261010'
transcript = json.loads((OUT / 'transcript.json').read_text())
s = load_scenario('crusade_on_novgorod', seed=20261010)
interesting, issues, windows = [], [], []
seen_windows = set()
source_text = []
for name in sorted(_HANDLERS):
    if any(term in name for term in ('lordship', 'muster', 'legate_use', 'veche')):
        fn = _HANDLERS[name]
        lines, start = inspect.getsourcelines(fn)
        source_text.append(f'### {name}: {inspect.getsourcefile(fn)}:{start}\n' + ''.join(lines))
for module, name in ((actions, '_spend_lordship'), (actions, '_h_advance_step')):
    fn = getattr(module, name)
    source_text.append(f'### {name}\n' + inspect.getsource(fn))
(OUT / 'choice_handler_sources.txt').write_text('\n\n'.join(source_text))
for i, row in enumerate(transcript):
    side = s.meta.active_player or 'teutonic'
    raw = legal_moves(s, with_previews=False)
    if s.meta.phase == 'levy':
        held = getattr(s.decks, side).holds
        extra = s.legate.extra_muster_target_lord if side == 'teutonic' else s.veche.extra_muster_target_lord
        bonus = dict(s.meta.lordship_bonus)
        for cid in held:
            if cid not in ('T3', 'R3'):
                continue
            key = (s.meta.box, side, s.meta.levy_step, cid)
            if key not in seen_windows:
                seen_windows.add(key)
                windows.append({'kind': 'lordship_hold', 'action_index': i, 'box': s.meta.box,
                                'side': side, 'levy_step': s.meta.levy_step, 'card': cid,
                                'menu_types': sorted({a['type'] for a in raw})})
        if extra:
            key = (s.meta.box, side, extra)
            if key not in seen_windows:
                seen_windows.add(key)
                windows.append({'kind': 'extra_muster', 'action_index': i, 'box': s.meta.box,
                                'side': side, 'target': extra, 'menu': raw})
        if bonus:
            key = (s.meta.box, side, 'bonus')
            if key not in seen_windows:
                seen_windows.add(key)
                windows.append({'kind': 'lordship_bonus', 'action_index': i, 'box': s.meta.box,
                                'side': side, 'bonus': bonus, 'menu': raw})
    prior = {lid: (l.state, l.location) for lid, l in s.lords.items()}
    vp_before = [s.calendar.teutonic_vp, s.calendar.russian_vp]
    action = row['action']
    result = apply_action(s, copy.deepcopy(action))
    changed = {lid: {'before': p, 'after': [s.lords[lid].state, s.lords[lid].location]}
               for lid, p in prior.items() if p[0] != s.lords[lid].state}
    vp_after = [s.calendar.teutonic_vp, s.calendar.russian_vp]
    if changed or vp_before != vp_after or action['type'] in ('cmd_storm', 'stand_battle', 'withdraw', 'avoid_battle', 'veche_action'):
        interesting.append({'index': i, 'box': row.get('box'), 'action': action,
                            'roster_changes': changed, 'vp_before': vp_before, 'vp_after': vp_after,
                            'result': result if action['type'] not in ('cmd_storm', 'stand_battle') else {k:v for k,v in result.items() if k != 'battle'}})
    for sd in ('teutonic', 'russian'):
        d = getattr(s.decks, sd)
        occurrences = Counter()
        for zone in ('deck', 'discard', 'removed', 'holds', 'pending_draw', 'capabilities_in_play', 'this_levy_events', 'this_campaign_events'):
            occurrences.update(getattr(d, zone, []))
        for l in s.lords.values():
            if l.side == sd:
                occurrences.update(l.this_lord_capabilities)
        expected = {cid for cid, c in load_cards().items() if c['side'] == sd}
        bad = {cid: occurrences[cid] for cid in expected if occurrences[cid] != 1}
        if bad and not any(x.get('side') == sd and x.get('bad') == bad for x in issues):
            issues.append({'kind': 'card_conservation', 'index': i, 'box': s.meta.box, 'side': sd, 'bad': bad,
                           'deck_fields': d.model_dump()})
(OUT / 'review.json').write_text(json.dumps({'interesting': interesting, 'windows': windows, 'issues': issues}, indent=2))
(OUT / 'review_summary.json').write_text(json.dumps({'interesting_events': len(interesting), 'windows': windows, 'issues': issues,
                                                   'handler_names': sorted(_HANDLERS)}, indent=2))
print('REVIEW', json.dumps({'events': len(interesting), 'windows': len(windows), 'issues': len(issues)}), flush=True)
# Exercise late-season transitions by keeping a defensible, tax-funded reserve
# at Novgorod/Wenden rather than sending every available Lord forward.
source = (ROOT / 'scripts' / 'crusade_diagnostic.py').read_text()
source = source.replace("OUT = ROOT / 'reports' / 'crusade_20261010'", "OUT = ROOT / 'reports' / 'crusade_20261010' / 'reserve_game'")
anchor = "        if typ in ('cmd_march', 'cmd_sail'):\n            dest = args.get('to') or args.get('destination')"
replacement = "        if typ in ('cmd_march', 'cmd_sail'):\n            if lid in ('domash', 'rudolf') and l.location in _seats_of(s, lid):\n                return -40\n            dest = args.get('to') or args.get('destination')"
assert source.count(anchor) == 1
source = source.replace(anchor, replacement)
source = source.replace("'policy': 'resource-aware automated play, with explicit raw-JSON legal requests'", "'policy': 'resource-aware automated play with Domash/Rudolf home reserves and explicit raw-JSON legal requests'")
namespace = {'__name__': 'reserve_policy', '__file__': str(ROOT / 'scripts' / 'crusade_diagnostic.py')}
exec(compile(source, namespace['__file__'], 'exec'), namespace)
namespace['run_game']()
