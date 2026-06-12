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

Items noted but NOT changed (need design input):
- R10 Steppe Warriors implements as a side-wide Capability at first
  Levy even when neither Aleksandr nor Andrey is Mustered (eligibility
  "Aleksandr, Andrey"); this_lord cards auto-discard in the same spot.
- `pay_with_coin` candidates list non-collocated targets (handler
  correctly rejects with `pay_target_not_collocated`).
- Group-march variants are never enumerated in `legal_actions()`
  (handler accepts `args.group`); an agent following the "palette only"
  rule in LLM_PLAY_GUIDE.md can never group-march.
- 4.9.4 Wastage auto-picks which Asset to discard rather than offering
  the owner the choice.
