# Active-Play Smoke Test Findings — 2026-05-08

Scenario: drove Pleskau through real moves (March, Approach, Battle,
attempted Storm, FPD, end-of-card transitions). Found bugs that the
unit tests missed because the unit tests didn't compose phases the way
real play does.

Findings are tagged SMOKE-NNN for traceability.

## Fixed in this PR

### SMOKE-001 — FPD processes removed Lords with stale `moved_fought` (HIGH)

**Reproduction.** In `tests/_playthrough_forced_combat.py`, Hermann
(Teutonic) marches izborsk → pskov, triggering Approach with Gavrilo.
Gavrilo wins the Battle; Hermann's forces all Rout, so Hermann is
permanently removed (1.5.1) by the Battle Aftermath.

But Hermann's `moved_fought` flag was set to True BEFORE the permanent
removal (during the cmd_march and again at battle aftermath). The
subsequent `fpd_resolve` step iterated all Lords with
`side == "teutonic" and moved_fought == True` — which included
removed-Hermann. The FPD code then tried to Feed Hermann (units=0,
cost=1, consumed=1 from non-existent provender), recorded `unfed=true`,
and applied the unfed-penalty Service shift on a Service marker that
was already removed by `_remove_lord_permanently`.

**Fix.** `_h_fpd_resolve` now skips Lords with `state != "mustered"`
and clears their stale `moved_fought` flag. Regression test in
`tests/test_smoke_findings.py::test_smoke_fpd_skips_removed_lord_with_stale_moved_fought`.

**Files touched.** `src/nevsky/campaign.py::_h_fpd_resolve`,
`tests/test_smoke_findings.py`.

## Logged for later (not fixed in this PR)

### SMOKE-002 — `lords.json` lists Hermann/Rudolf/Yaroslav with `(any)` Transport slots; Q-001 spec table doesn't (MEDIUM)

**Reproduction.**
```
$ PYTHONPATH=src python3 -c "from nevsky.static_data import load_lords; \
  print({lid: data.get('starting_transport_choice') for lid, data in load_lords().items() \
         if data.get('starting_transport_choice')})"
```
Output includes `hermann`, `rudolf`, `yaroslav` with 1-slot `(any)`
entries.

**But** the Q-001 user-supplied spec table in RULES_DECISIONS.md only
covers `andreas`, `aleksandr`, `andrey`, `domash`, `gavrilo`,
`karelians`, `vladislav`. The spec also explicitly states:

> Nevsky_Lords.txt — (any) slot inventory: Andreas, Vladislav, Andrey,
> Domash, Gavrilo, Karelians, Aleksandr.

So `hermann`, `rudolf`, `yaroslav` should NOT have `(any)` slots in
`lords.json`. Either:
1. The static data is wrong: those Lords have fixed Transport, not
   `(any)`. Fix `lords.json` and remove the entries.
2. The Q-001 spec table is incomplete: those Lords DO have `(any)`
   slots and need entries.

The current loader silently falls back to `allowed[0]` for any Lord
not in the table; today that's `boat`, regardless of geography. For
Pleskau, this gives Hermann a Boat at Dorpat (no waterway use case
on his immediate trackways into Rus).

**Recommendation.** Cross-check `Nevsky_Lords.txt` to determine the
canonical state. Most likely: remove the `(any)` slots from
`lords.json` for these three Lords, since the user's spec was explicit.

**Status.** Not fixed in this PR (changing `lords.json` rebases the
default tests). Logged here for the user to adjudicate.

### SMOKE-003 — Spoils transfer doesn't preserve a "transferred to" recipient identity for the agent (LOW)

**Observation.** In `transfer_spoils`, the receiving Lord is hard-coded
to `to_lords[0]`. The rules (4.4.5) say "Any one Teutonic Lord present
receives the Coin, regardless of who is active or originally Levied
the card" — i.e., the player should choose. Phase 3b's deterministic
"first winner Lord" choice is fine for the harness's automated
resolution, but an LLM agent has no hook to override.

**Recommendation.** Future enhancement: accept an optional
`spoils_recipient` arg on `stand_battle` to route the spoils.

**Status.** Not fixed; not blocking active play.

### SMOKE-004 — Battle initiative log records Strikes that contributed 0 hits (LOW / cosmetic)

**Observation.** In a Battle with no Asiatic Horse, the
`archery_defender` and `archery_attacker` steps have `raw_hits: 0.0,
hits: 0` and `distribution: []`. The log is correct but verbose.

**Recommendation.** Optionally collapse zero-hit steps in the log.

**Status.** Not fixed; cosmetic.

### SMOKE-005 — `_playthrough_*.py` scripts assume the Activation loop alternates per call (LOW / docs)

**Observation.** The smoke-test driver expected
`command_reveal` to alternate sides automatically after a single
March. In reality, the active Lord can take more actions (until card
ends via Battle/Siege/Storm/Sail/Tax/Pass or actions exhausted). The
driver had to be rewritten to call `cmd_pass` to end the card.

**Recommendation.** Document the activation loop more visibly in
ACTIONS.md.

**Status.** Not a bug; clarification opportunity.

## Coverage observations

The smoke test successfully exercised:
- Full Levy 1 with AoW shuffle/draw/implement, Pay/Disband/Muster/CtA
  all skipped, Levy → Campaign transition.
- Plan building (T-Hermann-x3 + 3 Pass; R-Gavrilo-x2 + 4 Pass).
- Activation: real `command_reveal`, real `cmd_march`, real
  `cmd_pass`, FPD T then R, Lord lord card alternation.
- A real Battle: Hermann (Teutonic, attacker) vs Gavrilo (Russian,
  defender). 2 rounds; Hermann lost; permanently removed; Spoils
  transferred to Gavrilo (Hermann's coin / provender / boat).

The test did NOT exercise:
- Storm or Siege from a real Battle outcome (Hermann lost, didn't
  reach pskov).
- Multi-Lord group March / Marshal grouping.
- Avoid Battle / Withdraw responses.
- Multi-Campaign sequencing across Levy boundaries.
- Veche Decline / Auto-Muster / Extra Muster flows in Call to Arms
  with state pressure (e.g., low VP markers).

These are all candidates for follow-up smoke tests.

---

## Round 2 fixes (this PR)

### SMOKE-003 — Spoils recipient hard-coded (FIXED)

`stand_battle` and `cmd_storm` now accept optional `args.spoils_recipient`
to direct Spoils to a specific winner-side own-Lord present at the
Battle Locale (4.4.5). Falls back to `winner_lords[0]` /
`attackers[0]` when the override is missing or invalid.
Regression: `test_smoke_003_spoils_recipient_routed_to_named_lord`.

### SMOKE-004 — Battle log records zero-hit Strikes (FIXED)

`resolve_battle` and `resolve_storm` now skip Strike steps that
produced zero Hits AND distributed nothing. The initiative-order test
was relaxed from "prefix" to "subsequence in order" to accept the
filtering. Regression: `test_smoke_004_battle_log_skips_zero_hit_steps`.

### SMOKE-005 — Activation loop semantics undocumented (FIXED via docs)

ACTIONS.md now contains a dedicated "Activation loop semantics" section
explaining the lord-card lifecycle: actions consume one-by-one until
exhausted or the card ends via Pass/Battle/Siege/Storm/Sail/Tax/etc.
Includes a typical-agent-loop pseudocode block.

### SMOKE-006 — Withdraw uses hardcoded capacity table (FIXED)

`_h_withdraw` had a hardcoded dict with WRONG values for City
(my=2, json=3), Bishopric (my=2, json=3), and Castle (my=1, json=2).
Now reads from `load_strongholds()`. Trade Routes and locales without
a Strongholds table entry (Commanderies) reject Withdraw.
Regression: `test_smoke_006_withdraw_capacity_uses_strongholds_json`.

### SMOKE-007 — Sally loss leaves 0-forces Lord on map (FIXED)

`cmd_sally` loss aftermath now permanently removes any sallying Lord
whose forces all routed (1.5.1). The loser stays Besieged if he has
units left; if he has nothing left, he leaves the game.
Regression: `test_smoke_007_sally_loss_with_zero_forces_removes_lord`.

### SMOKE-008 — Subsumed by SMOKE-007.

### SMOKE-009 — FPD charges 1 Provender for a 0-unit Lord (FIXED)

`fpd_resolve` now uses cost=0 for a 0-unit Lord (defensive — that Lord
should already be removed via Battle Aftermath / SMOKE-007, but this
catches stragglers and avoids charging non-existent units).
Regression: `test_smoke_009_fpd_zero_units_costs_zero`.

## Test count

Pre-fixes: 253 tests. Post-fixes: 271 tests (+18: 5 new regressions, 13
from Q-002 which landed before this PR).

---

## Round 3 (multi-turn Watland; this PR)

Smoke target: 5-turn Watland (boxes 4-8) playthrough, all-pass plans on
both sides. The driver attempts to implement every immediate event with
a default arg picker.

### SMOKE-010 — aow_implement_card partial mutation on resolver failure (FIXED)

**Reproduction.** When implementing R17 Dietrich during Turn 2 of
Watland, my smoke driver passed `args.target = "andreas"` (cylinder
shift). But Andreas is mustered, so his cylinder isn't on the
Calendar; the resolver raises `no_cylinder`. Pre-fix:
`aow_implement_card` had already popped R17 from `pending_draw` before
calling the resolver, so the card vaporized. The agent could not retry
with a corrected arg.

**Fix.** Move every `pending_draw = pending_draw[1:]` pop to AFTER the
relevant mutation succeeds. For event resolvers, the resolver runs
first; only on success does the card move out of `pending_draw`.

**Regression.** `test_smoke_010_aow_implement_card_no_partial_mutation_on_failure`.

### SMOKE-011 — Plow & Reap fires on every LW/Summer box, not just last (FIXED)

**Reproduction.** In Watland, Turn 2 ends at box 5 (Late Winter, year 1
— NOT the last Late Winter; box 6 is). Pre-fix: my `_plow_and_reap`
checked only `season in ("summer", "late_winter")`, so it fired on
every LW box. Sleds got flipped to Carts and halved at box 5, then
again at box 6 (no-op since no Sleds remained). Functionally observable
in the smoke driver: after Turn 2's EOC, all Mustered Lords had Carts
where they should still have Sleds.

**Fix.** `_plow_and_reap(state, box)` now checks specific boxes:
end-of-Summer = {2, 10}; end-of-Late-Winter = {6, 14}. Per RoP 4.9.3
2E correction: NOT Early Winter, NOT mid-season.

**Regression.** Two tests: `test_smoke_011_plow_and_reap_only_at_end_of_season`
and `test_smoke_011_plow_and_reap_summer`.

### Non-bugs found by Round 3

- The disband cascade observed in the 5-turn Watland run is
  **rules-correct**. Lords whose Service markers start near the Levy
  marker disband as the Levy advances and they receive no Pay. The
  simulation just plays out a deterministic decay curve because no
  side does anything productive with their Plans.
- R17 / R11 args ergonomics: the Lord could be on Calendar, in Service,
  or off-the-end. An LLM agent should query state before picking
  `target`. The smoke driver was updated (round 3 only) with a
  `_pick_target` helper that prefers cylinder, then service, then
  None — illustrative of how an agent might handle this.

### Coverage delta

After three rounds of smoke testing the harness has been exercised end-
to-end across:

- A scenario load + pre-Levy decision (Q-001/Q-002 setup transports).
- A full Levy phase with Arts of War shuffle/draw/implement, including
  multiple immediate event types and one this-Levy block.
- A Campaign with all-pass plans, Pass-card alternation, and FPD T-then-R.
- A Campaign with a real Battle (March -> Approach -> Stand -> resolve
  with permanent removal + Spoils transfer).
- A Campaign with a Withdraw (Russian Lord into a Russian City), Sally
  resolved with loser permanently removed, and a Siege siegeworks check.
- A 5-turn multi-Levy/Campaign sequence including Levy -> Campaign ->
  Levy transition, Calendar marker advance, Plow & Reap (now correctly
  scoped to end-of-season).

What's still UNTESTED by smoke:
- Veche Decline / Auto-Muster / Extra Muster with state pressure.
- A Lord re-Mustering after Disband.
- Crusade-on-Novgorod multi-Campaign run (16 turns, the longest).
- T13 William of Modena Legate use (Sub-options 2a/2b/2c).
- R10 Steppe Warriors → Mongol/Kipchaq Vassal Muster.
- A Storm that Sacks the Stronghold and applies Spoils.

Total tests after Round 3: 274 (3 new regressions).
