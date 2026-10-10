# Sustained validation pass — October 10, 2026

Baseline: `2258489c657403331cc3de5d67fd455b0af88bce`.

## Findings and repairs

### Movement menu under-enumeration

A real Crusade seed-20261012 combined-force position in turn 7 had Yaroslav
at Odenpah, Converts, Light Horse and one Command action remaining. The menu
offered no March. The handler accepted March to Dorpat, discarded cargo
beyond the seasonal transport limit, and correctly charged zero actions.

The menu had compared the pre-discard, undiscounted solo cost before even
considering a full Marshal group. Related intended-behavior tests exposed
hidden legal discard-to-Unladen choices and shared-transport group moves.

A pure `_march_action_cost` now controls the menu and handler. The menu
calculates cost after the declared discard, includes the group-wide Converts
benefit and checks each group independently. Keeping cargo and spending two
actions versus discarding cargo and spending one are separate player choices.
Lieutenant/Lower pairs remain together. The repair adds no movement rule.

Rules: Arts of War T3 and Commands 4.3.1–4.3.2 / 1.7.2. The captured position
is retained in `tests/data/convergence_20261010/converts_march.json`.
The 27 movement regressions had 11 failures and 16 passes before correction;
all 27 passed afterward.

### First-Levy duplicate-Capability deadlocks

The expanded invariant sweep exposed four actual stalls: Crusade seed 32
and Watland seed 48, each under priority and random policies. In Crusade,
Gavrilo had received R5 Druzhina and the pending R6 was another Druzhina;
no other on-map Lord could receive it. In Watland, Andreas had T7 Warrior
Monks and the pending T15 was another Warrior Monks, again with no other
assignable on-map recipient. The menu offered an automatic discard, but the
handler demanded a Lord target and rejected the only move.

A shared assignment predicate now includes coats of arms, duplicate names
and the two-card mat limit. A This Lord card that cannot be assigned returns
to discard, not permanent removal. An existing Capability is preserved. An
available alternative recipient must be used rather than bypassed by a bare
discard. Explicit duplicate or invalid assignments still reject atomically.

Rules: 3.1.2's unassignable This Lord card branch, 3.4.4, and Q-R190-A in
`RULES_DECISIONS.md`. Eleven additional regressions cover the captured
positions, explicit bad targets, alternative recipients, full mats, and all
four formerly stalled seed/policy combinations.

### Test-reporting failure

The old invariant driver broke out when no candidate could be applied and
then returned a clean invariant check. It also did not distinguish hitting
its step limit from Game End. These paths can mask a deadlock without any
state-invariant violation. Its output now reports explicit completion and
stop reasons, and unrecoverable rejection fails. `--require-completion`
also fails a step-limited run. Six reporting/gate regressions prevent a
completed-but-flagged or unfinished game from being counted as clean.

## Method

Six baseline multi-policy games first located the movement issue. A first
post-movement-fix batch of 24 games had no recorded findings, but the expanded
invariant sweep then exposed the opening deadlocks. The clean-build gate was
reset and rerun after that repair. An intermediate unused-seed batch was
interrupted, not counted as a completed clean batch.

The final reusable protocol is in `docs/VALIDATION_PROTOCOL.md`. Complete
play logs, position streams, final saves and independently replayed results
are retained as validation evidence. The human-style player heuristics remain
external test code, not engine rules or claims of expert play.

## Verification

The final local and GitHub validation totals are appended only after their
respective gates complete. A clean batch means no errors found by those
checks, not that every game rule or every possible trajectory is proven.

## Completed final-build validation

- Full local Python 3.13.5 suite: **1,815 passed**, no failures, errors or skips.
- Full GitHub Actions Python 3.12 suite: **1,815 passed**, no failures, errors or skips, verified from JUnit.
- **44 new regression cases**: 27 movement, 11 opening deadlock/assignment, and 6 reporting/gate checks.
- On both platforms, **600 of 600 invariant cases reached Game End**, with no violations or step-limited cases. These include short scenarios and early victories, not 600 full-length Crusades.
- On both platforms, **3,000 opening prefixes** across six loadable scenarios cleared without failure; the local run checked 29,950 offered choices. Prefixes are not counted as games.
- Local final-build campaign gate: **48 of 48 completed cleanly**, **42 reached turn 16**, **76,635 actions** and **3,851 save/reload checks**; every complete log replayed exactly and the source digest was unchanged.
- GitHub final-build campaign gate: **48 of 48 completed cleanly**, **42 reached turn 16**, **76635 actions** and **3851 save/reload checks**; all replay and source-integrity gates passed.
- Targeted Ruff checks on new test/player modules, compilation and git diff --check passed.

Remote evidence: Actions run `38076279743`, artifact `nevsky-convergence-results`. The second platform reruns the same 48 cases; it does not create 48 additional independent seeds.

The local campaign gate exercised 2,180 Marches, 37 field-Battle responses, 35 Storms, 21 Sallies, 50 Sails, 336 Lordship Hold plays, 165 other Hold plays and 128 Lieutenant placements. No Legate-use or Stonemasons command was selected in that batch; those remain covered only by targeted tests or earlier work, not by a new full-game trajectory here. Counts of actions do not imply every legal target or argument combination was tested.

This is a sustained clean batch under the documented checks, not a guarantee that every possible game state is bug-free. A newly confirmed defect resets the clean-build gate. Temporary source-export and patch-transport workflows are excluded from the final code tree; ordinary CI is unchanged.
