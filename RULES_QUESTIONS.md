# Open Questions

Format per BRIEF: ID, Context, Consultation log (5 steps), What is
ambiguous, Options, Affects, Blocking?

When resolved, MOVE the entry to RULES_DECISIONS.md with the user's
adjudication, citation, and commit hash.

## Q-010 — Storm action cost: D-R203 "entire card" vs 4.5.2 "a Command action"

**Context.** D-R203 (adjudicated 2026-05-20) requires a pristine full
Command card for all five `entire_card` Commands: Siege, Storm, Sally,
Tax, Sail. That adjudication was grounded in Commands.txt's
`action_cost: entire_card` tags plus the printed rulebook's 4.2 clause.
During the 2026-07-05 audit pass the rulebook text was re-extracted:
4.2.1 lists only "Siege, Sail, and Tax take an entire card's actions
(4.5.1, 4.7.3, 4.7.4)" — Storm is NOT in that list, and 4.5.2 reads
"Any Lord outside a Besieged Stronghold may use A COMMAND ACTION to
launch an Attack" (emphasis added). 4.5.3 Sally likewise says "may use
a Command to Attack Besiegers".

**Consultation.** (1) reference/Nevsky_Commands.txt tags storm
`entire_card`; (2) its own header says the Rules of Play govern on
conflict; (3) rulebook 4.2.1 names only Siege/Sail/Tax; (4) 4.5.2 says
"a Command action"; (5) 2E changes file silent on this point.

**What is ambiguous.** Whether Storm (and Sally) genuinely require a
pristine card, or cost one action each — e.g. March-to-join-a-Siege
(1 action) then Storm (2nd action) would be legal by the 4.5.2 text,
with 4.4.5 Recovery then ending the card anyway.

**Options.** (a) Keep D-R203 as-is (house-rule-adjacent, consistent
cost model); (b) narrow D-R203 to Siege/Sail/Tax and make Storm/Sally
cost one action (rulebook-literal).

**Affects.** `_require_full_command_card` call sites in _h_cmd_storm /
_h_cmd_sally; the pristine gate in the Siege/Storm/Sally enumeration.

**Blocking?** No — D-R203 stands until re-adjudicated (decisions are
permanent; this would be a new decision superseding its scope).

## Q-011 — resolve_battle max_rounds=10 stalemate awarded to defender

**Context.** `battle.py::resolve_battle` caps Battles at 10 Rounds and
awards a no-Concede stalemate to the defender. No such rule exists —
4.4.2 Battles continue "Round after Round, until a side Concedes or all
its Lords Rout." With Hits auto-generated (no dice) a Battle between
forces that can still Strike always progresses, but degenerate arrays
(e.g. both sides all-Ships/zero-strike units) could loop forever
without the cap.

**What is ambiguous.** Whether a harness artifact cap is acceptable
(and if so, who should win / whether it should instead force a Concede
decision), or whether the engine should prove termination and drop the
cap.

**Options.** (a) keep cap as defensive artifact, document it; (b) raise
the cap and log a warning; (c) treat cap-hit as attacker Concede (they
failed to take the field); (d) prove termination impossible without
strike-capable units and auto-drain.

**Affects.** resolve_battle/resolve_storm terminal conditions.

**Blocking?** No.

