# Long Crusade playtest — confirmed findings

Engine: `394de473fd886f3f5f898dc2d0dcfb3b517253cb` (unchanged).
Scenario: Crusade on Novgorod, boxes 1–16. Seed: `20261010`.

## Completed games

| Trajectory | Completion | Engine outcome | Actions including setup | Save/reload checks |
| --- | --- | --- | ---: | ---: |
| First, resource-aware offensive/defensive policy | Turn 14 | Teutonic Campaign Victory, Russia has no Mustered Lords; VP T5/R0 | 1322 | 66 |
| Reserve policy, Domash and Rudolf retained at home | End of turn 16 | Teutonic VP victory, T3.5/R1 | 1685 | 85 |

Both are automated self-play trajectories with external player policies, not manually selected expert games or a balance study. The reserve variant changes strategy, not rules or victory conditions. Both logs replay exactly to their final states. The primary runtime checks detected no exceptions, stalls, rejected concrete menu candidates, negative resources, or VP-accounting mismatches. Final card checks found no missing/duplicate cards and confirmed all six No Event cards remain in play. Post-game actions are correctly rejected.

**The primary `summary.json` files' zero findings refer only to those runtime checks. They do NOT supersede the confirmed rules/interface defects below.** Follow-up probes branched from actual recorded positions without inventing state, inserting cards, changing dice, or modifying the engine. Their alternative actions did not alter the reported game scores.

## Four confirmed bug groups

### 1. T3 Vodian Treachery conquest bookkeeping

`events.py::_ev_vodian_treachery` directly increments conquest/VP rather than consistently applying common conquest cleanup.

At first-game turn 11, before transcript index 1133, Kaibolovo was already Teutonic-Conquered. Playing the genuinely held T3 against it succeeds, changes its Conquered marker count **1 -> 2**, and credits Teutonic VP **4 -> 5**.

At a separate, legitimate conquest in turn 10, before index 1050, T3 changes conquest **0 -> 1** and VP **2 -> 3**, but leaves a siege marker in place and leaves the Calendar victory marker at **box 2 instead of 3**.

See `reproductions/treachery_bookkeeping.json` and the corresponding saved states.

### 2. Playable held events omitted from the action menu

The implemented `aow_play_hold` and `aow_lordship_plus_2` actions are not surfaced by `legal_moves.py` in tested legal positions.

* R3 Pogost, turn 4: Aleksandr has **0 Provender**; the Russian menu offers only `fpd_resolve`. A direct legal held-card action adds **4 Provender**.
* T3 Vodian Treachery, turn 10: a legal conquest of Kaibolovo is absent from the menu.
* T17 Dietrich von Grueningen, turn 3: Rudolf's legal +2 Lordship hold is absent.
* R8 Prince of Polotsk, reserve-game turn 15: Domash's legal +2 Lordship hold is absent.

The card reference explicitly allows Pogost at any time, including during another side's activation and while besieged. These are missing choices, not merely weak player-policy decisions.

### 3. Bonus Lordship expenditures also omitted

`legal_moves.py::_muster_moves` compares expenditure with printed Lordship, while `actions.py::_spend_lordship` uses printed Lordship plus the bonus.

After legitimately playing T17 on Rudolf, his budget is **1 + 2 = 3**, but the menu stops after one expenditure. Two further normal `levy_transport` actions succeed through the dispatcher.

The same failure reproduces for Domash with R8: **2 + 2 = 4**, menu stops after two expenditures, while two more normal expenditures succeed. Fixing hold visibility alone will not fix this independent budget bug.

### 4. Veche Option C hides its extra-Muster continuation

From the actual first-game turn-1 Call-to-Arms position (before index 30), choose the offered Option C for Gavrilo. The engine spends the VP marker (**1 -> 0**) and returns `extra_muster: true`, but the next menu contains **only `advance_step`**.

A direct `levy_transport` for Gavrilo succeeds and increases his Carts to four. The player can buy the extra Muster but cannot discover its actions through the menu.

Root area: `legal_moves.py::_call_to_arms_moves` / Call-to-Arms routing. This was reproduced for Veche C specifically. The analogous Legate 2c path merits review during repair but was not independently reproduced here.

## Reproduction material

`reproductions/results.json` contains eight concrete reproductions spanning the four groups, including exact alternative action sequences and their genuine pre-action checkpoints. `reproductions/verification.json` confirms each saved sequence replays. `reproductions/first_checks.json` and `reserve_game_checks.json` contain final terminal/card checks.

Original game: `transcript.json`, `summary.json`, `box_*.state.json`, `final.state.json`.
Reserve game: equivalent files under `reserve_game/`.
Consolidated evidence: `final_review.json`.

Rerun the focused probes on this branch with:

```sh
pip install -e '.[dev]'
python scripts/crusade_finalize.py
```

The scripts are external test/player tools. No engine fixes or changes to `main` were made in this playtest. The tests do not establish correctness of every card, optional rule, or combat-choice combination.
