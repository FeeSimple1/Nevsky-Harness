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
4. ~~**4.4.3 Retreat gates.**~~ RESOLVED 2026-07-06 as PLAY-29. Shared
   `_legal_retreat_dests` gates Retreat on "no UNBESIEGED enemy Lords or
   Strongholds" (a Besieged enemy Lord/Stronghold no longer bars retreat
   there, so a besieger isn't wrongly escalated to removal). The owning
   player CHOOSES the destination via `args.retreat_to = {lord_id:
   locale}` (Defenders; unspecified -> first legal). The Sally-retreat
   path now uses the same helper -- its extra enemy-Conquered block (no
   such clause in 4.4.3) is removed. Voluntary removal already exists via
   `args.remove_losers` (PLAY-12). Regression:
   `tests/test_play29_retreat_gates.py`, `tests/test_round_61_sally_retreat.py`.
5. ~~**4.3.4 Avoid destination gates + palette mismatch.**~~ RESOLVED
   2026-07-06 as PLAY-30. The Avoid handler and enumerator now share
   `_legal_retreat_dests` (4.3.4 Avoid == 4.4.3 Retreat gate): block only
   UNBESIEGED enemy Lords/Strongholds, no enemy-Conquered clause, exclude
   only the enemy's Approach Way (a PARALLEL Way of another type back to
   from_locale is offered). Enumerator emits per-(dest, way_type) so every
   option round-trips through the handler. Regression:
   `tests/test_play30_avoid_gates.py`.
6. ~~**4.8.1 Feed sharing.**~~ RESOLVED 2026-07-06 as PLAY-31. Feed is
   now TWO passes: (1) every Moved/Fought Lord Feeds his own Forces from
   his own mat, then (2) only SURPLUS is shared to co-located same-side
   Lords who expended all their own -- so no Lord is raided of Assets he
   needs, and the correct Lord goes Unfed. `args.feed_loot_first`
   (bool/list) chooses Provender-vs-Loot spend order (default
   Provender-first); `args.feed_donor_order` prioritises donors;
   `args.hillforts_skip` chooses the T8 skip-Lord among the eligible
   (validated). Regression: `tests/test_play31_feed_sharing.py`.
7. ~~**4.8.2 Pay window.**~~ RESOLVED 2026-07-10 as PLAY-32. The
   per-card Pay window now opens after EVERY Command card whenever the
   side has a payable resource (Coin, Loot at a Friendly Locale, or
   Russian Veche Coin) -- 4.8.2 "any Teutonic then Russian Lords may
   receive Pay as per Levy (3.2)"; the old pending-Disband-only gate
   was a harness artifact of the BUG-4/R203 fix. Protocol unchanged:
   first `fpd_resolve` Feeds and pauses (`pay_window: true`), the side
   Pays via `pay_with_coin`/`pay_with_loot` as desired, a second
   `fpd_resolve` runs the Disband check. Pay is optional ("may"):
   `args.decline_pay` completes Feed -> Disband in one call (used by
   the scripted drivers). Regression:
   `tests/test_play32_pay_window_every_card.py`.
8. Choice/palette cluster:
   - ~~**4.4.2 Reposition Advance slot choice**~~ RESOLVED 2026-07-10 as
     PLAY-33. 4.4.2: Reserves slide "into ANY empty Front positions".
     When open Front slots outnumber the Reserves, each advancing
     Reserve Lord's slot is now an owner choice -- new
     `reserve_advance_slot` battle decision (options = currently open
     slots), asked after the which-Lord decision. Protocol unchanged
     when Reserves >= open slots (per-slot which-Lord already reaches
     every pairing); the leftmost fallback preserves prior
     deterministic behavior. Regression:
     `tests/test_play33_reposition_slot_choice.py`.
   - ~~**4.0 excess side-capability discard**~~ RESOLVED 2026-07-10 as
     PLAY-34. 4.0: players "must SELECT and discard" excess side
     Capabilities. `advance_step` (on the call completing Call to
     Arms) accepts `args.rule_4_0_discards = {side: [card_id, ...]}`;
     named cards are validated and discarded first (with SMOKE-031
     cascade cleanup), any remaining excess tail-drops as before.
     Regression: `tests/test_play34_rule_4_0_discard_choice.py`.
   - ~~**Spoils distribution**~~ RESOLVED 2026-07-10 as PLAY-35. New
     `distribute_spoils` helper spreads every Spoils path (Battle
     Aftermath via `transfer_spoils`, Avoid discards, Storm Sack
     transfers, Storm Stronghold award, Novgorod Veche Coin) across
     ALL winner Lords: explicit `args.spoils_allocation = {lord:
     {asset: n}}` first, then spill-fill in priority order
     (`args.spoils_recipient` now also takes a list); assets vanish
     only when every winner mat is at the 1.7.3 cap. Regression:
     `tests/test_play35_spoils_distribution.py`.
   - ~~**Avoid Provender cap**~~ RESOLVED 2026-07-10 as PLAY-36.
     4.3.4: Avoiders take "Provender equal to their own OR SHARED
     Transport". The Lords Avoiding together in one call now pool
     their usable Transport (1.5.2 Sharing): own covers own first,
     spare group capacity covers co-avoiders' excess (markers stay on
     owners' mats), only Provender beyond the GROUP total is
     discarded. `args.avoid_keep_order` (list of avoider ids) directs
     who benefits from spare capacity first. A staying Lord's
     Transport does NOT count (it isn't moving across the Way).
     Regression: `tests/test_play36_avoid_shared_transport.py`.
   - **Veche-A / Legate-2b Calendar-edge** slides clamp at box 1 /
     reject off-right instead of 2.2.3 off-edge placement (incl. a
     VP-burning no-op Veche A offered at box 1).
9. **Battle-hold palette surfacing.** Tier-2 holds are reachable only
   via stand_battle args; the palette never names them (parity note,
   not a rules divergence).

### Questions logged for the user
- Q-010 — RESOLVED 2026-07-06 (D-Q010): rules-literal. Storm (4.5.2) and
  Sally (4.5.3) cost one Command action; D-R203's pristine gate narrowed
  to Siege/Sail/Tax (+ Stone Kremlin / Stonemasons).
- Q-011 — RESOLVED 2026-07-06 (D-Q011): the resolve_battle max_rounds=10
  cap is lifted (default None -> far safety bound + no-progress guard).
