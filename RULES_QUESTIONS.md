# Open Questions

Format per BRIEF: ID, Context, Consultation log (5 steps), What is
ambiguous, Options, Affects, Blocking?

When resolved, MOVE the entry to RULES_DECISIONS.md with the user's
adjudication, citation, and commit hash.

---

## Q-002 — Hermann / Rudolf / Yaroslav Transport-(any) slot status

**Context.**
`src/nevsky/data/static/lords.json` currently encodes a 1-slot
Transport-(any) entry for `hermann`, `rudolf`, and `yaroslav`. The
Q-001 user-supplied spec table (in RULES_DECISIONS.md) does NOT
include these three Lords in any per-scenario default rows AND
explicitly states the (any) slot inventory: "Andreas, Vladislav,
Andrey, Domash, Gavrilo, Karelians, Aleksandr."

This implies `lords.json` is wrong for hermann/rudolf/yaroslav —
either their starting Transport should be a fixed type (e.g., Cart
for the trackway-heavy mats) or they should have no Transport at
all.

**Consultation log.**

1. *Curated reference.* `reference/Nevsky_Lords.txt` is the canonical
   source for each Lord's mat. Need to read it to confirm whether
   hermann/rudolf/yaroslav have (any) slots or fixed Transport.
   (Not re-read for this question; the project's own data is the
   evidence trail.)
2. *Rules of Play.* Not consulted (PDF restriction).
3. *Cross-references.* Q-001 user spec section "Affected files" calls
   out the (any) slot inventory by name; this list excludes
   hermann/rudolf/yaroslav.
4. *Playbook.* Not consulted (PDF restriction).
5. *Second Edition Changes.* Not relevant.

No external/historical sources consulted.

**What is ambiguous.**
Whether `lords.json` should retain the (any) Transport slot for
hermann/rudolf/yaroslav (and the Q-001 default table needs to be
extended) OR whether the slot should be removed (Q-001 spec is
correct as written).

**Options.**

a. *Remove (any) slots from lords.json.* Fix the static data to match
   the Q-001 inventory. Drawback: requires confirming Nevsky_Lords.txt.

b. *Add Hermann/Rudolf/Yaroslav rows to the Q-001 default table.*
   Apply the heuristic: trackway-dominated start locales -> Cart for
   non-Winter, Sled for Winter. Watland (Late Winter start) already
   has Andreas+Sled for Fellin, so by analogy Hermann at Dorpat in
   Watland would be Sled. In Pleskau (Summer), Hermann at Dorpat would
   be Cart per rule 3b.

c. *Default-via-heuristic in code.* Implement the spec's decision tree
   so any (any) slot not in the table gets a heuristic default. More
   work; more flexible.

**Affects.**
- `src/nevsky/data/static/lords.json`
- `src/nevsky/scenarios.py::_Q001_DEFAULTS`
- `tests/test_q_001_setup_transport.py` (parametrized table)

**Blocking?**
No. Current behavior: untabled Lords default to `allowed[0]` = `boat`,
which is potentially wrong for Hermann at Dorpat (no waterway use),
but doesn't break any rules engine. The PendingDecision is emitted
correctly, so the player can override.

