# Final audit addendum: four new bug groups in total

This extends `REPORT.md` for engine `d1ed51f9b5e78039e0b307bb2ad91c89bd366303`, Crusade on Novgorod seed **20261011**. Both completed games remain 1,742 actions / 16 turns / 87 successful save-reload checks each. No engine file or main-branch change was made.

## NEW-SEED-4: Mindaugas changes numeric VP but not the Calendar marker

A final independent audit checked the Calendar victory-marker flags at every saved pre-action position, separately from the runtime numeric-score-versus-board-marker accounting check. It found a fourth defect, directly present in the recorded games:

| Actual recorded event | Position | Numeric score | Calendar marker after event |
| --- | --- | --- | --- |
| T15 Mindaugas, Ravage Ostrov | Turn 7; action 652 (one-based) in both runs | Teutonic 0.5 to 1.0 | No box flagged; box 1 should be flagged |
| T15 Mindaugas again | Turn 12; action 1,227 in ordered run | Teutonic 0.5 to 1.0 | No box flagged; box 1 should be flagged |
| R12 Mindaugas, Ravage Rositten | Turn 13; action 1,330 in ordered run | Russian 0.5 to 1.0 | No box flagged; box 1 should be flagged |

The source is `events.py::_ev_mindaugas_t` and `_ev_mindaugas_r`: each directly adds 0.5 to the numeric score without calling the shared `refresh_victory_markers`. The marker remains stale until a later action happens to synchronize it. The numeric VP award itself is correct; this is a board/Calendar representation bug, and it did not change either recorded winner.

This is not a recurrence of the previous T3 fix: T3's synchronization repair is present and its existing regression still passes. These are additional immediate-event paths with the same class of missing synchronization.

The saved-position checks found 123 stale-marker observations in the initial run and 622 in the ordered run. These are repeated observations of stale state, NOT hundreds of independent bugs; they also include an intermediate end-campaign Grow window. No opposing unbesieged-Lord co-location anomaly was found. The report's clean numeric score/board-marker accounting result does not cover these separate Calendar display fields.

## Final verification totals

- Four new defect groups: Muster interleaving, post-shift readiness, final-turn Wastage/Reset ordering, and immediate-event Calendar marker synchronization.
- **Six intended-behavior regression cases fail on the unchanged current engine**, reproducing the four groups: interleaving (1), readiness (1), final-turn cleanup (2 factions), Mindaugas marker synchronization (2 factions).
- **38 existing long-campaign-fix regression tests passed**; the entire pre-existing 1,725-test suite was not rerun for this playtest.
- Both 1,742-action logs were independently replayed again; exact results and final states matched, recorded winners matched, terminal actions were rejected without mutation, and each faction retained all 21 AoW cards exactly once, including its three No cards.
- The main game with the player's sequential-Muster safeguard ended at turn 16 with **Teutonic victory 1–0.5**. The earlier menu-driven diagnostic ended at turn 16 with **Russian victory 0.5–0**, but includes the illegal interleaving the engine allowed. Neither result is a balance estimate or a prediction after all fixes.

The accompanying `nevsky-seed-20261011-evidence.zip` contains the complete evidence for all four groups, including six failing regression cases and the successful prior-regression log. These defects are diagnosed, not repaired.
