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
