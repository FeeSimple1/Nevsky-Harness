# Fixes from Crusade seed 20261011

Date: October 10, 2026. Baseline: `d1ed51f9b5e78039e0b307bb2ad91c89bd366303`.
Evidence: the complete Crusade on Novgorod playtest with seed **20261011**.

## Corrections

1. **Ordinary Muster order (3.4).** The menu and authoritative Lordship
   spender both reject returning to a Lord after another Lord begins.
   `meta.muster_lord_order` persists this order through save/reload. An
   unsuccessful Fealty roll still starts a Lord's Muster, while an illegal
   rejected request does not change the order. Extra Musters from Veche C
   and Legate 2c are independent; their actions remain available. The order
   resets at the next ordinary Muster and expires at Call to Arms.
2. **Readiness after Calendar shifts (3.4.1, T7 and other shifts).** Eligibility
   uses the actual cylinder position for ordinary Muster, Veche B and
   Legate 2a. Disbanded cylinders at or left of Levy can be recruited without
   waiting for the next segment. Successful actions refresh their stored
   display status. Removed and on-map Lords remain ineligible, and a
   cylinder shifted right of Levy is still unavailable.
3. **Final-turn sequence (4.9.1–4.9.5).** Both sides complete Grow before
   determining the winner. The final turn performs no Plow and Reap,
   Wastage, Reset, Serf removal, Lieutenant unstacking or Calendar advance.
   The menu omits final-turn Wastage and Reset choices. Earlier saved
   end-Campaign requests that included cleanup selections no longer cause
   those selections to execute after Game End. Non-final turns retain their
   normal cleanup. Each half of Grow synchronizes the Calendar VP marker.
4. **VP marker synchronization.** Both Mindaugas events (T15/R12) synchronize
   the Calendar marker immediately after awarding the half-point. Fresh
   verification exposed the corresponding downward-score bug in Bountiful
   Harvest (T14/R18); those paths are corrected too, including crossing
   below 1 VP. The existing 17.5-point cap remains enforced.

Rules basis: the repository's `reference/Nevsky_Sequence_of_Play.txt`, 3.4,
3.4.1 and 4.9, and `reference/Nevsky_Arts_of_War_Reference.txt`, the named
Hold and immediate Events. No variant, house rule or strategy was added to
the rules engine.

## Regression evidence

All **six** original intended-behavior reproductions failed against the
unchanged baseline and passed after correction. The permanent new test
module contains **46** cases: the six saved-position behaviors plus both
factions, save/reload, failed recruitment, invalid-action rollback, extra
Muster independence, readiness boundaries, terminal ordering, marker
thresholds/cap, Bountiful Harvest, and a complete legal campaign replay.
The six source fixtures preserve the actual captured board/Calendar/cards;
only append-only history is omitted. Additional synthetic edge fixtures are
separate tests, not claimed to be played positions.

The **84** focused cases (46 new plus 38 prior long-campaign cases) pass.
The old 1,322- and 1,685-action logs retain their original data, but action 18
in each contains the newly prohibited Hermann → Knud & Abel → Hermann
interleaving. Their tests now require rejection at that exact action and
verify rollback, rather than bypassing the corrected rule to make an
invalid game replay. Full-trajectory coverage is replaced by the valid
**1,742-action**, 16-turn ordered game with seed 20261011, checking its
recorded Teutonic **1–0.5** victory, **87** save/reload checks and complete
card conservation. The two final actions preserve mats rather than
reproducing the old erroneous Wastage.

## Validation commands

- `PYTHONPATH=src python -m pytest -q -n 4`
- `PYTHONPATH=src python scripts/fuzz_invariants.py --seeds 1-25`
- `python -m ruff check src/nevsky/held_actions.py tests/test_seed_20261011_fixes.py`
- `python -m compileall -q src tests/test_seed_20261011_fixes.py`
- `git diff --check`

The isolated repair workflow records completed full-suite and sweep results
below before committing the tested engine files. Temporary transport and
validation workflow files are excluded from the published tree.

## Completed validation

- Full GitHub Actions Python 3.12 suite: **1,771 passed**, zero failures, errors or skipped cases.
- Independent local Python 3.13.5 full suite: **1,771 passed**.
- Focused suite: **84 passed** (46 new cases and 38 prior long-campaign cases).
- The six original intended-behavior checks failed on the baseline and pass after correction.
- Invariant sweep: **150 clean cases** on both GitHub and the local runtime.
- Complete 1,742-action ordered campaign replay passed, including 87 save/reload checks.
- A fresh external-policy game on the corrected engine completed all 16 boxes, with Teutonic victory 1-0.5, 1,742 actions, 87 successful save/reload checks and no recorded runtime findings. This is a smoke test, not a balance estimate or exhaustive rules proof.
- Targeted Ruff, compilation and git diff --check passed.

Remote evidence: Actions run `38073036168`, JUnit and invariant-log artifact `nevsky-seed-repair-results`.
The SHA256-verified patch was applied to the pinned source, tested, and committed only after every gate passed. Temporary transport and repair workflow files were removed before this commit. The ordinary CI workflow is unchanged.
