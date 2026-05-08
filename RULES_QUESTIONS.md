# Open Questions

Format per BRIEF: ID, Context, Consultation log (5 steps), What is
ambiguous, Options, Affects, Blocking?

When resolved, MOVE the entry to RULES_DECISIONS.md with the user's
adjudication, citation, and commit hash.

---

## Q-004 — T12 Ordensburgen: which Strongholds are Commanderies? (1.3.1)

**Context.**
The Teutonic Capability T12 Ordensburgen grants Teutonic Lords extra
Seats at every Commandery, plus +1 Command when a Lord starts a
Command card at one. Per Rules of Play 1.3.1, "Commanderies are
Strongholds with the Order symbol on the map." Per the Misc Reference
file: "Strongholds with the Order symbol serve as EXTRA Seats for the
relevant Teutonic Lords while T12 Ordensburgen Capability is in play."
The full list of Commanderies is identified by an Order seat symbol on
the printed map (see Playbook page 5: "small black-cross-on-white Seat
symbols, not to be confused with Teutonic master Andreas's larger,
more ornate symbols at Riga and Wenden").

**Consultation log.**
1. *Rules of Play 2E (page 3, page 36 example).* Wenden is named
   explicitly: "Wenden would be two Seats each for Andreas and Rudolf"
   (Playbook page 36, T12).
2. *Playbook (page 8).* The example play references "the OrdenSBurGen
   Commanderies at Fellin and Adsel or Leal" — confirming Fellin
   (Castle), Adsel (Castle), and Leal (Bishopric) as Commanderies.
3. *Playbook (page 6).* "Heinrich is able to Muster at Fellin (instead
   of Leal) only because that Stronghold counts as a Seat for Heinrich
   via the OrdenSBurGen card" — Fellin confirmed.
4. *Background book (page 35).* "the commanderies of the Teutonic
   Order" but no enumeration.
5. *Reference files / 2E Changes / Map Reference.* No enumeration.
   Map symbols are the source of truth. Without the physical map, the
   set is incomplete: Wesenberg, Odenpah (Castles); Reval, Riga,
   Dorpat (Bishoprics) MAY also bear the Order symbol, but textual
   sources do not confirm them.

**What is ambiguous.**
The complete set of Commanderies. Confirmed by text: Wenden, Fellin,
Adsel, Leal. Possible additional Commanderies (per the rules' "all
Strongholds with the Order symbol"): Wesenberg, Odenpah, Reval,
Dorpat. The current implementation flags only the four confirmed ones.

**Options.**

a. *Use only confirmed (current).* Wenden, Fellin, Adsel, Leal flagged
   `commandery: true`. Others remain false until the map is consulted.
b. *Expand by territory.* Flag every Teutonic-territory Stronghold
   that is a Castle or a Bishopric AND is owned by the Order (not a
   civilian Bishop's seat). Risky without map verification.
c. *Match by primary seat.* Flag every Locale that appears as a
   primary Seat for any Teutonic Order Lord (Andreas, Hermann, Rudolf,
   Heinrich) — but this conflates Coat-of-Arms seats with Order seat
   symbols, which the rules say are different (Playbook page 5).

**Affects.**
- `src/nevsky/data/static/locales.json` (`commandery` flag)
- `src/nevsky/actions.py::_seats_of` (T12 extra-Seat enumeration)
- `src/nevsky/campaign.py::effective_command_rating`
  (Ordensburgen +1 detection)

**Blocking?**
No. Option (a) is conservative and can be expanded once the map's
Order seat symbols are read off. Players using the harness for the
Crusade/Watland scenarios will see the +1 trigger at Wenden, Fellin,
Adsel, Leal exactly. If the canonical map adds more Commanderies, an
edit to locales.json suffices.

---

## Q-005 — Battle Array three-front-positions and Flanking (4.4.1, 4.4.2)

**Context.**
Per Rules of Play 2E (page 14), Battle Array uses three Front
positions per side: left, center, right; with the Active Lord at
Front center, other Lords filling left/right, and any remainder in
Reserve. Defenders match opposite. In each Round after the first,
"Reposition" advances Reserve Lords into empty Front positions and
fills empty center positions from left/right. Strikes occur between
opposite Lords; if a Lord has no opposite, Flanking applies — the
Lord's units Strike the closest enemy Lord in that row, and the
target's owner may direct Hits to either the directly-opposed Lord
or the Flanker.

The current Phase 3b implementation pools all participating Lords on
each side as a single Front and pools their Strike Hits per side per
step (no per-Lord Flanking, no Reposition rules, no per-position
Strike resolution). This is a documented Phase 3b simplification:
"single-front lane (no flanking)" — see `resolve_battle` docstring
in `src/nevsky/battle.py` line ~283.

Per the Round 8 BRIEF amendment (Rules-Accuracy-Trumps-Simplification
clause), this simplification is in violation: it changes combat math
in cases where the Active Lord is much weaker than his Reserve
support, where the Defender has fewer Lords than the Attacker (so
Flanking is automatic), and where Lord Routs mid-round create new
Flanking situations.

**Consultation log.**
1. *Rules of Play 2E (page 14).* Full Array rules; cited verbatim:
   "A side must as able have a Lord each in three Front positions:
   left, center, and right. Other Lords start in Reserve. The Active
   Lord must start at Front center. ... The Defender must put one
   Lord directly opposite each Front Attacking Lord, first in the
   center, then left and/or right, as able."
2. *Rules of Play 2E (page 15).* Reposition specifics: Advance Lords;
   Center fill. Flanking definition: "Whenever a Lord facing an
   enemy row has no enemy Lord directly opposite ... the Lord's units
   Strike the closest enemy Lord in that row".
3. *2E Changes file.* Confirms 2E added the explicit three-front rule
   and Reposition mechanics; pre-2E Array was simpler.
4. *Battle and Storm Reference.* Reflects 2E (already aligned).
5. *Playbook.* Pages 14-19 walk through several Battles using the
   three-position Array.

**What is ambiguous.**
Nothing about the rule itself is ambiguous. The question is *scope of
the harness fix*. A faithful implementation requires:
- Per-Lord Front position state (left / center / right / reserve).
- Per-position Strike Hit accumulation (no side-pool).
- Reposition step at the start of each Round after the first.
- Flanking detection and target-selection (owner picks for Hits).
- Mid-round Routs trigger Flanking re-evaluation.

This is a multi-day refactor of `resolve_battle` and `resolve_storm`
(Storm uses one-Lord Front so it is closer to the rules already, but
Reserve / Reposition still apply — Storm Reposition is "switch Front
and any Reserve Lord", page 17).

**Options.**

a. *Full refactor.* Implement the three-position Array, Reposition,
   and Flanking everywhere `resolve_battle` is called. Update all
   tests. Estimated 1-2 days.
b. *State-only refactor.* Track per-Lord position in CombatPending
   and the resolve_battle log, but keep the per-side pool combat
   math. Documents the divergence but does not fix it. Per
   Rules-Accuracy-Trumps-Simplification, this is insufficient.
c. *Defer.* Document the divergence as a known LIMITATION in BRIEF
   and SMOKE_TEST_FINDINGS. Leave the test suite green. Address in a
   future round dedicated to Battle Array.

**Affects.**
- `src/nevsky/battle.py` (`resolve_battle`, `_assign_hit_owner_pick`)
- `src/nevsky/state.py` (`CombatPending` — per-Lord position)
- `src/nevsky/campaign.py` (`cmd_stand_battle`, Lord-position picker)
- `tests/test_march_and_battle.py`,
  `tests/test_concede_pursuit.py`,
  `tests/test_steppe_warriors_and_holds.py`
- All Battle smoke tests (re-verify outcomes under three-position)

**Blocking?**
No, but high-priority for Round 10. Per the BRIEF
Rules-Accuracy-Trumps-Simplification clause, this is the largest
unresolved divergence in the Battle module. Logging this question
alongside Q-006 (Relief Sally Array, depends on this).

---

## Q-006 — Relief Sally Array (4.4.1, 4.4.2)

**Context.**
Per Rules of Play 2E (page 14), Relief Sally lets Besieged Lords join
an Attack at their Locale with no added Command actions — they Array
"in a row above as above but behind the Defenders". Defender Reserve
Lords instead position opposite Sallying Attackers as a Rearguard
row. If no Rearguard, Sallying Lords Flank Front Defenders all
equally closely. Siegeworks (rolled separately) protect against
Strikes by Sallying Attackers ONLY. If the Attackers lose, Withdraw
Sallying Lords back into the Stronghold and reduce Siege markers
there to one (page 14).

The current Phase 3c `cmd_relief_sally` is a much simpler "combine
Sally with Marching Attack" path. It does not Array Sallying Lords
behind the Defender's Front, does not implement Rearguard, does not
roll Siegeworks separately for Sallying-vs-Front Strikes, and does
not handle the "Withdraw Sallying Lords back into Stronghold" loss
path the same way.

**Consultation log.**
1. *Rules of Play 2E (pages 14, 15).* Relief Sally Array, Adjust Rows
   (Rearguard becomes Reserve / Sallying Lords Flank), Siegeworks
   round-separately.
2. *2E Changes file.* "Battle Array, Relief Sally, and Flanking"
   were clarified in 2E.
3. *Battle and Storm Reference.* Aligned with 2E.
4. *Reference / Sequence of Play.* Aligned.
5. *Playbook.* No specific Relief Sally example in the example play
   sections I have read (pages 5-8).

**What is ambiguous.**
Nothing rules-wise. Like Q-005, this is a scope question. Q-006
depends on Q-005: Relief Sally Array uses the same three-position
Front concept plus a fourth row (Sallying behind Defenders / Reserve
Defenders forming Rearguard). Implementing Q-006 without Q-005 is
not coherent.

**Options.**

a. *Implement after Q-005.* Once the three-position Battle Array is
   in place, add Rearguard / Sallying-row, Siegeworks-vs-Sallying,
   and the Withdraw-into-Stronghold loss path.
b. *Defer.* Same as Q-005 option (c).

**Affects.**
- Same as Q-005, plus `src/nevsky/campaign.py::cmd_relief_sally`,
  `src/nevsky/battle.py` Storm-with-Sally side, and tests covering
  Sally / Relief Sally outcomes.

**Blocking?**
No, but tied to Q-005. Should be addressed together.
