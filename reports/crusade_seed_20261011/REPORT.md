# New-seed Crusade playtest — October 10, 2026

Engine: `d1ed51f9b5e78039e0b307bb2ad91c89bd366303` (unchanged).
Scenario: `crusade_on_novgorod`, all 16 Calendar boxes.
New seed: **20261011**; the preceding long-campaign test used 20261010.

## Completed games

| Run | Policy | Actions including setup | Final box | Engine result |
| --- | --- | ---: | ---: | --- |
| Initial diagnostic | Resource-aware menu-driven play, with Rudolf and Domash home reserves | 1,742 | 16 | Russian 0.5–0 |
| Sequential-Muster follow-up | Same new seed and general policy, but each Lord finishes ordinary Muster before the next starts | 1,742 | 16 | Teutonic 1–0.5 |

Both sides were automated by an external player script. The policy considers resources and public positions, not future dice results. Optional non-combat Holds and extra Musters were included. Both games had 87 successful save/reload checks: **174 combined**. Both complete logs replayed exactly, including action results and final state: **3,484 combined actions**. These are two policies on one new seed, not independent random samples or a balance study.

The initial game exposed illegal Muster interleaving accepted by the engine. Its result is therefore an engine diagnostic, not a certified rules-valid game. The follow-up avoided that behavior in the player policy without changing the engine. This is not a scoring correction to the first result.

## NEW-SEED-1: Ordinary Muster permits returning to an earlier Lord

Directly observed in the initial game's first Levy, actions **16–18** (one-based):

1. Hermann attempts to Muster Rudolf at Wenden.
2. Knud & Abel Levy a Cart.
3. Hermann Levies a Cart.

Every action was offered and accepted. Rule 3.4 requires each Lord to finish all his actions before the next Lord begins. The engine checks individual budgets but does not remember which Lords have finished their Muster; both the menu and handler permit returning to Hermann. The sequential-Muster follow-up contains no such returns.

Rules: `reference/Nevsky_Sequence_of_Play.txt`, lines 146–156.
Code: `actions.py::_spend_lordship` (lines 1997–2034), `legal_moves.py::_muster_moves`.
Impact: illegal order of Levy decisions and card/resource availability, not merely a presentation issue.

## NEW-SEED-2: A shifted Disbanded Lord remains incorrectly ineligible to Muster

Reproduced from actual **turn-7** positions in both games, before action index **663** (zero-based). This is a legal alternative tested on a saved copy, not the recorded choice and not an edited board.

- Hermann is Disbanded, with his cylinder in box 9; Levy is in box 7.
- Play the genuinely held **T7 Tverdilo** to shift Hermann left two boxes.
- The engine moves his cylinder to box 7 and consumes the Hold.
- His internal state stays `disbanded`.
- Hermann is absent from the Muster menu. A direct request for Andreas to Muster him at the free Seat of Dorpat is rejected: `bad_target: hermann state is disbanded (not 'ready')`.

Readiness is determined by a cylinder at or left of Levy, so the attempt should be available; the Fealty roll may of course fail legitimately. Readiness is refreshed only when entering Muster. `_shift_cylinder` changes the Calendar position without refreshing that status, while `_h_muster_lord` and the menu demand the stale `ready` label.

Rules: Sequence of Play glossary READY and 3.4.1; Arts of War T7.
Code: `events.py::_shift_cylinder` (43–75), `actions.py::_h_advance_step` (424–448), `_h_muster_lord` (2090–2105).
Impact: a legal card-assisted re-Muster is delayed or denied after paying the card cost.

## NEW-SEED-3: Final-turn Wastage runs after the scenario should end

Directly observed in **both full 16-turn games**, for both sides. The printed sequence is Grow (4.9.1), Game End (4.9.2), then Plow/Reap, Wastage and Reset only if the game continues. The handler skips final-turn Plow/Reap but still performs Wastage and Reset before setting game-over.

In the sequential-Muster game, the last two actions unnecessarily discarded:

- Teutons: one Cart each from Rudolf and Yaroslav, and Knud & Abel's T2 capability.
- Russians: Domash's R14 capability, Gavrilo's R16 capability, Vladislav's Boat, and a Karelian Cart.

The correct final-turn Grow removals are NOT defects. The unnecessary Wastage did not change the recorded VP or winner in these positions, but it corrupts the final mats and asks for decisions that should not occur. Blank/default end-campaign requests reproduce the same defect, so this is not caused by explicitly supplying Wastage choices.

Rules: `reference/Nevsky_Sequence_of_Play.txt`, lines 378–426.
Code: `campaign.py::_h_end_campaign_resolve`; Wastage runs at 1950 onward, while the final game-end check is deferred until both sides complete at 2059 onward. The end-campaign menu also advertises these final-turn Wastage choices.

## Verification and limitations

- No exceptions, deadlocks, rejected concrete menu candidates, invariant violations, negative resources, card-conservation failures, score/marker-total mismatches, nondeterministic applications, or save/reload mismatches were recorded by either main run's runtime checks.
- Both sides retained exactly one copy of each of their 21 Arts of War cards, including all six No cards across the decks; post-game actions were rejected without mutation.
- The ordered game exercised 20 Marches, two resolved field Battles, one Storm, six Lordship Hold plays, Pogost, Veche extra Muster, Supply, Pay, seasonal transitions and both year-end Grow steps. It did not use a Legate extra Muster, a T3/T13 Hold, or an opposing-activation Hold interruption. No exhaustive combat or optional-rule coverage is claimed.
- The **38 existing long-campaign-fix regression tests passed** on Python 3.13.5.
- Four new intended-behavior regression cases **fail against the unchanged engine**, reproducing the three groups above (one interleaving case, one readiness case, and final-turn cleanup for each side).
- All **357 tracked files** in the pinned source export match their original bytes. Only external diagnostic scripts and output were added locally. No engine fixes were made and `main` was not updated by this playtest.

Full evidence is preserved in the accompanying downloadable `nevsky-seed-20261011-evidence.zip`: both transcripts, all pre-action positions, turn checkpoints, final saves, player/audit scripts, the four failing rule regressions, successful prior-regression log, source-integrity check and independent replay verification. The diagnostics above are newly identified defects, not fixes.
