# Nevsky validation protocol

The goal is sustained clean play, not merely fixing the latest reported list.
Use a test–reproduce–fix–regress–retest cycle. A new confirmed defect resets the
clean-build gate; results from an older build do not certify its replacement.
The goal is an empirical stopping criterion, not a claim of mathematical
proof that no undiscovered defect exists.

## Repair cycle

1. Read current `main` and pin its exact commit. Keep test-player strategy
   outside `src/nevsky`; use the repository's rules references and adjudications.
2. Run varied complete scenarios and independent rules/state checks. Record
   seed, player policy, every action, actual Game End, checkpoints, and replay.
   Different policies on one seed are different trajectories, not independent
   random samples. An early rules-defined victory is a completed game, but
   is not a full 16-turn campaign.
3. Reproduce each defect from a saved position or minimal legal setup. Write
   an intended-behavior regression that fails before the repair. Fix the
   shared rule predicate when possible, not only a menu symptom. Invalid
   explicit actions must still be rejected without mutation.
4. Rerun the complete regression suite, the failing seeds and new seeds.
   Never weaken assertions merely to obtain green tests or insert a player
   workaround and represent it as an engine fix.
5. Publish only tested code; read back `main` to verify the actual commit.
   Preserve concise repository evidence and the complete downloadable logs.

## Completion-required game gate

```
python scripts/convergence_suite.py \
  --seeds 20261012-20261027 --workers 4 \
  --minimum-full-length 8 --output reports/convergence_unique_run
```

This runs three external player policies: logistics, combined-force and
maritime/capability-focused. It requires every requested case to complete,
no recorded diagnostics, exact full-log replay, and a minimum number of
complete 16-turn trajectories. It hashes the engine and relevant test-player
code before and after the batch and rejects a batch during which that code
changes. Never reuse a populated output directory to accidentally mix builds.

The game driver checks offered-move rejection, state mutation during menu
inspection, deterministic application, save/reload, card conservation,
score/board accounting, Calendar marker display, readiness, Muster order,
Lieutenant pairs, opposing unbesieged co-location and final-turn mat cleanup.
A targeted independent request also checks otherwise-hidden Converts Marches.
Legality probes do not choose moves based on future combat results or dice.

## Complementary checks

```
PYTHONPATH=src python -m pytest -q -n 4
python scripts/fuzz_invariants.py --seeds 1-100 --max-steps 3000 \
  --require-completion --report-json reports/invariants.json
python scripts/check_openings.py --seeds 500 --report reports/openings.json
```

The old bounded invariant sweep could return success after a step limit or
an unrecoverable menu rejection. It now explicitly distinguishes completed,
step-limited and failed cases. Bounded invariant checks remain useful, but
are not evidence of completed games. `--require-completion` makes an
unfinished case fail the command. `check_openings` checks opening prefixes
across all six loadable scenarios and never counts them as full games.

For this pass the practical gate is 48 completed multi-policy Crusade
trajectories on the final unchanged build, including at least eight full
16-turn games, plus the complete regression suite, 600 completion-required
invariant cases and 3,000 opening prefixes. Counts alone are insufficient:
report the exercised and unexercised mechanics. No finite batch certifies
all legal positions, optional-rule combinations or strategic choices.
