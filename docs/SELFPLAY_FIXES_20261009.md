# Fixes from the Pleskau self-play

Baseline: `8fff2ad6419ee541d2bf27fa73fc85fed059bd70`.
Original diagnostic branch: `playtest/nevsky-selfplay-20261009`.
Verified repair commit: `78c4da3109994870cce4ea8bf57cb130ad117b6f`.

## Corrections

| Defect | Correction |
| --- | --- |
| The planning menu hid a Lord after the first Command card | Offer that Lord while the plan contains fewer than three copies; preserve seasonal plan size and the handler's fourth-copy rejection. |
| Ordinary Pleskau disbands awarded no points | Both permanent removal and at-limit Disband use `_award_lord_departure_vp`, updating the opposing live VP, accumulated departure counter, and Calendar marker together. |
| Forced actions were omitted from the helper's history | Manual and automatic success paths share `_record_action`; failed automatic actions do not advance the turn or enter completed history. |
| Filtered menu failures could produce a false clean summary | `over_enum_filtered` is notable; all diagnostics print with complete details, and only an empty findings list produces the clean summary. |

Pleskau credit applies only to a Mustered Lord actually on the map before
leaving it. Duplicate cleanup and removals of already off-map or
scenario-excluded Lords do not award points. A genuinely new departure after
re-Mustering remains eligible. Other scenarios do not receive the bonus, and
the existing 17.5-VP cap is preserved.

The rules basis is the repository's Pleskau Victory section in
`reference/Nevsky Scenario Reference.txt` (Disbands **or** is removed from the
map), and the three Command cards per Lord already correctly enforced by
`campaign.py::_h_plan_add_card` (1.9.2 / 4.1). No house rule, agent policy in
the engine, or save-schema change was introduced.

## Permanent regression coverage

`tests/test_selfplay_fixes_20261009.py` adds 37 regression cases covering both
sides, all three seasonal plan lengths, both Levy and Campaign departure
entry points, scoring guards, VP cap, save/reload, helper history replay,
failed automatic actions, and filtered/unknown diagnostic reporting.

`tests/data/pleskau_selfplay_20261009.json` retains the original 179 actions,
run-length encoded without changing their order. The replay now verifies a
**Russian 3–1 victory**, with credit for Gavrilo's removal, Yaroslav's Levy
Disband, and Knud & Abel's Campaign Disband. This is the identical recorded
game through the fixed engine, not a prediction about different choices.

A separate automated, combat-oriented self-play uses the corrected menu and
checks the departure counters against actual map departures after each action.
It completed after 147 post-setup actions, with Russian Campaign Victory under
5.2 when the Teutons had no Mustered Lords left; the recorded VP was T1/R4.
It is a smoke/regression game, not expert or manually selected play.

## Validation

The isolated repair runs used Python 3.12.15. The first run's game and full
suite passed, but its final lint gate caught formatting and a loop-variable
binding in the new test module. Those test-only issues were corrected; the
second run passed every gate and published the verified repair commit above.

- New tests on the unmodified baseline: **22 failed, 15 passed**, reproducing
  the missing legal moves, missing disband points, incorrect off-map credit,
  incomplete history, and misleading diagnostics.
- New tests after correction: **37 passed**, including the exact original
  game replay and a fresh menu-driven self-play.
- Complete suite: **1,687 passed** (1,650 existing plus 37 new cases).
- `python scripts/fuzz_invariants.py --seeds 1-25`: **150 games clean on
  invariants I1–I12**, covering Pleskau, Watland, and Crusade on Novgorod with
  priority and random policies.
- `ruff check tests/test_selfplay_fixes_20261009.py`: passed on the final run.
- `git diff --check`: passed.

Evidence: GitHub Actions repair run `38024257687`, job `114131620422`;
first-run detailed before/after results in run `38024150775`, job
`114131296506`. The temporary repair workflow and one-shot patch script were
removed before the verified code was committed. The existing CI workflow is
unchanged. These checks validate the repaired behavior; they do not establish
that every game rule or every possible trajectory is bug-free.
