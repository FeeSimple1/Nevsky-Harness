"""Finalize independently replayable evidence for the completed long games."""
from __future__ import annotations
import copy
import json
import runpy
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'scripts')]
# Keep evidence dictionaries frozen at capture time, not live asset references.
path = ROOT / 'scripts' / 'crusade_reproductions_20261010.py'
text = path.read_text()
anchor = "    print('REPRO', key, json.dumps(results[key]), flush=True)"
replacement = "    results[key] = copy.deepcopy(results[key])\n" + anchor
if replacement not in text:
    assert text.count(anchor) == 1
    path.write_text(text.replace(anchor, replacement))
runpy.run_path(str(path), run_name='__main__')

from nevsky.actions import apply_action
from nevsky.state import GameState
from nevsky.scenarios import refresh_victory_markers
from crusade_diagnostic import snapshot
OUT = ROOT / 'reports' / 'crusade_20261010'
E = OUT / 'reproductions'
results = json.loads((E / 'results.json').read_text())
bookkeeping = {}
for key in ('hidden_hold_T3', 'T3_double_conquest'):
    rec = results[key]
    s = GameState.model_validate_json((E / rec['state_file']).read_text())
    p = s.model_copy(deep=True)
    a = rec['actions'][0]
    target = a['args']['target']
    response = apply_action(p, a)
    markers_before = [b.box for b in s.calendar.boxes if b.teutonic_victory_marker]
    markers_after = [b.box for b in p.calendar.boxes if b.teutonic_victory_marker]
    fixed_markers = p.model_copy(deep=True)
    refresh_victory_markers(fixed_markers)
    expected = [b.box for b in fixed_markers.calendar.boxes if b.teutonic_victory_marker]
    bookkeeping[key] = {'box': s.meta.box, 'target': target, 'action': a,
        'conquered_before': s.locales[target].teutonic_conquered,
        'conquered_after': p.locales[target].teutonic_conquered,
        'siege_before': s.locales[target].siege_markers,
        'siege_after': p.locales[target].siege_markers,
        'vp_before': s.calendar.teutonic_vp, 'vp_after': p.calendar.teutonic_vp,
        'vp_markers_before': markers_before, 'vp_markers_after': markers_after,
        'vp_markers_expected_from_live_score': expected, 'result': response}
(E / 'treachery_bookkeeping.json').write_text(json.dumps(bookkeeping, indent=2))
# Rebuild boundary summaries from immutable checkpoints, not retained references.
for folder in (OUT, OUT / 'reserve_game'):
    states = [GameState.model_validate_json(f.read_text()) for f in sorted(folder.glob('box_*.state.json'))]
    states.append(GameState.model_validate_json((folder / 'final.state.json').read_text()))
    (folder / 'boundaries.json').write_text(json.dumps([snapshot(s) for s in states], indent=2))
review = json.loads((OUT / 'review.json').read_text())
checks = {g:json.loads((E / f'{g}_checks.json').read_text()) for g in ('first','reserve_game')}
summary = {'games': {g:json.loads((folder / 'summary.json').read_text()) for g,folder in (('first',OUT),('reserve_game',OUT/'reserve_game'))},
           'confirmed_reproductions': {key:{k:v for k,v in val.items() if k not in ('card','menu_types','actions','assets_before','assets_after')} for key,val in results.items()},
           'treachery_bookkeeping': bookkeeping,
           'card_conservation_issues_first_game': review['issues'],
           'final_checks': checks}
(OUT / 'final_review.json').write_text(json.dumps(summary, indent=2))
print('FINAL_REVIEW', json.dumps({'reproduction_count':len(results),'treachery':bookkeeping,
      'card_conservation_issues_first_game':len(review['issues']),
      'terminal_guards':{g:checks[g]['terminal_guard'] for g in checks}}), flush=True)
