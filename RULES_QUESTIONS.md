# Open Questions

Format per BRIEF: ID, Context, Consultation log (5 steps), What is
ambiguous, Options, Affects, Blocking?

When resolved, MOVE the entry to RULES_DECISIONS.md with the user's
adjudication, citation, and commit hash.

---

## Q-007 — Russian Archery special rounding (4.4.2)

**Context.**
Per `reference/Nevsky_Forces_Reference.txt`:

> When Russian -2-Armor Crossbowmen archery (Garrison Men-at-Arms during
> Storm, or a Lord's Men-at-Arms with Streltsy R3) combines with other
> Russian archery, round up any 1/2 Hit that causes the Armor reduction.
> (Rules 4.4.2 Russian Archery)

The current `resolve_battle` / `resolve_storm` rounding model sums all
contributing strikers' raw hits per target per step, then applies a
single `_round_up` at end of step. `striker_has_armor_minus_2` is
recorded as a per-target boolean: True if ANY contributing striker had
the -2-Armor flag.

**What is ambiguous.**
The Forces Reference rule asks for a *specific* round-up of the half-
Hit that causes the Armor reduction. With the current implementation,
when Russian Streltsy MaA (1 unit -> 0.5 -2-Armor archery) combines
with Asiatic Horse (e.g., 2 units -> 1.0 archery), the per-target raw
is 1.5 -> ceil 2. Both incoming Hits flag -2-Armor. That may be more
generous than the rule intends, OR it may be exactly correct depending
on whether "the half-Hit" refers to the rounded total's contribution
or to the literal 0.5 Hit from the -2-Armor source.

**Consultation log.**
1. *Curated reference (Forces).* Quoted above.
2. *Rules of Play 2E section 4.4.2.* "Russian Archery" — confirms the
   rule but the explanatory text mirrors the Forces Reference; doesn't
   resolve the rounding-granularity question.
3. *Rules of Play 2E key terms.* "Hit", "Round Up", "Armor" entries do
   not address the special rounding case.
4. *Playbook examples.* No worked examples of mixed Russian archery
   that I can locate.
5. *Second Edition Changes.* No erratum on this point.

No external/historical sources consulted.

**Options.**

a. *Current behavior.* Apply -2-Armor to all Hits in the step if any
   Russian striker had the -2-Armor flag. This is mechanically
   simple but potentially over-applies.
b. *Per-Hit attribution.* Track which Hit came from which striker;
   apply -2-Armor only to the first ceiling(-2-Armor raw) Hits per
   target. Requires a more granular per-Hit accounting in
   resolve_battle/resolve_storm.
c. *Rounded-up-to-1 sub-step.* Resolve the -2-Armor archery as its own
   sub-step (1 Hit minimum if any -2-Armor source is present), then
   resolve regular archery separately. Closer to the rule's "round
   up the half-Hit that causes the Armor reduction" phrasing.

**Affects.**
- `src/nevsky/battle.py::_resolve_hits` and `_absorb_hit` (Armor roll
  thresholds).
- `src/nevsky/battle.py` archery step assignment (around line 1180 for
  Battle, line 1716 for Storm).

**Blocking?**
No. The current behavior is conservative-toward-Russian (over-applies
-2-Armor in mixed cases), and the smoke driver shows Russians winning
balanced 1v1 Battles 84% already. Tightening this would mildly weaken
Russian archery — unlikely to flip scenario outcomes.


## Q-008 — Bridge / Marsh / Hill / Ambush battle effects (4.4.2 Tier 2 events)

**Context.**
Tier 2 Battle Hold events (T4/R1 Bridge, T5/R2 Marsh, T6/R6 Ambush,
T9/R5 Hill, T10 Field Organ, R4 Raven's Rock) are partially wired:
`_consume_battle_holds` validates and discards them per
`battle.py::resolve_battle`'s `holds` arg. But the actual Battle-side
mechanical effects are mostly NO-OPs.

Specifically the Bridge effect ("opposing front center Lord Melee
Strikes with units up to twice Round number") was previously documented
as "no-op since front-center is not modeled". Q-005 (Battle Array
three-front-positions) modeled front-center; the Bridge cap rule is
now implementable but not wired.

**What is ambiguous.**
Whether Tier 2 Battle Holds beyond Marsh (Horse blocked rounds 1-2)
and Raven's Rock (Russian Walls 1-2 vs Melee R1) should be implemented
strictly per their card text:

- Bridge: cap front-center Lord's Melee at `2 * round_number` units.
- Hill: defender Archery x1 rounds 1-2 (only one Lord's Archery? or
  side-wide x1 multiplier?).
- Ambush: Round 1 ignore enemy left/right Lords' strikes.
- Field Organ: requires args.field_organ_lord; effect is...?

The card-text wording for each is ambiguous in the abstract; need
adjudication on the implementation interpretation.

**Consultation log.**
1. *Reference (Arts of War).* Card text for each (T4-T10, R1-R6).
2. *Rules of Play 2E section 4.4.2 Tier 2 events.* Lists the events
   but defers to card text.
3. *Rules of Play 2E key terms.* "Hold" event entry: "Discard the
   moment used."
4. *Playbook examples.* No worked Tier 2 Battle Hold play examples
   I can locate.
5. *Second Edition Changes.* No erratum.

No external sources consulted.

**Options.**

a. *Wire each per a literal reading of the card text.* Risk:
   misinterpretation; rebalances Battle outcomes.
b. *Leave as no-ops (current state).* Fine as long as the user/LLM
   knows these Holds don't do anything when consumed. The harness
   tracks consumption correctly; only the battle-side modifier is
   missing.
c. *Wire per Volko Ruhnke's worked examples.* Would need to find them
   — they're in InsideGMT articles or BGG forum posts (excluded by
   BRIEF policy).

**Affects.**
- `src/nevsky/battle.py::resolve_battle` per-step Strike-cap and
  per-Round Hit modification logic.
- `src/nevsky/events.py::_consume_battle_holds` documentation.

**Blocking?**
No. Players currently can play Tier 2 Battle Holds; they just don't
mechanically affect the Battle. The harness flags this so user/LLM
applies the effect manually in interpretation.

