# Playtests

Playtest issues that require user interpretation are logged here.

Phase 0 stub.

## Fable interactive playtest — crusade_on_novgorod (2026-06-11)

Two LLM-driven games of the full campaign scenario through `nevsky.llm`
(seeds 42 and 7). Three engine bugs found and fixed (regression tests in
`tests/test_play_fable_fixes.py`):

- **PLAY-1 — AoW decks were never shuffled (3.1.1).** `aow_shuffle` was
  only enumerated when the deck was empty, and nothing shuffled at Levy
  entry, so every game drew the sorted sequence T1+T10 / R1+R10 ...
  regardless of seed. Fix: `_h_aow_draw` performs the 3.1.1 shuffle
  (deck + discard) before drawing, once per side per Levy.

- **PLAY-2 — Avoid Battle ended the Marching side's card.** Per 4.3.4 a
  fully-Avoided Approach yields no Battle; only Battle/Storm (4.4.4
  Recovery) or Encamp (4.3.5) ends the card. Fix: attacker's card
  continues with remaining actions unless the Approach left it
  Besieging.

- **PLAY-3 — Stale Siege markers (4.3.5) when besiegers left by Avoid
  Battle, by the Approach branch of `cmd_march`, or by `cmd_sail`.**
  Observed live: Hermann "Besieged" inside Teuton-Conquered Izborsk by
  nobody, locked to Sally/Pass with Sally raising `no_defenders`. Fix:
  all three departure paths now run `_lift_siege_if_no_besiegers`.

Open items from the playtest — all four since resolved against the
rulebook (`sources/NevskyRules_Second_Edition.pdf`) and Playbook
(`sources/Nevsky_PLAYBOOK-FINAL.pdf`); see
`tests/test_play_fable_palette.py`:

- **R10 Steppe Warriors at first Levy with neither Suzdal brother
  Mustered — harness CORRECT, no change.** The Playbook's Watland
  walkthrough covers this exact draw: "Even though the Capability
  applies only to the Lords Aleksandr and Andrey and neither is
  currently Mustered, the player keeps the Capability because it is
  not a This Lord card (3.1.2)." The this_lord auto-discard branch is
  likewise per the Playbook (a This Lord card with no eligible
  Mustered Lord is discarded without redraw).
- **PLAY-4 (fixed):** `pay_with_coin`/`pay_with_loot` candidates now
  carry a per-payer `targets_by_payer` map mirroring 3.2.1/3.2.2
  (own Service or co-located Lord; Besieged target only from a payer
  Besieged with him); the `targets` union no longer advertises
  unreachable Lords.
- **PLAY-5 (fixed):** 4.3.1 Marshal group March is now enumerated (one
  full-group variant per destination when the active Lord currently
  fills a Marshal role; any subset remains legal via `args.group`).
  Lieutenant pairs were already handled (SMOKE-146).
- **PLAY-6 (fixed):** 4.9.4 Wastage now honors the owner's choice via
  `args.wastage = {lord_id: "<asset_type>" | "capability:<card_id>"}`
  per the rulebook example (two Boats trigger; owner may discard a
  Boat, the singleton Provender, or the This Lord card). Unspecified
  Lords keep the deterministic auto-discard, and the
  `end_campaign_resolve` palette entry surfaces qualifying Lords and
  their discardable items.

## Fable adversarial audit pass (2026-07-05/06)

Three parallel rules-vs-code audits (siege/avoid/withdraw/sally;
End-Campaign/Calendar/Veche; Battle Array/group March/capabilities),
every finding verified against `reference/*.txt` and the 2E rulebook
PDF before any change. Nineteen divergences fixed as PLAY-7..25
(regression tests in `tests/test_play_fable_fixes.py`); commits
53ed45f, 12a9c0d, c5df418, 652d686, 71c12c2, 15df8b3.

Highlights: 4.5.1 Surrender never removed Siege markers (and added
Siegeworks); battle-retreat departures left stale Sieges (the PLAY-3
family's missing path); winning a Battle outside an enemy Stronghold
didn't begin the Siege; **winners never rolled 4.4.4 Losses** (the
SMOKE-093/098/099 lineage rests on a misquote — printed 4.4.4 says
"both sides", and 4.5.2 makes even Sacking Storm attackers keep Routed
units only on a 1); fully-Routed losers were denied the 4.4.3
Retreat/Withdraw/Removal choice; T6/R6 Ambush suppressed the wrong
side whenever its owner attacked; Wastage ran before Plow & Reap;
Levy Disband (3.3) was skippable; Conquered Strongholds defended with
their static-territory side (PLAY-25).

### Verified-correct notes (do not re-flag)
- R10 Steppe Warriors first-Levy handling (Playbook-verified, above).
- Array order/geometry, Flanking targeting, strike initiative, Pursuit
  halving, storm 6-hit melee cap, garrison-first absorption, sally RAID
  and forced Withdraw, Losses thresholds for losers, Lieutenant
  placement constraints, group shared-Transport Laden math, capability
  eligibility gating both directions, Veche/Legate CtA machinery,
  disband box math, 3.1.1 shuffle, Pay per-payer targeting.

### Known open items (audited, reproduced, NOT yet fixed)
Ordered by expected impact; probe scripts described in the audit
transcripts (not committed).

1. ~~**4.3.4 partial Avoid/Withdraw.**~~ RESOLVED 2026-07-06 as PLAY-26.
   `avoid_battle` / `withdraw` now take an optional `lords` subset and
   stay non-terminal while outside defenders remain, so the Inactive
   side can Avoid "some or all" to "one or more adjacent Locales",
   Withdraw "some or all ... up to Siege Capacity" (cumulative cap via
   `CombatPending.withdrawn_lords`), and the remainder Stands. Bare
   `avoid_battle{to}` / `withdraw{}` keep the all-defenders behavior.
   Enumerator offers per-Lord variants. Regression:
   `tests/test_play26_partial_avoid_withdraw.py`.
2. ~~**4.4.2 remaining Hits after a mid-step Rout.**~~ RESOLVED
   2026-07-06 as PLAY-27. When a struck target Routs with Hits still
   unapplied, `_apply_row_spillover` carries them to the surviving
   Lords in the SAME Array row (closest slot first, cascading); a
   fully-Routed row ignores them (4.4.2). `_resolve_hits` now reports
   `applied` so leftover = hits - applied. Raven's Rock Walls re-apply
   to spillover onto a Russian target in Melee Round 1. The operator's
   *choice* of absorber when equidistant remains open item #3.
   Regression: `tests/test_play27_rout_hit_spillover.py`.
3. ~~**4.4.2 Flanking absorb choice.**~~ RESOLVED 2026-07-06 as
   PLAY-28. New `flank_absorb` decision: when a striker is directly
   OPPOSED to its target and the target's side has Front Lord(s)
   Flanking that striker (and no enemy Flanks the target), the target's
   owner may redirect the striker's Hits onto a Flanking Lord instead
   (helper `_front_flankers_of`). Fallback keeps the opposed Lord, so
   behavior is unchanged unless the operator elects. Front row only (the
   documented geometry). Regression:
   `tests/test_play28_flank_absorb_choice.py`.
4. **4.4.3 Retreat gates.** Retreat legality omits the "Unbesieged"
   qualifier on enemy Lords/Strongholds (a Locale where your own side
   besieges the enemy is wrongly barred — can escalate to permanent
   removal); destination is auto-picked (first legal neighbor), and
   voluntary removal is never offered. Sally-retreat additionally
   blocks enemy-Conquered Locales (SMOKE-049 note mislabels 4.4.3).
5. **4.3.4 Avoid destination gates + palette mismatch.** Handler
   over-restricts (blocks Besieged enemy strongholds and
   enemy-Conquered trade routes); enumerator conversely offers
   destinations the handler rejects, and skips the parallel-Way
   avoid-back-along-other-Way case the handler permits.
6. **4.8.1 Feed sharing.** Surplus-only sharing violated: an
   earlier-iterated Lord eats a co-located Lord's NON-surplus
   Provender (the wrong Lord goes Unfed and takes the Service shift);
   provender-vs-loot order and donor choice are hard-coded; T8
   Hillforts' skip-Lord is auto-picked.
7. **4.8.2 Pay window.** Opens only when a Disband is pending; SoP has
   Pay after every Command card ("Lords may Pay or Disband").
8. **4.4.2 Reposition Advance slot choice** (lone Reserve forced
   leftmost); **4.0 excess side-capability discard** auto-drops the
   list tail (owner should choose); **Spoils distribution** goes to a
   single recipient with over-cap overflow vanishing (4.4.3 "divide
   among them", 4.5.2 "distribute as desired"); **Avoid Provender cap**
   ignores shared Transport (4.3.4 "own or shared"); **Veche-A /
   Legate-2b Calendar-edge** slides clamp at box 1 / reject off-right
   instead of 2.2.3 off-edge placement (incl. a VP-burning no-op Veche
   A offered at box 1).
9. **Battle-hold palette surfacing.** Tier-2 holds are reachable only
   via stand_battle args; the palette never names them (parity note,
   not a rules divergence).

### Questions logged for the user
- Q-010 — RESOLVED 2026-07-06 (D-Q010): rules-literal. Storm (4.5.2) and
  Sally (4.5.3) cost one Command action; D-R203's pristine gate narrowed
  to Siege/Sail/Tax (+ Stone Kremlin / Stonemasons).
- Q-011 — RESOLVED 2026-07-06 (D-Q011): the resolve_battle max_rounds=10
  cap is lifted (default None -> far safety bound + no-progress guard).
