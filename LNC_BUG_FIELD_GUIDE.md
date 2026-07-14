# A Field Guide to Rules-Engine Bugs

**Lessons from building the Nevsky harness, for other Levy & Campaign
engine projects.**

This guide catalogs the bugs actually found while building a
rules-faithful engine for *Nevsky* (GMT, Levy & Campaign Vol. I, 2nd
Edition) with an LLM-driven development and audit loop. The project
logged roughly **190 distinct findings** across development: ~144
SMOKE-tagged findings from scripted playthrough rounds, 41 PLAY-tagged
divergences from adversarial rules-vs-code audits and golden-test
validation, 4 BUG-tagged findings from LLM playthroughs, and a handful
of AUDIT/Q items resolved by owner adjudication. Every fix shipped with
a rule citation, a dedicated regression test, and a green run of the
full verification stack (~1,580 tests, a 9,300-probe palette-parity
sweep, and 120 invariant-checked fuzz games per change).

The point of this document: **the same bugs will appear in an engine
for Almoravid, Inferno, Plantagenet, or Henry**, because they are not
Nevsky bugs — they are the failure modes of translating a Levy &
Campaign rulebook into code. Each section names the class, shows real
examples, and says which detection technique actually caught it.

---

## 1. The one-sentence summary

Internal consistency checks (fuzzing, invariants, self-play) find
crashes and state corruption; they **cannot** find a rule implemented
plausibly-but-wrongly, because the engine is self-consistently wrong.
The classes below are ordered roughly by how often each escaped the
internal checks and had to be caught by reading the rulebook again,
by palette-parity sweeping, or by replaying the designer's own
published example.

---

## 2. The bug taxonomy

### 2.1 Dropped qualifiers

The rulebook qualifies a noun; the code tests the bare noun.

- 4.4.3 Retreat blocks Locales with **Unbesieged** enemy Lords or
  Strongholds. The code blocked *any* enemy Lord or Stronghold — so a
  Lord besieging an enemy castle wrongly blocked his own side's
  Retreat there, escalating survivable defeats into removals (PLAY-29,
  and the same dropped word in Avoid Battle, PLAY-30).
- 4.3.4 Avoid caps Provender at "their own **or shared** Transport."
  The code counted own Transport only, so a co-Avoiding ally's empty
  carts couldn't carry the grain and it went to the enemy as Spoils
  (PLAY-36).

*Why it happens:* the qualifier lives in a subordinate clause and the
first implementation pass is keyed on the sentence's subject.

*How to catch:* diff the code's predicate against the printed sentence
word by word, once per gate, in a dedicated audit pass. Every
adjective in a Levy & Campaign rule is load-bearing.

### 2.2 Silently narrowed scope

The rule grants something broadly; the engine grants it in the one
situation the developer was thinking about.

- 4.8.2 grants Pay after **every** Command card. The engine opened the
  Pay window only when a Disband was pending — the case that motivated
  writing the window in the first place (PLAY-32).
- 4.3.4 lets "some or all" defenders Avoid "to one or more adjacent
  Locales." The engine supported all-defenders-to-one-Locale only
  (PLAY-26; same pattern in Withdraw).
- Spoils: "the winning player **distributes** these Assets among mats
  of Lords at the Locale" / "distribute **as desired**." The engine
  handed everything to `winners[0]` and let anything over that one
  mat's cap evaporate while allies had room (PLAY-35).

*Why it happens:* the implementing session generalizes from the
triggering playtest incident, not from the rule text.

*How to catch:* grep the rulebook for "each", "every", "any", "some or
all", "one or more", "as desired" and confirm the code's cardinality
matches. These words are the spec.

### 2.3 The engine decides what the player should

Levy & Campaign rules are full of owner choices. An engine under
schedule pressure hardcodes a "reasonable" default and the choice
disappears — the game still *runs*, so nothing flags it.

Real examples: which excess Capability to discard at 4.0 (engine: list
tail — PLAY-34); which Front slot an advancing Reserve Lord takes
(engine: leftmost — PLAY-33); whether a Flanking Lord absorbs Hits for
the Lord he flanks (engine: never — PLAY-28); how Spoils split
(PLAY-35); which Lord's Provender rides shared Transport (PLAY-36);
Wastage discards (PLAY-6); Loot-vs-Provender Feed order and donor
order in Feed sharing (PLAY-31); declining the 4.5.1 Surrender roll
(PLAY-7); Battle casualty-assignment policy (R198).

*Why it happens:* a default is needed to make the state machine
advance, and defaults fossilize.

*How to catch:* audit for the words "may", "select", "choose",
"desired", "player's discretion" and check each has an args channel or
decision hook. Convention that worked well: every added choice keeps
the old deterministic behavior as the no-args fallback, so no existing
test or driver breaks, and each choice is validated fail-loud.

### 2.4 Palette/handler drift (parity bugs)

Any engine that both *enumerates* legal moves and *executes* them has
two implementations of the same rule, and they drift in both
directions:

- Legal but never offered: the R18 Stone Kremlin command existed in
  the handler but was never enumerated, so a palette-driven agent
  could never discover it (BUG-1); Tier-2 Battle Holds were reachable
  only by callers who already knew the args schema (PLAY-38).
- Offered but rejected: the enumerator emitted `concede: <side>` while
  the handler demanded `concede: <battle role>` (SMOKE-119); Veche
  Option A was offered for off-Calendar cylinders the handler refused
  (SMOKE-156).
- Offered and silently dropped: a templated move expansion returned
  empty instead of erroring, so Sail/Supply quietly vanished from an
  LLM's option list (BUG-3).

*How to catch:* two things carried most of the weight. First, an
automated **round-trip sweep**: at every step of scripted games, apply
every enumerated move to a state copy and fail on any rejection; run
it after every enumerator or handler change. Second, **share the gate
functions** — when Avoid and Retreat were rewritten to call one
`_legal_retreat_dests`, an entire family of drift became impossible.

### 2.5 Over-acceptance (the sweep's blind spot)

The round-trip sweep proves everything offered is legal. It proves
nothing about what else the handler accepts. These hide longest:

- A March `group` that omitted the active Lord moved the *other* Lords
  while he stayed behind — an "order others to march without me" no
  rule allows (PLAY-39, found only by the golden test).
- Defending-only Hold cards (Marsh, Hill) were consumable on the
  attack (SMOKE-080); season-restricted Holds were consumable out of
  season — destroying the card *and* applying the effect (SMOKE-079),
  or destroying it while a separate check nulled the effect, an
  illegal play that silently burned the card (PLAY-16).

*How to catch:* adversarial handler audits asking "what garbage does
this accept?", and validating args fail-loud instead of coercing.

### 2.6 Harness artifacts that become invisible rules

Engineering conveniences read like rules once the original author is
gone: a 10-Round Battle cap that no printed rule contains (Q-011); the
Pay window's pending-Disband gate (PLAY-32); the leftmost-slot
Reposition default (PLAY-33).

*How to catch:* mark every simplification as an artifact in the code
comment at birth, and log it in a known-items file. The Nevsky
backlog's "Known open items" list, kept ruthlessly current, was how
these got scheduled for removal instead of being rediscovered.

### 2.7 Missing legal options

The engine handles the common path and a legal alternative simply has
no expression:

- No way to discard Provender down to usable Transport and March
  *Unladen* at single-action cost, though 1.7.2 names "March Unladen"
  explicitly and the Playbook walks through the decision (PLAY-40).
- The parallel-Way Avoid (a second Way of a different type between the
  same two Locales) was dropped by a set-keyed enumerator (PLAY-30).
- Winners never rolled 4.4.4 Losses at all — losses were assumed to be
  a loser's problem (fixed in the PLAY-7..25 audit wave).

*How to catch:* golden tests from published examples (see §3.4), and
audits that walk the rule section asking "can the engine express every
sentence?" rather than "is what it does legal?"

### 2.8 State lifecycle leaks and partial mutations

Classic software bugs, but with rules-flavored consequences:

- `in_stronghold` survived a March to a new Locale, so the Battle
  Array treated a field army as garrisoned (SMOKE-036).
- A failed event resolver had already popped the card — an exception
  destroyed it (SMOKE-010: mutate only after success).
- This-Levy events leaked into the next Levy when an agent skipped the
  optional discard action (SMOKE-039: fire mandatory cleanup on the
  phase transition, never trust the caller).
- Departing besiegers left immortal Siege markers via three different
  exit paths — each path fixed separately over weeks (PLAY-3, then the
  battle-retreat path much later). Centralize the cleanup helper and
  call it from *every* exit.

### 2.9 Missing cross-system cascades

One rules object touches another and the link is only in the flavor
text of a card or a reference sheet:

- Discarding the Crusade capability must Disband Summer Crusaders;
  Steppe Warriors likewise for Mongols; William of Modena's discard
  removes the Legate pawn (SMOKE-031's cascade family).
- An Unfed Service shift must drag Vassal Service markers with it
  under the advanced rule (SMOKE-144).
- A Teutonic Lord Avoiding/Withdrawing/Retreating with the Legate
  removes the pawn — wired for two of the three triggers, missing for
  the third (SMOKE-043 then SMOKE-084).

*How to catch:* route every discard/removal through one helper that
owns the cascades, and audit the Arts of War reference sheet
separately from the rulebook — the cascades mostly live there.

### 2.10 Bad quotes and edition drift

Two document-hygiene classes that caused real bugs:

- **Misquoted rules in comments become load-bearing.** A transcribed
  "4.4.4" quote in a code comment said the winner restores all Routed
  units; the printed rule says "both sides" roll. Later work built on
  the comment (SMOKE-093/098/099 lineage, unwound by PLAY-11). Rule:
  re-extract text from the PDF for every audit; never trust a quote
  that lives in a comment.
- **Know which edition each source describes.** The Background Book's
  examples are 1st Edition; the engine is 2E. The 2E scenario setups,
  Ravage costs, and Veche slide distances all differ. Declare a trump
  order up front (here: 2E Rules of Play > everything) and annotate
  every deviation when validating against older material.

Related: calendar-edge behavior (2.2.3's "just off the board" for
shifts past box 1/16) was clamped or rejected in two different
subsystems (PLAY-37). Track-edge rules are easy to shortcut and every
L&C game has them.

---

## 3. What actually caught what

Ranked by yield, with the honest caveat that each layer was blind to
the classes above it left for the others.

**3.1 Scripted playthrough rounds (the SMOKE series, ~144 findings).**
Step a scenario through the action API move by move, eyeball every
state transition, log each anomaly with a serial number, fix, add a
regression test. Tedious, and by far the highest total yield — most lifecycle,
cascade, and math bugs fell here.

**3.2 Adversarial rules-vs-code audits (the PLAY series).** Re-extract
the rulebook text, pick a subsystem, and compare sentence-by-sentence
against the code — assuming the code is wrong until proven right.
All the dropped-qualifier and narrowed-scope bugs fell here. Parallel
audits over disjoint subsystems worked well.

**3.3 Palette-parity sweeping + invariant fuzzing (continuous).** The
round-trip sweep (§2.4) and a fuzzer asserting ~12 global invariants
(piece conservation, VP accounting, phase legality) over seeded
random-policy games. Low individual yield after the early rounds, but
they are the *ratchet*: run green after every single change, they
guarantee fixed bugs stay fixed and new choices don't break parity.

**3.4 Golden tests from the designer's published example (3 findings
in one afternoon, at the very end).** Replay the Playbook's worked
example with every printed die roll scripted, asserting every printed
intermediate number. This is the **only external check** in the whole
stack, and on first contact it found three bugs that ~1,580 tests and
hundreds of fuzz games had sailed past (PLAY-39/40/41) — including a
plain arithmetic error in a card bonus (+1 per unit, not +1 flat) that
no internal check could ever notice because the engine agreed with
itself perfectly. **Do this early, not late.** If your volume's
playbook has a worked example, it is the cheapest high-grade test
oracle you will ever get. Requirements: a seedable RNG you can replace
with a scripted FIFO of the printed rolls, and scripted decision
hooks.

**3.5 LLM self-play with a palette-driven agent (BUG series).** An
agent that only sees enumerated moves finds enumeration gaps fast
(BUG-1..4), because unlike a human tester it cannot compensate with
rules knowledge the palette didn't offer.

**3.6 The owner adjudication loop (Q/D series).** Genuine rules
ambiguities go to the human as numbered questions with options and a
recommendation; answers get logged as numbered decisions citing the
rule, and the decision ID goes into every commit and comment that
depends on it. This is what keeps "we decided X in May" from being
relitigated in July — and what lets a *successor session or model*
audit prior work quickly, which happened here across model
generations without loss.

---

## 4. Process rules that paid for themselves

1. **One finding, one commit, one regression test.** Tag findings with
   a serial ID; cite the printed rule and the verification counts in
   the commit message.
2. **Deterministic, seedable, scriptable RNG** with a state counter.
   Reproducibility is table stakes; scriptability is what makes golden
   tests possible.
3. **New player choices default to the old deterministic behavior.**
   Fallbacks preserve every existing test and driver; scripted
   args/decisions express the choice. Validate fail-loud.
4. **Shared gate helpers between enumerator and handler.** Parity by
   construction beats parity by testing.
5. **Keep four living documents**: an actions/API reference, a
   playtest/known-items log (with struck-through resolutions), a rules
   decision log, and an open-questions file. The known-items list is
   the difference between "artifact we know about" and "rule nobody
   remembers inventing."
6. **Re-extract the rulebook PDF before every audit.** Comments lie;
   the PDF doesn't.
7. **Run the full ratchet on every change** — suite, parity sweep,
   fuzz — even for "obviously safe" one-liners. Several of the fixes
   above were regressions of earlier fixes' blind spots.

---

## 5. Starter checklist for a new L&C engine

Before writing code: pick the edition of record and the trump order
for conflicting sources; build the seeded/scriptable RNG first; set up
the four living documents.

While implementing each rules section: word-by-word predicate check
against the printed text (§2.1-2.2); an args/decision channel for
every "may/select/as desired" (§2.3); shared gates for any rule
enforced in two places (§2.4); fail-loud validation for every
handler arg (§2.5); artifact-tag every simplification (§2.6); route
removals/discards through cascade-owning helpers (§2.9).

As soon as a Battle resolves end-to-end: **encode the playbook's
worked example as a golden test.** It will find things. It found
things here after three audit waves, ~190 logged-and-fixed findings,
and a clean 1,580-test suite.

---

*Nevsky harness, v0.36.0, July 2026. Finding series referenced:
SMOKE-001..156 (scripted playthrough rounds), PLAY-1..41 (playtests,
adversarial audits, golden tests), BUG-1..4 (LLM playthrough R203),
AUDIT (early fix wave), Q-/D- (owner adjudications, RULES_DECISIONS.md).
All regression tests live in `tests/`; the verification stack is
`pytest` + `scripts/roundtrip_sweep.py` + `scripts/fuzz_invariants.py`.*
