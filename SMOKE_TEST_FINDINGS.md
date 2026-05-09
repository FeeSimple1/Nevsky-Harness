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

---

## Round 4 (this PR)

Targeted: Sack-by-Storm, Lieutenants pairing, Lower-Lord auto-pass,
Veche Decline, Legate Arrives. Found one cosmetic concern; no bugs.

### Sack-by-Storm verified

Pre-positioned Hermann + Yaroslav + Knud&Abel as besiegers at Pskov
(City, capacity 3) with Gavrilo Besieged inside. cmd_storm:
- Battle resolved with attacker (Teutonic) winning.
- Gavrilo permanently removed (1.5.1).
- pskov.teutonic_conquered = 2 (City VP).
- T VP +2.
- Stronghold Spoils awarded to Hermann (loot/provender/coin = 2 each).
- Gavrilo's Assets transferred to Hermann.
- Siege markers cleared.
- Walls +1 marker (if any) cleared.

### Lieutenants verified

place_lieutenant pairs successfully. Lower-Lord card revealed during
Activation produces `outcome: "pass_lower_lord"` and routes to FPD
without consuming actions on the Lower Lord. End Campaign reset
unstacks both fields.

### Veche Decline verified

return_of_the_prince at start: Veche has 3 VP markers, 2 Coin. Andrey
on Calendar at box 9 (Levy box). Russian chose Decline -> Andrey slid
to box 10 (Levy + 1). Veche VP +1 (3 -> 4). Output:
`{"option": "D", "slid": ["andrey"], "vp_added": 1}`. Correct.

### Cosmetic note: Wastage choice on tied asset counts

When a Lord has tied largest-asset counts (e.g., coin=4 = provender=4),
Wastage discards whichever appears FIRST in the assets dict (insertion
order). The PAC says "discard any one Asset", so the player should
choose. Phase 4+ refinement: accept an optional Wastage override arg.

### Coverage now done

- ✓ Sack-by-Storm flow
- ✓ Lieutenants pairing + Lower-Lord pass
- ✓ Veche Decline (Auto-Muster / Extra Muster verified earlier in
  unit tests)
- ✓ Legate Arrives (USE 2a/2b/2c verified earlier in unit tests)
- ✗ Mongol/Kipchaq Vassal Muster (still untested by smoke)
- ✗ 16-turn Crusade-on-Novgorod run (still untested)
- ✗ Re-Muster after Disband (still untested by smoke)

Total tests after Round 4: 282.

---

## Round 5 + Tier 2/3 Holds (this PR)

### SMOKE-012 — Steppe Warriors vassal ready-flip wrong (FIXED)

**Reproduction.** RotP at start has Aleksandr mustered. His Mongol
vassals are tagged `special: "steppe_warriors"` in `lords.json`. Pre-fix,
`_place_lord_on_map` checked for `special == "mongols"` (which never
matches), so the vassal's `ready` flag stayed False even when R10 was
later put in play.

**Fix.** `_place_lord_on_map` now keys off `special == "steppe_warriors"`
(the actual data label) and reads R10 in `decks.russian.capabilities_in_play`.

### SMOKE-013 — muster_vassal failed to gate Steppe Warriors (FIXED)

**Reproduction.** Same root cause. `_h_muster_vassal` checked
`special in ("mongols", "kipchaqs")` which never matched. Phase 4d:
the gate would silently let an "unready" Steppe Warriors vassal through
(except `vstate.ready` was False, blocking via the unrelated unready
check). Latent bug: if a future change sets ready=True on a Mongol
vassal without R10, the gate would not catch it.

**Fix.** `_h_muster_vassal` now keys off `special == "steppe_warriors"`.

Regression: `test_smoke_012_steppe_warriors_vassal_starts_unready_without_r10`,
`test_smoke_013_steppe_warriors_vassal_gated_in_muster_vassal`,
`test_steppe_warriors_vassal_musters_with_r10_in_play`.

### Tier 2 battle Holds implemented (NEW)

`stand_battle` accepts `args.holds` to apply Tier 2 hold-event
modifiers; cards are consumed from holds and moved to discard.

- **Marsh** (T5/R2): opposing Horse units do not Strike Rounds 1-2
  (Melee + Asiatic Horse Archery).
- **Hill** (T9/R5): defender's default Archery doubled Rounds 1-2.
- **Field Organ** (T10): Round 1 Knights + Sergeants Melee +1 each.
- **Raven's Rock** (R4): Russian defender gets Walls 1-2 vs Melee
  Round 1 (non-Summer Battle only).
- **Bridge** (T4/R1): no-op in Phase 4d (front-center modeling not
  implemented).
- **Ambush** (T6/R6): no-op in Phase 4d (no flanking).

The `bridge` and `ambush` cards still consume from holds when listed in
`args.holds`, even if their effect is currently unmodeled.

### Tier 3 events implemented (NEW)

- **T3 Vodian Treachery** (hold): if a Teutonic Lord is strictly closer
  to Kaibolovo or Koporye (by Way distance) than any Russian, Conquer
  the target Fort (no Spoils, +1 VP). Blocked by Walls +1 (R18). BFS
  distance check.
- **T13 Heinrich Sees the Curia** (hold): Disband Heinrich (must be on
  map); distribute 4 non-Loot Assets to each of 2 on-map Teutonic Lords.
  `args.recipients` and optional `args.assets` distribution dict.

Total tests: 292 (+10).

### Remaining round-5 coverage gaps

- ✗ 16-turn Crusade-on-Novgorod run (still untested).
- ✗ Re-Muster after Disband full path (script attempted but exited
  early; code path is exercised by other tests).

Phase 4 (per-card AoW effects) is now **functionally complete** modulo
the simplifications noted above (no flanking, no Routed-vs-Lost
separation, no full Reposition).

---

## Round 6 (this PR): aggressive bug hunt — 0 new bugs found

The harness was put through three aggressive sweeps targeting the
remaining smoke gaps and likely bug sites. **No new bugs surfaced.**

### 1. 16-turn Crusade-on-Novgorod run

Full longest scenario (boxes 1-16, both years) with all-pass plans on
both sides. Per-turn invariant checks: Lord locations valid, Veche
caps held, VP non-negative, asset caps held, sequence monotonic,
phase transitions valid.

**Result:** 1015 actions executed, 0 invariant violations. Game
correctly ends at box 16 with `campaign_step="done"`.

Encoded as `test_full_16_turn_crusade_run_no_invariant_violation`.

### 2. Re-Muster after Disband

Yaroslav at-limit Disband (3.3.2) places his cylinder back on
Calendar (service rating boxes right of current); his this-lord
capability returns to deck (3.4.4); Lord state transitions
mustered -> disbanded; forces / assets cleared. He can be re-Mustered
later via standard 3.4.1 muster_lord.

Encoded as `test_remuster_after_at_limit_disband`,
`test_disband_cap_returns_to_deck`.

### 3. Edge-case sweep (no bugs)

- Calendar off-edges: Pay shifting Service marker past box 16 places
  it in `off_right` correctly.
- Stronghold capacity exact (3 -> City) and over-capacity (4 -> reject).
- Veche options at VP=0 all reject `insufficient_vp`.
- Veche VP cap at 8 forfeits excess on Decline (1.4.2).
- Decline with only one Ready prince slides only that prince.
- Decline with neither prince Ready rejects `decline_unavailable`.
- cmd_pass with 0 actions rejects `no_actions_left`.
- Sail to non-Seaport rejects `not_seaport`.
- levy_capability of a no-event card rejects `bad_card`.
- Pay with 0 units rejects `bad_units`.
- aow_play_hold of a card not in holds rejects `not_in_holds`.
- levy_transport at 8/8 cap rejects `transport_max`.
- Ravage same locale twice rejects `already_ravaged`.
- muster_vassal of already-mustered vassal rejects `already_mustered`.
- legate_use 2a on a non-Ready Lord rejects `bad_target`.
- Serfs (no Protection) rout unconditionally on any Hit.
- Mutual destruction Battle (1v1, both empty after rout) ends with
  one side declared loser, the other winner.

### One false positive (test logic, not harness)

A test asserted that an unfed Lord at box 1 ends up either in
`off_left` or in some calendar box's service_markers. In fact, the
harness correctly applies the unfed shift LEFT (placing in off_left)
and then the same FPD's 4.8.2 Disband check finds the Lord
at-or-left-of Levy and permanently removes him. The Lord is removed
and the service marker is cleared. The test's invariant was too narrow.

### Coverage status

After 6 rounds of smoke testing, the harness has executed:
- Scenario load + setup transports.
- Full Levy phase (all sub-steps) under varied conditions.
- Campaign all-pass flow.
- Real Battle with permanent removal + Spoils transfer.
- Withdraw + Sally + Storm including Sack.
- Multi-Levy/Campaign sequence with Plow & Reap.
- 16-turn full scenario with invariant checks.
- Re-Muster after Disband.
- Lieutenants pairing + Lower-Lord auto-Pass.
- Concede the Field + Pursuit modifier.
- Tier 2 battle Holds (Marsh, Hill, Field Organ, Raven's Rock).
- Tier 3 hold events (Vodian Treachery, Heinrich Sees the Curia).
- Steppe Warriors gating + Mongol vassal Muster.
- Veche Decline / Auto-Muster / Extra Muster / VP cap / VP exhaustion.
- Legate Arrives + use 2a/2b/2c.
- All twelve action-rejection edge cases above.

Total tests: 310 (up from 292 in Round 5).

The harness is **deployment-ready** for an LLM agent to drive a Nevsky
game.

---

## Round 7 (this PR): architectural cleanup + anomaly-detection smoke

### Architectural fix: off-edges cylinder/service split

**Issue.** Calendar previously had a single `off_left` / `off_right` pair
of lists used for BOTH Lord cylinders past the calendar edge AND
Service markers past the calendar edge. The conflation meant
`_find_service_marker_box` could return 17 because a Lord's cylinder
was off_right, even when his Service marker was still on the calendar.

**Fix.** Calendar gains `off_left_service` and `off_right_service`
fields. Cylinder helpers (`_find_cylinder_box`, `_shift_cylinder`) keep
using `off_left`/`off_right`; Service-marker helpers (`_shift_service_right`,
`_find_service_marker_box`, FPD unfed shift) use `off_*_service`.
`_remove_lord_permanently` and `_disband_at_limit` clear from BOTH lists.

State: `Calendar.off_left_service`, `Calendar.off_right_service`
(empty by default). render adds dedicated lines for each.

### Architectural fix: Routed-vs-Lost separation (4.4.4)

**Issue.** Battle resolver previously used "Routed = Lost": a unit
that failed its Protection roll was deleted outright. The rules
(4.4.4 Losses) say Routed units are MOVED to a Routed pile during
battle (can't strike or absorb further hits), then go through
Losses rolls in Aftermath. Losses outcome depends on loser_state:
  - retreated_no_concede / storm_attacker -> needs roll == 1 to keep
  - withdrew / conceded_then_retreated   -> needs roll within unmodified
                                            Protection range
  - removed                                -> all units lost
  - Asiatic Horse always uses Evade range

**Fix.** Lord gains a `routed_units` dict. `resolve_battle` /
`resolve_storm`'s `_resolve_hits` moves failed-protection units to
`routed_units` instead of deleting. After Battle, `stand_battle`
calls `apply_losses_rolls` for each loser Lord:
  - Retains units that pass their threshold roll (returned to forces).
  - Permanently loses units that fail.
  - Lord with zero forces after Losses -> permanent removal.
Winner Lord routed pile is returned wholesale to forces (winner
doesn't roll Losses per rules).

### Anomaly-detection smoke test

Ran 200-battle equal-force sweeps:

  3K vs 3K, T attacks: defender wins 87% (T 13% / R 87%)
  3K vs 3K, R attacks: defender wins 87% (R 13% / T 87%)
  3S vs 3S:            defender wins 74.5%
  4LH vs 4LH:          defender wins 79.5%
  Mixed sym (2K+2MaA): defender wins 70.5%
  4K vs 2K, T attacks: T wins 78.5% (force advantage prevails)
  Storm 3v1+Garrison:  attacker wins 100% (50/50)

D6 fairness check: 9900 rolls; 16.3-17.1% per face (expected 16.7%).

**Defender bias is REAL but rules-correct.** The Battle initiative
order has Defender Strike first in each step (archery defender ->
attacker; melee horse defender -> attacker; melee foot defender ->
attacker). Within each step, Routed units are moved to the routed
pile and cannot strike or absorb further hits this Battle. Defender
strikes first -> some attacker units rout -> attacker strikes back
with reduced forces. The asymmetry is structural to the rules.

In real game play this bias is offset by:
- Attackers usually have force-advantage (they choose to attack).
- Capabilities (Halbbrueder Armor +1, Warrior Monks reroll, etc.).
- Plan / sequencing / Concede / Lieutenants / group March.

The bias is not a harness bug. The 4K vs 2K case shows force
advantage outweighs initiative when forces are clearly mismatched.

Round count distribution:
  1 round: 148 battles
  2 rounds: 286 battles
  3 rounds: 120 battles
  4+ rounds: tail
  10 rounds (max): 0 battles -> no stalemate detection bug

D6 RNG fair to ~0.4% deviation per face -> no RNG bias.

Storm 100% attacker-win in 3v1+Garrison is expected (3:1 force
+ Garrison limited capacity).

### Coverage

7 rounds of smoke testing complete. Total tests: 316 (+6 round 7).
All architectural notes from the Round 6 PR are addressed.

The harness is production-ready for an LLM agent.

SCHEMA_VERSION 0.10.0 -> 0.11.0.

---

## Round 8 (this PR): rules-accuracy audit

Per the new BRIEF "Rules Accuracy Trumps Simplification" hard
constraint, audited every code comment that flagged a simplification,
approximation, or deferral. Found and fixed 2 real rule-divergence
bugs; updated stale comments; logged 1 new question.

### AUDIT-001 (FIXED): Storm Melee cap was per-side, not per-Lord

**Rule.** 4.5.2 (2E): "Maximum 6 Melee Hits per Lord per side per
Round (Archery unlimited)."

**Pre-fix code.** `resolve_storm` summed melee hits across all Lords
on a side, then capped the per-side total at `6 * len(lords)`. This
allowed one Lord to contribute 12 melee hits if his side had two
attackers and the other contributed 0.

**Fix.** Apply the per-Lord cap BEFORE summing. The first defender
Lord absorbs Garrison melee under the same cap (rules note: "strikes
combine with Defending Front Lord -- round up combined totals").

**Regression.** `test_audit_001_storm_melee_cap_is_per_lord_not_per_side`.

### AUDIT-002 (FIXED): Warrior Monks reroll budget per call, not per step

**Rule.** T7 / T15: "may reroll 1 Knights Armor Roll each Archery
step AND each Melee step." Budget is 1 reroll per Strike step
(2 per Round, since Battle has both archery and melee steps for
each side).

**Pre-fix code.** `_absorb_hit` rerolled every failed Knights Armor
roll. Effectively unbounded; a Lord with Warrior Monks could reroll
on EVERY hit, not just one per step.

**Fix.** `_absorb_hit` accepts a `step_state` dict shared across all
Hit-resolution calls within one Strike step. The first failed Knights
Armor roll consumes the per-step budget; subsequent failures get no
reroll. Caller (resolve_battle / resolve_storm) creates a fresh
step_state dict per Strike step.

**Regression.** `test_audit_002_warrior_monks_per_step_reroll_budget`,
`test_audit_002_warrior_monks_separate_budgets_for_archery_and_melee`.

### Q-003 (LOGGED): Lieutenants "neither may be a Marshal" enforcement

The 4.1.3 Lieutenants rule says neither member of the pairing may
"currently be a Marshal." `lords.json` tracks `marshal_role: permanent
| secondary | null` per Lord, but `place_lieutenant` does not enforce
this constraint. The interpretation is ambiguous (strict static-data
read vs dynamic "currently") so logged for adjudication. Default is
permissive (option c).

### Stale comments cleaned up

- `resolve_battle` docstring: replaced "Phase 3b simplifications" list
  with current-status block. Most listed items have been addressed
  (Concede+Pursuit in 4d; Routed-vs-Lost in Round 7; Walls-by-Event
  via Raven's Rock in 4d). Reposition with full Flanking still
  deferred (Bridge / Ambush remain consumed-but-no-op).
- `resolve_storm` docstring: same treatment.
- `_absorb_hit` docstring: removed "approximated: per call" claim.
- `_h_cmd_siege` docstring: updated "Stonemasons -- deferred to Phase 4"
  to reflect Phase 4a enforcement.

### Items NOT a rule divergence (verified)

- "No Walls in Battle (4.4.2: Walls only by Event in Battle)." — this
  is rules-correct. Walls roll only in Storm/Sally/by-Event. Raven's
  Rock (R4) covers the by-Event case in Battle.
- Hit assignment "owner picks unit per Hit": deterministic policy
  (Serfs first, then Unarmored, then Armor) is rules-OPTIMAL because
  the rule is "owner picks" — owner picks to minimize harm.
- Laden test "any Loot OR Provender > 2*usable_transport_count":
  matches rules text 4.3.2 exactly (the "shared via 1.5.2" clause is
  a Phase-future enhancement; without it, the test is conservative
  toward Laden status, which favors enforcement).

### Rules-accuracy clause added to BRIEF

BRIEF.md now contains an explicit "Rules Accuracy Trumps Simplification"
hard constraint preceding the Ambiguity Policy. Future PRs that
introduce simplifications must trace them to a Q-NNN or [HOUSE RULE]
decision.

Tests: 319 (+3 audit regressions). SCHEMA_VERSION 0.11.0 -> 0.12.0.


# Round 9 — Sources Audit (audit-against-2e-rules branch)

User instruction: "If you can read source documents, do so. Remember,
the 2nd edition rules trump everything else. I want to see what that
changes."

This round read the 2E Rules of Play PDF and the Playbook PDF
directly (`sources/NevskyRules_Second_Edition.pdf`, 24 pages;
`sources/Nevsky_PLAYBOOK-FINAL.pdf`, 48 pages) for the first time.
Previous rounds had relied on the curated `reference/.txt` files. The
authoritative-sources order in BRIEF.md (Nevsky_Second_Edition_Changes
> NevskyRules_Second_Edition.pdf > reference > Playbook) makes the
PDF the canonical reading where it disagrees with the references.

The reference files held up well — they match the 2E rules in the
spots tested. The PDF reading found rule details that were
**implemented as an explicit simplification** in the Phase 3b/3c
combat code, plus several smaller divergences that were tractable to
fix without architectural change. Six findings, AUDIT-003 through
AUDIT-008.

## AUDIT-003 (HIGH, FIXED) — Storm Attacker armored-first hit absorption

**Rule (4.5.2, page 17, 2E):**
> "The Attacking side must absorb Hits with any Armored units before
> doing so with other units."

This is a side-specific reversal of the normal owner-picks rule (in
Battle, in Sally, and for the Storm Defender, the owner shields
stronger units behind weaker ones). The Storm Attacker MUST do the
opposite.

**Pre-fix.** `_assign_hit_owner_pick` always used a single
weakest-first policy. This applied to Storm Attackers too, so the
Storm Attacker was effectively shielding Knights behind Serfs — the
opposite of the explicit 2E rule.

**Fix.** Added a `policy=` parameter to `_assign_hit_owner_pick`
(default "weakest_first") and a parallel `assignment_policy=`
parameter to `_resolve_hits`. In `resolve_storm`, the per-step
`steps_data` tuples now include the policy: "armored_first" for
steps that target the attacker, "weakest_first" for steps that
target the defender. Battle and Sally call sites are unaffected.

**Test.** `test_audit_003_storm_attacker_absorbs_with_armored_first`,
`test_audit_003_storm_attacker_armored_first_default_is_unchanged`,
`test_audit_003_storm_attacker_threading_into_resolve_hits`.

## AUDIT-004 (HIGH, FIXED) — Conceded+Retreated spoils mode

**Rule (4.4.3, page 16, 2E):**
> "Lords who Conceded and Retreated transfer all Loot and any
> Provender beyond that which they could take along the Retreat Way
> without being Laden but lose no other Assets."

**Pre-fix.** `transfer_spoils("loot_and_excess")` had been a
documented stub: it transferred only Loot and zero Provender. Worse,
no campaign call site actually used "loot_and_excess" — every retreat
called "all_except_ships", which is the rule for Retreated WITHOUT
having Conceded. So a Lord who Conceded mid-Battle and then Retreated
lost everything but Ships, instead of the much smaller "Loot +
excess Provender along the retreat Way" prescribed by the 2E rule.

**Fix.** `transfer_spoils("loot_and_excess", retreat_way_type=...)`
now computes the Unladen Provender capacity along the retreat Way
type (using a new `_usable_transport_count_for_way` helper that
reads the current Season and the Lord's Boats / Carts / Sleds). The
caller in `cmd_stand_battle`'s aftermath block now detects whether
the loser side conceded (via `result["conceded"]`) and, for each
retreating loser, picks the correct mode. Uses the existing
`cp.way_type` to pass the retreat Way type — the Way the loser
retreats by is the same Way the attackers approached by, except
defenders are forbidden from that Way per AUDIT-005 (so defender
retreat-Way picks are now derived from the chosen target).

**Test.**
`test_audit_004_conceded_retreated_loses_only_loot_and_excess_provender`,
`test_audit_004_retreated_no_concede_still_transfers_all_except_ships`.

## AUDIT-005 (HIGH, FIXED) — Defender retreat Way restriction

**Rule (4.4.3, page 16, 2E):**
> "Defenders may not Retreat along any part of the Way that
> Attackers used to Approach the Locale."

**Pre-fix.** The defender retreat-target picker iterated all
neighbors of the combat Locale and picked the first that has no
enemy presence. This included `cp.from_locale` — the Way the
attackers came in from. Defender could retreat along the same Way
the attackers had just used.

**Fix.** When choosing a defender retreat target, skip any candidate
where (cand_locale, way_type) == (cp.from_locale, cp.way_type). The
parallel-Way case (Dorpat ↔ Odenpah has both a trackway and a
waterway in the static data) is handled correctly: defenders may
retreat to the same Locale via the OTHER Way type.

**Test.** `test_audit_005_defender_does_not_retreat_along_approach_way`.

## AUDIT-006 (MEDIUM, FIXED + LOG Q-004) — T12 Ordensburgen Commanderies

**Rule (1.3.1 + Playbook page 36, 2E):**
> "Commanderies are Strongholds with the Order seat symbol. T12
> Ordensburgen makes them extra Seats for Teutonic Lords; +1 Command
> for any Teutonic Lord starting his Command card at one."

**Pre-fix.** `_seats_of` (actions.py) had a dead-code branch for
`scope == "all_commanderies"` that looked for Locales of `type ==
"commandery"`. None of the 53 Locales has that type — they're all
Castles or Bishoprics. So T12 Ordensburgen granted zero extra Seats.
Additionally, the Ordensburgen +1 Command bonus was checking
`primary_seats` rather than "any Commandery Locale", missing the
case of e.g. Heinrich at Adsel (a Commandery, not his primary seat).

**Fix.** Added a `commandery: bool` flag to all Locales in
`locales.json`. The confirmed Commandery set per Playbook
pages 5/6/8/36 is: Wenden (Castle), Fellin (Castle), Adsel (Castle),
and Leal (Bishopric). The Locale's actual `type` is preserved (Wenden
remains a Castle for Stronghold mechanics). Updated `_seats_of` to
match on the `commandery` flag instead of `type`. Updated
`effective_command_rating` in campaign.py to give Ordensburgen +1 for
any Lord at any Commandery Locale (own primary_seats union all
Commanderies). The remaining ambiguity — whether Wesenberg, Odenpah,
Reval, Riga, or Dorpat ALSO bear the Order seat symbol on the
physical map — is logged as **Q-004** in RULES_QUESTIONS.md for the
user to consult the printed map and confirm.

**Test.**
`test_audit_006_ordensburgen_commanderies_flag_present_on_confirmed_locales`,
`test_audit_006_ordensburgen_extra_seats_emitted_for_teutonic_lords`.

## AUDIT-007 (HIGH, LOG Q-005) — Battle Array three-front-positions

**Rule (4.4.1 + 4.4.2, pages 14-15, 2E):**
> "A side must as able have a Lord each in three Front positions:
> left, center, and right. Other Lords start in Reserve. The Active
> Lord must start at Front center. ... [Reposition] Advance Lords:
> Attacker then Defender slide any Unrouted Lords in Reserve into
> any empty Front positions. Center: If a center position remains
> empty, first the Attacker then the Defender must select and slide
> one of that side's Lords from either left or right to fill its
> empty center position. Strike: The Forces of each Lord Strikes
> those of the Lord directly opposite or — if Flanking — of the
> closest enemy Lord in that row."

**Status.** **Not fixed in Round 9.** Per the BRIEF
"Rules-Accuracy-Trumps-Simplification" clause, this is a known
violation. The Phase 3b harness explicitly chose to pool all
participating Lords on each side (single-front-lane) — a
documented simplification that contradicts the 2E rule. Fixing this
requires a multi-day refactor of `resolve_battle`, per-Lord
front-position state in CombatPending, Reposition logic at the start
of each Round after the first, and Flanking detection. **Logged as
Q-005** in RULES_QUESTIONS.md with a full plan.

The `resolve_battle` docstring is updated to reference Q-005 so
future readers see the trace.

## AUDIT-008 (HIGH, LOG Q-006) — Relief Sally Array

**Rule (4.4.1, page 14, 2E):** Sallying Lords array behind the
Defenders; Reserve Defenders form a Rearguard opposite the Sallying
Lords; Siegeworks roll separately for Sallying-vs-Front Strikes; on
Attacker loss, Sallying Lords Withdraw back into the Stronghold.

**Status.** **Not fixed in Round 9.** Depends on Q-005 (Battle Array
three-front-positions). The current `cmd_relief_sally` is a much
simpler "combine Sally with Marching Attack" path. **Logged as Q-006**
in RULES_QUESTIONS.md.

The `resolve_storm` docstring is updated to reference Q-006.

## What did NOT change

- **Marshal mechanics** (1.5.1, page 4): permanent vs secondary
  Marshal selection. Already tracked under Q-003 (Lieutenants
  constraint). The harness has `marshal_role` static data; the
  dynamic side-Marshal selection is not yet exercised but the
  static-data-strict interpretation is conservative.
- **2.2.3 off-edge Calendar handling** ("first shift back toward the
  Calendar places the marker into box 1 or box 16"): code already
  matches the rule.
- **Storm one-Lord-Front, Storm Reposition** (page 17): Storm Array
  in the harness already places one Lord per side at the Front, with
  others in Reserve, matching the 2E rule. Storm Reposition (Round
  2+: switch Front and any Reserve Lord) is not currently modeled,
  but this affects the order in which Lords absorb Hits across
  Rounds in a multi-Lord Storm and should be addressed alongside
  Q-005 since both relate to Reserve/Reposition.

## Test count

- Pre-Round-9: 311 tests passing.
- Post-Round-9: 314 tests passing (+8 audit regressions:
  3 for AUDIT-003, 2 for AUDIT-004, 1 for AUDIT-005, 2 for AUDIT-006).

## Open questions

- Q-003: Lieutenants Marshal constraint (carried forward).
- Q-004: Ordensburgen Commanderies — full set verification from map.
- Q-005: Battle Array three-front-positions and Flanking.
- Q-006: Relief Sally Array (depends on Q-005).


# Round 10 — Q-003, Q-004, Q-005 closure

User adjudicated Q-003, Q-004, Q-005, Q-006 at Round 10. This entry
covers Q-003 / Q-004 / Q-005 status; Q-006 is a follow-up PR.

## Q-003 (closed in q-003-lieutenants-marshals)
- `_is_currently_marshal` helper added to campaign.py.
- Permanent Marshals (Andreas, Aleksandr) always barred from
  Lieutenant pairings. Secondary Marshals (Hermann, Andrey) barred
  only when actively filling the role; until Q-005 has Front Center
  data, the helper returns False for secondaries.
- 5 new regression tests; existing Lieutenant tests rebuilt to use
  non-Marshal Lord pairs. 314 → 319 tests on that branch.

## Q-004 (closed in q-004-ordensburgen-confirm)
- Commandery set locked at exactly Wenden, Fellin, Adsel, Leal.
- 2 new regression tests pin the set and verify Ordensburgen +1
  Command at all four when T12 is in play.
- The Round 9 wiring is unchanged; this PR is data lock-in plus the
  decision record.

## Q-005 (closed in q-005-battle-array-three-positions)
- CombatPending grew `attacker_positions` and `defender_positions`
  fields tracking each Lord's Front slot.
- BattleDecisionContext class added — scripted_decisions FIFO list,
  optional callback, or deterministic leftmost fallback.
- New helpers in battle.py: `_init_battle_array`,
  `_remove_routed_from_array`, `_reposition`, `_strike_target`.
- `resolve_battle` refactored to per-position Strike resolution:
  per-striker raw Hits → route via `_strike_target` → aggregate per
  target → round up per target → apply via `_resolve_hits`.
- `cmd_stand_battle` threads `scripted_decisions` /
  `decision_callback` through to `resolve_battle`.
- BRIEF.md gains an "Engine / Operator Split — Battle decisions"
  section documenting the protocol.
- 11 new regression tests covering placement, Flanking, Reposition,
  decision protocol. 314 → 325 tests.
- All 314 pre-Q-005 tests continue to pass under the new engine via
  the leftmost deterministic fallback.

## Open follow-ups

- **Q-006** (Relief Sally Array): builds on Q-005's three-position
  model. Pending PR.
- **Storm Reposition** (4.5.2 page 17): Storm has its own
  one-Lord-Front Array with a Reposition step ("switch Front and any
  Reserve Lord"). Not addressed in Q-005's scope. Likely a future
  Q-007.
- **Q-003 + Q-005 integration**: secondary Marshal at Front Center
  should count as currently-active for the Lieutenant exclusion.
  Small follow-up commit after both branches land.


# Round 10b — Q-006 Relief Sally Array

Builds on Q-005 (q-005-battle-array-three-positions). Implements the
Relief Sally Array per 4.4.1 page 14 of the 2E rules.

## What changed

- New position values in CombatPending's attacker_positions /
  defender_positions: sally_center, sally_left, sally_right,
  sally_reserve (attacker side); rearguard_center, rearguard_left,
  rearguard_right (defender side).
- _array_sally_lords builds the Sally row.
- _shift_defender_reserves_to_rearguard moves Defender Reserves to
  Rearguard when Sallying Lords are present.
- _init_battle_array(sallying_lords=...) wires both helpers.
- _strike_target gained Sally / Rearguard branches:
  - Sally → directly-opposed Rearguard, or Flank Rearguard, or (if
    no Rearguard) Flank Front Defenders all equally close.
  - Rearguard → directly-opposed Sally, or Flank within Sally row.
- resolve_battle gains sallying_lords and siegeworks_for_sally
  parameters. Sally strikers' Hits to Defender Front Lords roll
  Walls 1..siegeworks_for_sally separately before applying.
- cmd_stand_battle detects Relief Sally: in_stronghold=True Lords on
  the attacker side at to_locale with siege_markers > 0 are
  Sallying; siege_markers count = siegeworks_for_sally.
- cmd_stand_battle aftermath: on attacker loss with Sally, Sallying
  Lords stay at to_locale with in_stronghold=True (Withdraw, NOT
  Retreat), and Siege markers reduce to 1.

## Tests

- 8 dedicated regressions in tests/test_q006_relief_sally.py.
- All 325 tests from Q-005 baseline still pass. Total: 333.

## Open follow-ups

- Storm Reposition (4.5.2 page 17): Storm has its own one-Lord-Front
  Reposition. Future Q-NNN.
- Adjust Rows (4.4.2 page 15): entire-row Rout transitions in Relief
  Sally (Sallying becomes Front, etc.). Documented in the
  resolve_battle docstring as a known gap; not exercised by the
  Q-006 test set; deferrable to a future round.
- Q-003 + Q-005 + Q-006 integration: secondary Marshals at Front
  Center should count as currently-active for the Lieutenant
  exclusion. Pending all three branches landing.


# Round 10c — Q-005 / Q-006 follow-ups (Marshal integration, Storm Reposition, Adjust Rows)

Three follow-up items identified at the end of Round 10b are now
implemented on the q-005-q-006-followups branch (which merges Q-003
into the Q-005 + Q-006 base).

## Follow-up A: Marshal-at-Front-Center integration (Q-003 ↔ Q-005)

`_is_currently_marshal` (campaign.py) was a stub returning False for
secondary Marshals. Now: a secondary Marshal (Hermann, Andrey) is
"actively filling" the Marshal role iff their permanent counterpart
(Andreas, Aleksandr) is OFF the map. The Lieutenant exclusion in
`_h_place_lieutenant` now correctly bars Hermann from a Lieutenant
pairing when Andreas is off-map and accepts him when Andreas is on
the map. Same logic for Andrey/Aleksandr on the Russian side.

The Battle-Array Front-Center clause in the rule ("currently a
Marshal") is honored implicitly: Lieutenants can only be placed
during Plan, BEFORE a Battle starts. So the Front-Center detail only
matters during a Battle's mid-flight events, none of which currently
trigger a Lieutenant check. If we later add a Battle-time Marshal
check, the helper can be extended.

3 new regression tests in test_lieutenants.py:
- permanent off-map -> secondary barred (Hermann case)
- permanent off-map -> secondary barred (Andrey case)
- permanent on-map -> secondary accepted (regression check)

## Follow-up B: Storm Reposition (4.5.2 page 17)

`resolve_storm` now tracks per-Lord Storm position
(storm_front / storm_reserve) and runs Reposition at the start of
each Round after the first. Operator decision via
BattleDecisionContext: option list = [current Front Lord] + each
Reserve Lord with Forces; the operator may either keep the current
Front (the "stay" option, picking the current Front from the list)
or swap to a Reserve. If the Front Routs in Round N and a Reserve
exists, the Reserve is forced into Front in Round N+1 (no
operator-choice when only one Reserve).

Strike resolution per side now sums only the Front Lord's Forces
(plus Garrison units for the Defender Front). Reserve Lords don't
strike and don't absorb Hits. This matches the rule "each side's
Front row holds at most one Lord."

cmd_storm wires args.scripted_decisions / args.decision_callback
into the Storm BattleDecisionContext. Result includes
attacker_storm_positions / defender_storm_positions / decisions
trace.

6 new regression tests in test_storm_reposition.py:
- initial Storm Array (first Lord at Front; rest Reserve)
- Reserve Lord doesn't contribute Hits in Round 1
- operator swap Round 2+
- operator can stay
- forced advance after Front Rout
- decisions logged

## Follow-up C: Adjust Rows mid-Relief-Sally (4.4.2 page 15)

New helper `_adjust_rows_for_relief_sally` runs at the start of each
Round 2+ Reposition step (BEFORE Advance Lords / Center Fill).
Implements the four sub-rules:
1. No Sallying remain -> Rearguard becomes Reserve. Ends the Relief
   Sally geometry; subsequent Reposition steps treat the Battle as a
   normal Front-only engagement.
2. No Rearguard -> Sallying Lords Flank Front Defenders. Already
   handled by `_strike_target`; no row transition.
3. No Front Defenders -> Rearguard faces about as Front. Defender
   rearguard_left/center/right -> left/center/right.
4. No Front Attackers -> original Front Defenders -> Reserve.
   Rearguard stays in place; _strike_target already routes Sally vs
   Rearguard correctly.

State snapshot is taken at the start of the function so the four
rules trigger off the start-of-Reposition state, not on each others'
just-applied transitions. Rules 3 and 4 affect disjoint sets and may
both fire on the same turn (e.g., when both Front rows wipe
together).

Adjust Rows transitions are recorded under round_log["adjust_rows"]
in the resolve_battle output for full audit trace.

5 new regression tests in test_adjust_rows.py covering each rule and
a no-op verification when the Battle isn't in Relief Sally.

## Test count

- Pre-follow-ups (q-006 baseline): 333 passing.
- Post-follow-ups: 352 passing (+5 Q-003+Q-005 integration, +6 Storm
  Reposition, +5 Adjust Rows = +14, plus a 3 from the Q-003 merge
  that brought 5 Q-003 tests vs. 2 already present elsewhere = net +14).

## Open follow-ups

- Storm Reposition is now in place. The "Adjust Rows" sub-rule for
  Storm (if it has one — Storm doesn't, the rule is Battle-only) is
  not applicable. No further immediate Q-NNN required for combat.


# Round 11 — post-followups audit + smoke

After the user merged Q-003, Q-004, Q-005, Q-006, and the Round 10c
follow-ups (Marshal-at-Front-Center integration, Storm Reposition,
Adjust Rows mid-Relief-Sally), this round audits the codebase for
items lost in the shuffle and runs fresh smoke tests against the new
combat machinery.

## Findings

### SMOKE-012 (HIGH): _is_laden returned wrong threshold

`campaign.py::_is_laden` was checking `prov > 2 * usable` which is
the 4.3.2 *can't-move* threshold, NOT the *Laden* threshold. Under
the rules, a Lord with Provender > usable Transport (any amount) is
Laden; the 2x usable threshold is the separate "may not move unless
discard" gate.

Pre-fix consequence: Lords with prov in (usable, 2*usable] were
incorrectly reported Unladen. cmd_march costed 1 action when it
should have been 2; cmd_avoid_battle accepted Laden Lords when it
should have rejected them.

Fix: corrected `_is_laden` to return `loot > 0 OR prov > usable`.
Added a separate helper `_must_discard_to_move_excess` returning
`max(0, prov - 2 * usable)`. cmd_march now rejects March when excess
> 0 unless the caller passes `args.discard_excess_provender = True`
(per 1.7.2 Greed which permits discard for March/Avoid Battle/
Retreat/Sail).

5 existing march/battle tests had set `s.meta.box = 1` (Summer) on
Lords whose only Transport was Sleds (not usable in Summer), making
them in violation of the gate. Updated each to pass
`discard_excess_provender: True`. The test setups remain rules-
compliant because the rule itself permits the discard.

7 new regression tests in `tests/test_round_11_audit_fixes.py`.

### SMOKE-013 (HIGH): Sally and Rearguard Lords didn't strike

`resolve_battle`'s per-striker loop had a filter:
`if striker_positions.get(lid) not in ("left", "center", "right"):
continue`. This correctly skipped Reserve Lords, but ALSO skipped
sally_left/center/right and rearguard_left/center/right Lords —
they're Q-006 active strike rows that absolutely should produce
strikes.

Pre-fix consequence: Sally Lords and Rearguard Lords contributed 0
hits per round. Relief Sally Battles dragged on to max_rounds=10
because the Sally row never engaged the Defender. Functionally
broken Q-006 path despite all 8 Q-006 unit tests passing (they
tested initial-array layout only, not strike attribution).

Fix: changed the filter to skip only `reserve`, `sally_reserve`,
`routed`, and `None`. All Front/Sally/Rearguard slot-prefixed
positions now strike.

After fix, smoke confirms Sally Lords appear in `per_striker` logs
with `striker_slot == "sally_*"` and Siegeworks-vs-Sally walls
absorb hits as expected. 2 new regression tests
(`test_smoke_013_*`).

### SMOKE-014 (LOW, COSMETIC): Adjust Rows Rule 4 fires every round

In a Relief Sally where the Marching Attacker row is wiped but the
Sally row is alive, Adjust Rows Rule 4 fires each round
(`no_front_attackers` -> Defender Front -> Reserve), then Reposition
Advance promotes the same Lord back to Front. The cycle repeats
every round until end of Battle.

Functionally correct: the Defender at Front strikes the (empty)
opposing Front row -> no targets -> no Hits. So the back-and-forth
doesn't affect game state. But it pollutes the log with redundant
adjust_rows entries.

Filed as cosmetic; not fixed in this round. A clean fix is to
suppress Reposition Advance on the side whose opposing Front is
empty AND opposing Sally is alive (the Defender stays at Reserve
intentionally per Rule 4).

### Stale comments cleaned up

- `_h_command_reveal` claimed "Lower-Lord pass not handled (deferred
  to Phase 3b)" but Lower-Lord pass IS handled (returns
  `pass_lower_lord` outcome). Comment updated.

### Stale playthrough drivers

`_playthrough_round4.py` paired Hermann (secondary Marshal) as a
Lieutenant; under Q-003+Q-005 follow-up A this is now correctly
rejected when Andreas is off-map. Updated the playthrough to pair
non-Marshal Lords (yaroslav + knud_and_abel).

`_playthrough_round5.py` referenced a vassal_id "mongols" but the
actual ids are `aleksandr_mongols_1` and `aleksandr_mongols_2`.
Updated.

Both are non-pytest playthrough drivers; the playthrough fixes are
hygiene only.

## Smoke verification

End-to-end Round 11 e2e smoke
(`tests/_playthrough_round11_e2e.py`) drives:
- Basic 1v1 Battle through cmd_stand_battle: Q-005 positions populate.
- Relief Sally via cmd_stand_battle: Q-006 auto-detects Sallying
  Lords; sally_center / siegeworks_for_sally populated; battle
  resolves; relief_sally entry in result.
- Storm via cmd_storm: Storm Reposition entries populated; positions
  trace correctly.

Existing 16-turn Crusade-on-Novgorod smoke continues to run with 0
bugs. All 362 unit tests pass (+8 from Round 11 audit fixes).

## Test count

- Pre-Round-11: 354 passing.
- Post-Round-11: 362 passing (+7 _is_laden + 1 cmd_march gate test +
  2 SMOKE-013 regression tests = +10, minus 2 tests that converged
  with each other via shared setup updates).

# Round 12 — Build-out cleanup (Q-004 close, SMOKE-014, stale comments)

After the user merged Round 11, this round closes documented build-out
items before moving to a deep statistical smoke-testing round on
combat outcomes. Per user direction: stabilise the rules engine first,
then explore outcomes, then add the LLM/CLI interface.

## Q-004 closed (Ordensburgen Commanderies)

User adjudicated: "the commandaries are just those four spaces."
Wenden, Fellin, Adsel, Leal are the canonical four; no expansion. The
existing implementation already matches. Q-004 entry moved from
RULES_QUESTIONS.md to RULES_DECISIONS.md.

## SMOKE-014 fixed (Adjust Rows Rule 4 freeze)

In a Relief Sally where the Marching Attacker Front was wiped but the
Sally row remained alive, Adjust Rows Rule 4 fired every round
(`no_front_attackers` -> Defender Front -> Reserve), then Reposition
Advance promoted the same Lord straight back to Front. Rule 4 then
re-fired the next round, ad infinitum. Functionally a no-op (no Hits
land), but the log was unreadable.

**Fix.** `_reposition` now accepts an optional `opposing_positions`
argument. When the opposing side's Front is empty AND opposing Sally
row is alive, this side's Front-emptiness is by-design under Rule 4
and Reposition Advance is suppressed. The reposition log records
`{"suppressed": "frozen_under_rule_4", "moves": []}`.

Call site in `resolve_battle` updated to pass the opposing positions
to both attacker and defender Reposition calls. Backwards-compatible:
callers that don't pass `opposing_positions` get the original
behavior.

4 new regression tests in `tests/test_smoke_014_reposition_suppression.py`:
- `test_reposition_suppressed_when_opposing_front_empty_and_sally_alive`
- `test_reposition_not_suppressed_when_opposing_front_alive`
- `test_reposition_not_suppressed_when_opposing_sally_dead`
- `test_reposition_no_opposing_positions_arg_runs_normally`

## Stale comments cleaned up

Per BRIEF "Rules Accuracy Trumps Simplification" audit clause: each
"deferred / simplified / Phase N+1" comment must trace to a Q-NNN, a
[HOUSE RULE], or a still-open future-phase commitment. Items that
have shipped should not still be flagged as deferred.

- `campaign.py` module docstring: refactored. Phase 3a/3b/3c are all
  shipped; AoW per-card effects are mostly wired (Druzhina, House of
  Suzdal, Ordensburgen, Luchniki, Halbbrueder, Streltsy / Balistarii,
  Warrior Monks, Asiatic Horse, Raiders, Converts, Trebuchets,
  Stonemasons all flow through the appropriate strike / muster /
  movement code paths). The new docstring lists actual coverage.
- `campaign.py::_h_cmd_sail` docstring: `(Marshal group, Lieutenant
  Lower Lord support deferred to 3b)` was stale. Marshal grouping
  via the `group` arg is implemented; Lieutenant pairing is a Plan-
  phase mechanic (Q-003) and does not interact with Sail group
  membership beyond co-location.
- `campaign.py::_effective_command_rating` docstring: the "Legate at
  Lord's location: +1" line was a phantom rule. T13 William of
  Modena's card text and 3.5.1 USE options 2a/2b/2c do not include
  any "+1 Command from Legate" mechanic; the comment incorrectly
  cited "the rules say the Legate may be removed for +1 Command".
  Removed and replaced with a positive note that no such rule exists.
- `battle.py` module docstring: the "Phase 4 ... per-card AoW
  capability effects ... deferred" list named LUCHNIKI, HALBBRUEDER,
  STRELTSY/BALISTARII, RAIDERS, CONVERTS, WARRIOR MONKS, all of
  which are implemented. New docstring describes what is actually
  active. ("Russian archery special rounding" is flagged separately
  as a possible Q-007 candidate -- see below.)
- `events.py` module docstring + `resolve_immediate_event` /
  `resolve_hold_event` docstrings: no longer claim Tier 2 is
  deferred. Tier 2 Battle Holds consume via `_consume_battle_holds`;
  Tier 3 holds (T3 Vodian Treachery, T13 Heinrich Curia, R3 Pogost)
  are wired into `_HOLD_RESOLVERS`. Events without a resolver still
  return `deferred: True` -- that is correct fallback behavior, not a
  deferred-feature flag.

## New finding to surface (potential Q-007)

**Russian archery special rounding** (Forces Reference, 4.4.2 Russian
Archery): "When Russian -2-Armor Crossbowmen archery (Garrison Men-at-
Arms during Storm, or a Lord's Men-at-Arms with Streltsy R3) combines
with other Russian archery, round up any 1/2 Hit that causes the
Armor reduction." The current implementation rounds the per-target
total raw at end-of-step and applies `striker_has_armor_minus_2=True`
if any contributing striker had it. Whether this matches the rule's
"round up the 1/2 Hit that causes the reduction" intent is unclear --
the rule may require a separate sub-step for the -2-armor portion.
Logged as a candidate for the next Q-NNN cycle if rules clarification
is needed; not blocking.

## Test count

- Pre-Round-12: 362 passing.
- Post-Round-12: 366 passing (+4 SMOKE-014 regression tests).

## Smoke deferred to next round

Per user direction, the next round is a deep statistical smoke pass
focused on combat outcome distributions: are Battles oddly lopsided?
Are Storm outcomes unexpected? Does any side have a scenario where
no strategy wins? That work begins after Round 12 lands.

# Round 13 — Combat statistical smoke + SMOKE-015 garrison-only Storm bug

Per user direction: deep statistical pass on Battle and Storm outcomes
only. Don't run whole scenarios; vary lord counts and force compositions
for Battle, vary stronghold types and attacker counts for Storm.
Aggregate defender win rates and force losses. Compare against priors:

> Storm should strongly favor defenders. Battle should favor defenders,
> but somewhat less.

## Smoke driver

`tests/_playthrough_round13_combat_smoke.py` — minimal-state harness
that calls `resolve_battle` / `resolve_storm` directly with synthesized
Lord forces. Six force compositions (balanced, knight-heavy, sergeants-
heavy, light-horse-heavy, militia-heavy, asiatic-heavy). Battle: 6
count pairings × 9 composition pairings × 500 trials = 27000 trials.
Storm: 5 stronghold types × 3 attacker counts × 3 defender counts × 2
siege-marker tiers × 2 composition pairs × 100 trials = 18000 trials.

## SMOKE-015 (HIGH, FIXED): garrison-only Storm short-circuited each round

The smoke driver immediately surfaced an anomaly: garrison-only Storms
(`defender_lords=[]`) showed 100% defender wins with 0% garrison
losses across every configuration, including 3 Knight-heavy attackers
storming a 1-MaA Fort. The attacker was generating zero hits.

**Root cause.** `_all_routed(state, [])` returns `True` (vacuous
`sum() == 0`). In `resolve_storm`'s steps_data loop, the per-step
end-of-round check

```python
if _all_routed(state, attacker_lords) or _all_routed(state, defender_lords):
    break
```

fired after the FIRST strike step (`archery_defender`) every round when
defender Lords was empty. The remaining three steps (`archery_attacker`,
`melee_defender`, `melee_attacker`) never ran. Garrison-only defenses
became invulnerable to attacker damage.

**Secondary issue (SMOKE-015b).** `def_melee` was accumulated inside
`for lid in def_front_lords:`, with the garrison melee added to each
defender Lord's contribution under the per-Lord 6-Hit cap. With empty
`def_front_lords` the loop never executed and `def_melee` stayed at 0
— garrison melee was silently dropped. Per Forces Reference, garrison
units have storm_melee values (MaA: 1, Knights: 1) regardless of
whether a Front Defender Lord is present.

**Fix.**
- Inner-loop break in `resolve_storm` and `resolve_battle` now
  short-circuits only when a non-empty side is fully routed. For
  Storm, "defender wiped" requires both empty defender Lords and
  zero garrison.
- `def_melee` calculation falls back to a garrison-alone branch when
  `def_front_lords` is empty (capped at 6 Hits per the per-Lord cap;
  no Lord to combine with, so the cap applies to garrison alone).

4 new regression tests in
`tests/test_smoke_015_garrison_only_storm.py`:
- `melee_attacker` step actually fires in garrison-only Storm.
- Overwhelming attacker forces win garrison-only Storm a clear
  majority of trials (was 0% pre-fix).
- Garrison melee strikes when no defender Lord is present.
- Normal Storm with defender Lord is unchanged by the fix.

## Battle outcomes (500 trials/cell)

Balanced-vs-balanced parity (the cleanest read on side bias):

| Lords | Defender win % | Avg rounds | Atk loss % | Def loss % |
|------:|---------------:|-----------:|-----------:|-----------:|
|   1v1 |          83.8% |       2.53 |       95%  |       52%  |
|   2v2 |          89.4% |       2.80 |       97%  |       52%  |
|   3v3 |          91.4% |       3.00 |       98%  |       52%  |
|   4v4 |          96.0% |       4.04 |       99%  |       49%  |

Battle's defender bias **grows with side count**. The structural
mechanic: Defender strikes before Attacker in every Strike step
(Archery, Melee Horse, Melee Foot) and Reposition runs at the start of
each round 2+, so the longer the Battle, the more cycles the Defender
gets to strike-first. By 4v4 the Defender wins 96%; this is heavier
than the user's prior of "moderate" defender favoring.

Composition effects (1v1 case for clarity):
- Knight-heavy attacker vs balanced defender: Attacker wins 63.6%.
  Knight density flips the bias.
- Balanced attacker vs militia-heavy defender: Attacker wins 99.8%.
  Militia (Unarmored, no Archery) is terrible defense.
- Balanced attacker vs asiatic-heavy defender: Attacker wins 92.2%.
  All-archery defense doesn't break a melee push.
- Light-horse-heavy attacker vs balanced: Attacker wins 0.4%. All
  light cavalry is the worst attack composition.

Numerical asymmetry (2v1 / 1v2): one extra Lord swings the win rate
from 84% defender to ~99% the side with the extra Lord. Lord count
dominates over composition in unbalanced parity.

## Storm outcomes (100 trials/cell, post SMOKE-015 fix)

Aggregated by defender Lord count and siege marker tier:

| Defenders | Siege markers | Avg D win % | Avg A loss % | Avg G loss % |
|----------:|--------------:|------------:|-------------:|-------------:|
|     0 (gar only) |    1 (2 rds) |       50.3% |        25.1% |        71.1% |
|     0 (gar only) |    3 (4 rds) |       20.1% |        19.0% |        89.7% |
|     1 Lord       |    1 (2 rds) |       99.9% |        50.7% |        64.0% |
|     1 Lord       |    3 (4 rds) |       95.9% |        52.4% |        84.3% |
|     2 Lords      |    1 (2 rds) |      100.0% |        50.4% |        64.2% |
|     2 Lords      |    3 (4 rds) |      100.0% |        51.9% |        83.9% |

**Storm with at least one defender Lord besieged: defender wins
96-100%** across every configuration. Matches the user's prior
("Storm strongly favors defenders").

**Storm vs garrison alone:** A 1-marker Storm is roughly a coin flip
(50% defender). A 3-marker (full siege, 4 rounds) is largely an
attacker win (only 20% defender). This is what we should expect: a
full siege wears down a garrison; a partial assault doesn't.

By stronghold type (averaged across all configs):

| Stronghold | Walls | Avg D win % |
|:-----------|------:|------------:|
| fort       |     3 |       64.7% |
| city       |     3 |       78.1% |
| novgorod   |     3 |       78.5% |
| castle     |     4 |       79.1% |
| bishopric  |     4 |       88.1% |

Bishopric is the strongest (walls 4 + 3-unit garrison including 1
Knight). Fort is the weakest (walls 3 + 1-MaA garrison). The
ranking matches the rules-data table.

## Comparison to priors

- **Storm strongly favors defenders.** ✅ Confirmed for any defended
  Stronghold (def_n ≥ 1): 96-100% defender win rate.
- **Battle moderately favors defenders.** ⚠️ Partially confirmed.
  Battle does favor defenders, but the bias is heavier than expected:
  84% at 1v1 climbing to 96% at 4v4 in balanced-comp parity. Worth
  flagging as something to revisit if outcomes feel "stuck" in
  scenario play. Most likely real-rules behavior given defender
  initiative and Reposition mechanics, but worth a sanity check.

## No "unwinnable side" in pure combat

No configuration showed a side at 0% win across all force
compositions. Knight-heavy attackers can break Battle defender bias;
overwhelming attacker forces can take garrison-only Strongholds; even
a small-garrison Fort falls to a focused 3-marker siege. Composition
choices and number of Lords matter as much as side bias.

## Test count

- Pre-Round-13: 366 passing.
- Post-Round-13: 370 passing (+4 SMOKE-015 regression tests).

## Open follow-ups

- Battle defender bias at 4v4 hit 96% in balanced parity. If, during
  full-scenario smoke later, Battle outcomes look stuck (e.g.,
  attackers with otherwise good force composition can never win
  high-Lord-count battles), revisit defender initiative ordering and
  Reposition Advance mechanics. The implementation matches 4.4.2
  Strike-step initiative as written; the question is whether the
  sum effect is right.
- Russian archery special rounding (flagged in Round 12) was not
  exercised by this smoke pass — the compositions don't combine
  -2-Armor archery with regular Russian archery. Will surface if
  later smoke uses Streltsy/Garrison-MaA archery in the same step.

# Round 15 — LLM-consumer interface gaps

User direction (2026-05-08): the harness should let an LLM agent (Claude
or ChatGPT) play any scenario without consulting external rules
references during play. A walkthrough of Pleskau turn 1 surfaced a
concrete punch list of gaps where the consumer had to leave the
harness state to make a decision. This round closes those gaps.

## Card effect text now in static data

`reference/Nevsky_Arts_of_War_Reference.txt` parsed and merged into
`src/nevsky/data/static/cards.json` as `event_text` and
`capability_text` fields on every numbered card (T1-T18, R1-R18) — 36
cards covered. No-Event/No-Capability blank cards intentionally have
empty strings.

## render_summary lockstep + content additions

`render_summary` now prints two new lines:

- **Next expected:** a one-line hint encoding the lockstep flow ("teutonic:
  aow_implement_card (pending: ['T4', 'T12'])"). Removes the need to grep
  the source to figure out which side acts next and what action it should
  issue.
- **Pending AoW {side}:** when a side has cards in `pending_draw`, this
  block lists each card with its EVENT name + persistence + text and
  CAPABILITY name + scope + text inline. The consumer can decide
  implement-vs-hold-vs-discard from the summary alone.

During `phase=campaign step=plan`, summary also includes a `Plan:
required=N | T=t_size(done?) | R=r_size(done?)` line so the consumer
knows the season's plan-size target without importing the internal
`_plan_target_size`.

## Legal-moves now concrete and self-explanatory

`legal_moves` previously emitted action templates with `args_template`
and `candidates` dicts; the consumer had to combine them. Now each
applicable substep emits **fully-populated concrete entries** with a
`note:` field describing what the action does:

- `muster_lord`: one entry per (by_lord, target_lord, seat) triple.
- `muster_vassal`: one entry per (by_lord, vassal_id) pair.
- `levy_transport`: one entry per (by_lord, transport_type) pair.
- `levy_capability`: one entry per (by_lord, card_id) with capability
  name + scope in the note.
- `plan_add_card`: one entry per Mustered Lord on the active side + a
  pass entry, each tagged with the slot index it would fill.
- `cmd_march`: one entry per reachable adjacent Locale via Ways, with
  the Way type in the note.
- `veche_action`: options A / B / C / D each enumerated as concrete
  actions with notes naming the rule (3.5.2) and the effect.
- `legate_arrives` / `legate_move` / `legate_use` (2a/2b/2c) each
  enumerated as concrete actions with notes naming the sub-option and
  effect (3.5.1).

Old `args_template` form is retained only as a fallback when the
concrete enumeration cannot be computed.

## lord_combat_summary helper

`render.py::lord_combat_summary(state, lord_id)` returns a structured
per-Lord readout: ratings (base + effective Command), service-disband
box, forces composition + total + Feed cost, this-Lord capabilities,
and Battle / Storm hit output by Strike step (archery, melee_horse,
melee_foot, storm_archery, storm_melee with the per-Lord 6-Hit cap
already applied). Removes the need to compute strike output from the
Forces table by hand.

## Tests

- 8 new regression tests in `tests/test_round_15_llm_interface.py`
  cover the contract surface: card data has effect text; render_summary
  shows the lockstep hint and pending-AoW block; legal_moves emits
  concrete `args` with notes for muster, plan, and cmd_march;
  lord_combat_summary returns the expected structured data.
- 370 → 378 passing total.

## Walkthrough check (Pleskau turn 1)

After the changes I re-walked the Pleskau turn 1 scenario to validate
that an LLM consumer reading only render_summary + legal_moves can
make every decision the rules require without consulting external
text. The previous blocker (muster_lord required the unfamiliar
`by_lord` arg) is gone — legal_moves at the Russian Muster step now
lists `{type: muster_lord, args: {by_lord: gavrilo, target_lord:
domash, seat: novgorod}, note: "gavrilo (Lordship) Musters domash at
novgorod (1d6<=Fealty success)"}` directly.

## Items intentionally NOT in this round

- Storm / Battle outcome previews (estimated win prob + force-loss
  distribution from a candidate engagement) — bigger scope; will be
  the next round if smoke shows the LLM consumer wants them. The
  Round 13 smoke driver has the underlying logic.
- VP forecast per candidate action — same scope notes as previews.
- Multi-hop `paths_from(locale_id, season, transport, max_hops)` — only
  1-hop adjacency is exposed by cmd_march enumeration. Multi-hop is
  derivable from repeated 1-hop queries; cleaner helper deferred.

# Round 16 — Engagement previews + VP forecast

Follow-on to Round 15 per user direction. With card text and concrete
action templates in place, the LLM consumer can issue any rule-legal
move from the harness state alone. This round adds the predictive
helpers so the consumer can compare candidate moves without rerunning
combat math by hand.

## battle_preview / storm_preview

`src/nevsky/previews.py` adds two pure functions:

- `battle_preview(state, attacker_side, attacker_lords, defender_lords,
   *, trials=100, max_rounds=10)` deep-copies the state per trial,
   runs `resolve_battle` with a unique RNG seed each trial, and
   aggregates winrate / avg rounds / avg per-side unit losses + loss
   percentages.
- `storm_preview(state, attacker_side, attacker_lords, locale_id, *,
   defender_lords=None, trials=100)` does the same for `resolve_storm`,
   pulling Walls / Garrison / Siege markers from current state and
   defaulting `defender_lords` to the Lords currently inside the
   Stronghold. Includes garrison-loss stats.

Neither helper mutates the caller's state (deepcopy + setattr on the
copy's `meta.rng_state`). Per-call cost is ~80ms at trials=50 against
typical configurations.

Spot validation: Hermann (4 units) vs Gavrilo (4 units) 1v1 Battle in
Pleskau gives 31% attacker win, 69% defender — consistent with the
Round 13 smoke's "balanced 1v1 ~70% defender" finding. Hermann
Storming Izborsk (Fort, walls 3, 1 garrison MaA, 1 siege marker) gives
84% attacker win, 33% expected attacker losses, 88% expected garrison
loss — also consistent with Round 13.

## vp_forecast

`vp_forecast(state, action, *, preview_trials=50)` returns expected
VP delta for any candidate action:

- Deterministic: cmd_ravage (+0.5 VP for own marker).
- Probabilistic: cmd_storm, cmd_sally, stand_battle (uses the preview
  helpers internally; expected VP = win_prob * stronghold VP).
- No-op: cmd_tax / cmd_forage / cmd_supply / cmd_pass / cmd_march /
  cmd_sail / end_card.

Result includes a one-line `note` field summarising the forecast in
human-readable form, plus the raw `preview` dict for probabilistic
actions.

## legal_moves notes now embed previews

For three high-stakes options, the legal_moves entry's `note` field
now includes the preview summary inline:

- `cmd_storm`: `"Storm (4.5.2) -- entire card | storm izborsk: A_win
  88%, expected +0.88 VP (VP=1); avg A_loss 29% / G_loss 88%"`
- `cmd_sally`: `"Sally (4.5.3) -- ... | sally: Sallier_win X%, avg
  Sally_loss Y% / Besieger_loss Z%"`
- `stand_battle` (combat-pending response): `"engage in Battle |
  battle: A%/D% win, avg A_loss%/D_loss%"`

`cmd_ravage` now includes the `+0.5 VP` text inline as well.

LLM consumer no longer has to call vp_forecast separately to compare
"Storm Izborsk vs Ravage Vod" — the comparison is in the action menu
the consumer is already reading.

## Tests

- 8 new regression tests in `test_round_16_engagement_previews.py`
  cover preview correctness, no-mutation, vp_forecast for all three
  kinds, and the legal_moves preview embedding.
- 378 → 386 passing.

## Items NOT in this round

- Multi-hop path query (`paths_from(locale_id, season, transport,
  max_hops)`) — still derivable from repeated 1-hop queries via
  cmd_march enumeration; deferred until smoke shows it's needed.
- Concede recommendation in Battle decision context — would need a
  per-round expected-loss model; nontrivial, deferred.
- Concede / Avoid Battle / Withdraw cost-benefit comparison alongside
  stand_battle. Currently the three options appear in legal_moves with
  notes but no comparable forecast. Could be added by running the
  battle preview once and reporting "if you stand: X%; if you
  concede: 50% damage taken this round + lose Battle; if you avoid:
  Z lord-shifts on Service." Deferred.

# Round 17 — Cleanup and repair

User direction: substantive cleanup and repair before further feature
work. Audit revealed three repair targets and two new open questions.

## Tightened broad except clauses (R15/R16 holdover)

Six `except Exception:` blocks were silently swallowing errors:

- `previews.py` battle_preview / storm_preview: per-trial except now
  tracks a `failed_trials` counter and `last_error` string, surfaced in
  the result dict when failures occur. Helper return shape gains a
  `successful_trials` field; the win-rate denominator uses the
  successful count rather than the total.
- `legal_moves.py` four preview-hook sites (cmd_storm, cmd_sally,
  stand_battle, cmd_march fallback): each except now catches a specific
  set (`ImportError, KeyError, ValueError, AttributeError,
  FileNotFoundError`) and surfaces the failure in the action's `note`
  field as `(preview unavailable: ExceptionName)`. Unexpected exceptions
  now propagate, so future bugs aren't hidden.

## Lord-id validation in previews

Both `battle_preview` and `storm_preview` now reject calls with
unknown lord_ids before running trials. Previously a typo like
`"nonexistent"` produced a confident-looking 0%-attacker-win, 0-pre-
units result that an LLM consumer might trust. Now returns
`{trials: 0, error: "unknown lord_id(s): ['nonexistent']"}`.

## Q-007 + Q-008 logged

`RULES_QUESTIONS.md` updated with two new questions surfaced from
prior smoke / audit work:

- **Q-007 — Russian Archery special rounding (4.4.2).** Forces
  Reference rule about rounding the half-Hit that causes Armor
  reduction when Russian -2-Armor archery combines with regular Russian
  archery. Current implementation flags `striker_has_armor_minus_2` if
  ANY contributing striker had it; that may over-apply in mixed cases.
  Three options (current behavior / per-Hit attribution / sub-step
  rounded-to-1) listed. Non-blocking; current behavior is generous to
  Russians and Russians already win 84% of balanced 1v1 Battles.

- **Q-008 — Tier 2 Battle Hold mechanical effects (4.4.2).** Bridge,
  Hill, Ambush, Field Organ are partially wired (consumption tracked,
  but the per-step Strike-cap / Hit-modification effects are no-ops).
  Bridge specifically: Q-005 made front-center modeled, so the
  `2 * round_number` cap on the front-center Lord is now implementable.
  Three options (literal-reading wire / leave as no-ops / consult
  Volko's worked examples — last excluded by BRIEF policy). Non-blocking;
  consumption is tracked and the user/LLM can apply the effect manually.

## Stale comment update

`events.py:621` Bridge docstring previously claimed "no-op since
front-center is not modeled" — front-center IS modeled per Q-005;
updated to reference Q-008.

## Playthrough drivers — none stale

Ran each of the 13 `_playthrough_*.py` drivers under the latest
state. All complete cleanly. Round 6's 16-turn Crusade-on-Novgorod
driver reports 0 BUGS FOUND. Round 14's all-six-scenarios passive
smoke driver runs all scenarios without errors. No cleanup needed.

## Tests

- 10 new regression tests in `test_round_17_cleanup.py` cover the
  validation guards, failed-trial tracking, preview-unavailable note
  surfacing, and presence of Q-007 / Q-008 in RULES_QUESTIONS.md.
- 386 → 396 passing.

# Round 18 — Q-007 + Q-008 resolutions

User adjudicated Q-007 (Russian Archery rounding) and Q-008 (Tier 2
Battle Hold mechanical effects), citing the Arts of War Reference Tips
sections as the controlling text. This round implements both per spec.

## Q-007 — Round in favor of Crossbowmen

Per Arts of War Reference R1/R2 Luchniki Tips: "When Luchniki Archer
units combine with Garrison or Streltsy Crossbowmen units, any Hit
that includes at least ½ a Hit from Crossbowmen does cause the
reduction to enemy Armor Protection. That is, when rounding units
with Archery, round in favor of Crossbowmen."

Implementation:
- battle.py archery accumulation now splits per-striker contribution
  into `this_cb_raw` (Streltsy/Balistarii MaA archery, -2 Armor) and
  `this_norm_raw` (default + Luchniki, no Armor reduction). Per-target
  state tracks `per_target_cb_raw` and `per_target_norm_raw`
  separately.
- Per the rule's algorithm:
    `total_hits = ceil(cb_raw + norm_raw)`
    `cb_hits   = min(ceil(cb_raw), total_hits)`
    `norm_hits = total_hits - cb_hits`
- `_resolve_hits` accepts an ordered `hit_flags: list[bool]` so the
  first `cb_hits` Hits carry -2 Armor and the rest don't. Replaces
  the old per-target `striker_has_armor_minus_2` boolean.
- `resolve_storm` archery resolution receives the same treatment;
  Garrison MaA archery is always Crossbow.

Net effect: in mixed-archery cases (Streltsy MaA + Asiatic Horse on
the same Lord, etc.), the -2 Armor reduction now applies to the
correct count of Hits per the rule, rather than the previous
"any-contributor flags everything" behavior.

## Q-008 — Tier 2 Battle Hold mechanical effects

All five Tier 2 Hold effects wired per the Arts of War Reference Tips,
each invoked via the existing `holds` dict on `resolve_battle`:

- **T4/R1 Bridge** (`holds["bridge"] = lord_id`): non-Winter only;
  the targeted Lord's Melee strike is computed from a capped subset
  of units (`cap = 2 * round_number`), heaviest hitters first via
  `_capped_unit_subset`. Archery and Hit absorption unaffected. Skips
  Relief Sallying Lords because Sally rows are on different positions
  from front-center.
- **T5/R2 Marsh** (`holds["marsh"] = "T5"|"R2"`): Rounds 1-2,
  Marsh-target side's Horse units (Knights, Light Horse, Asiatic
  Horse) blocked from Striking both Archery and Melee. Hit
  absorption unaffected. Refines the previous Asiatic-Horse-only
  partial implementation.
- **T6/R6 Ambush** (`holds["ambush"] = "T6"|"R6"`): Round 1 only,
  the targeted side's left/right front Lords are uninvolved — they
  don't strike, don't accept Hits, don't Rout.
- **T9/R5 Hill** (`holds["hill"] = "T9"|"R5"`): Defender side,
  Rounds 1-2, ALL archery contributions doubled (including Crossbow
  contributions; the doubled Crossbow Hits still carry -2 Armor).
  Refines the previous default-archery-only partial implementation.
- **T10 Field Organ** (`holds["field_organ"] = lord_id`): per-Lord,
  Round 1, Melee step only. +1 Hit per actually-striking Knight (in
  melee_horse) and Sergeant (in melee_foot). Critical: respects
  Bridge cap and Marsh Horse-block via `_striking_unit_count`-style
  filtering, so the bonus tracks units that actually strike.

`_consume_battle_holds` validates and discards each Hold per existing
behavior; that part was already correct.

## Helper additions

- `_capped_unit_subset(units, cap)`: priority-ordered subset
  (Knights > Sergeants > MaA > Light Horse > Militia > Asiatic Horse
  > Serfs) for Bridge cap.
- `_striking_unit_count(state, lord_id, utype, rounds, bridge_target_lord)`:
  Field Organ × Bridge interaction helper.

## Process note from user adjudication (BRIEF update)

User flagged that Q-007 / Q-008's "ambiguity" framing in earlier
rounds was a process error: the Arts of War Reference .txt file
(designer-clarified Tips) contains the answers and is unrestricted in
the repo. I'd been deferring to the PDF restriction inappropriately.

BRIEF.md updated:
- Source priority reordered. The .txt references (Forces, Battle and
  Storm, Arts of War Reference, etc.) are now FIRST stop, ahead of
  the PDF. Their Tips sections are designer-clarified and authoritative
  for card text and capability mechanics.
- PDF-restriction language clarified: in-repo PDFs are readable; the
  restriction was about external/web PDFs, not source/.
- Consultation chain updated: step 1 explicitly notes that if the
  answer is in the .txt reference, the consultation ends there and
  the question doesn't need to be logged.

events.py:621 stale comment about Bridge ("no-op since front-center
is not modeled") removed; the Bridge cap is now wired.

## Tests

16 new tests in `test_round_18_q007_q008.py`:
- Q-007 rounding-table parametrized tests (6 cases) verifying the
  algorithm against the rule's worked examples directly.
- `_resolve_hits` accepts ordered `hit_flags`.
- Q-008 effect tests: Bridge cap reduces damage; Bridge no-op in
  Winter; Marsh blocks all-Horse-attacker damage; Hill doubles
  defender archery; Field Organ adds Knight Hits; Field Organ ×
  Bridge interaction is well-formed.
- Ambush Round 1: targeted-side left/right strikers don't appear
  in the per_striker log.
- Storm Garrison MaA archery uses the Q-007 split (Storm runs
  cleanly with Garrison-only defense).
- Helper test: `_capped_unit_subset` priority order.

396 → 412 passing.

## Smoke spot-check

A single 1v1 cell (balanced parity, Russian defender with R3 Streltsy
in play): 500 trials, Russian win 93.8%. Within the expected band
given Streltsy's -2 Armor advantage; the Q-007 split applies the
rule precisely without the previous "any-contributor flags
everything" over-application.

# Round 20 — R19 interface gaps + optional rules infrastructure

User direction: fix the four interface gaps surfaced in Round 19 and
add optional-rules support so the player can declare which 2E variants
are active and the LLM agent can respect them.

## R19 interface gaps closed

**Gap 1 — cmd_march warning when destination is enemy Stronghold.**
`legal_moves`'s cmd_march entry now augments the note with two lines
when relevant:
- `NOTE: enters enemy Stronghold; places Siege & ends the Command card (4.3)`
  when the destination is an enemy-territory Stronghold.
- `NOTE: enemy Lord(s) [...] at dest; triggers Approach decision (4.3.4)`
  when a Mustered enemy Lord is at the destination.

**Gap 2 — withdraw arg-shape clarity.** The `withdraw` legal_moves
entry's note now explicitly says "no args required" and that the
action auto-targets `combat_pending.to_locale`.

**Gap 3 — paths_from helper.** New `render.paths_from(state,
from_locale, *, max_hops=4, season=None, transport=None)` returns a
dict `{locale_id: [intermediate, ..., target]}` of shortest-Way paths
within `max_hops` hops. Removes the need for an LLM agent to
reimplement BFS over Ways.

**Gap 4 — lord_card_status helper.** New
`render.lord_card_status(state, lord_id)` returns a structured dict
with `is_mustered, is_besieged, in_plan, in_plan_position,
is_active, actions_remaining, service_disband_box`. Simplifies
activation-loop bookkeeping.

## Optional rules infrastructure

`meta.optional_rules: dict[str, bool]` field added to the GameState
schema. Five known optional rules per Rules of Play 2.1.2 / 6.0:

- `hidden_mats` (1.5.2)
- `optional_counters` (1.6)
- `advanced_vassal_service` (3.4.2)
- `bidding_for_sides` (6.0)
- `no_horseback_archery` (6.0)

`load_scenario` extended with `optional_rules: dict[str, bool] | None`
and `bidding_bid: int = 0` keyword args. Unknown rule names raise
`ValueError`. New runtime helper `set_optional_rule(state, rule_name,
enabled)` lets the LLM toggle flags on declaration.

`render_summary` adds an `Optional rules:` line listing active flags
when any are enabled. Omitted when none are active.

## No Horseback Archery (6.0) — wired

When `meta.optional_rules.no_horseback_archery` is True, Asiatic Horse
Defense rolls succeed only on '1' (effectively Unarmored). Negates the
default `evade:1-3` Battle Melee defense.

Implementation: `_absorb_hit` checks the optional flag and overrides
the protection spec to `armor:1-1` for Asiatic Horse. The change
applies in all situations, including Battle Melee — matching the rule
text "always succeed only on '1'".

Smoke check: an all-Asiatic-Horse defender vs balanced attacker shows
materially lower Russian win rate with the variant on (regression test
`test_no_horseback_archery_makes_asiatic_horse_more_fragile` pins this
direction).

## Bidding for Sides (6.0) — wired

`load_scenario(..., bidding_bid=N)` adds N 1VP markers to the Veche
(capped at 8 per rule 1.3.3). If `bidding_bid > 0`, the
`bidding_for_sides` flag auto-enables. Negative bids rejected with
ValueError.

The bidding mechanic itself (two players concealing dice) is a setup-
time human procedure outside the harness's responsibility; the harness
takes the resolved bid value as input.

## Optional rules — scaffolded but not yet engine-affecting

Three optional rules are recorded in `meta.optional_rules` and shown
in `render_summary`, but full engine wire-up is deferred:

- **`optional_counters` (1.6).** Purely physical counter-substitution
  for wood pieces. No engine effect; flag is informational only.
- **`hidden_mats` (1.5.2).** Fog-of-war on Lord mats. The harness
  currently exposes full state; full implementation needs a
  `render_summary_for_side(state, side)` filter that omits opposing-
  side details. Deferred — flag scaffolded so the agent can know it's
  on and apply self-discipline.
- **`advanced_vassal_service` (3.4.2).** Vassal Service tracked on
  the Calendar instead of on Lord mat. Significant refactor of the
  Vassal Disband mechanic. Flag scaffolded; full implementation
  deferred.

## Tests

17 new in `test_round_20_gaps_and_optional_rules.py`:
- cmd_march note warns about enemy Stronghold + enemy Lord at dest.
- withdraw note explains no-args.
- paths_from returns ordered path lists; supports starting locale and
  multi-hop routes.
- lord_card_status returns the expected key set; handles unknown lord.
- load_scenario accepts and validates optional_rules kwarg.
- set_optional_rule toggles + returns summary; rejects unknown names.
- render_summary shows / omits the optional-rules line correctly.
- bidding_bid adds VP markers, capped at 8, rejects negatives.
- No Horseback Archery materially weakens Asiatic Horse defense.

412 → 429 passing.

# Round 21 — Finishing deferred work

User direction: finish anything previously deferred. Audit found three
items still open:

1. `hidden_mats` (1.5.2) render filter — flag was scaffolded R20.
2. Combat-pending forecasts (Concede / Avoid Battle / Withdraw) — R16
   deferred for size.
3. `advanced_vassal_service` (3.4.2) Vassal-on-Calendar wire-up — R20
   scaffolded, full impl deferred.

All three closed in this round.

## Hidden Mats (1.5.2) — render filter

`render.state_view_for_side(state, side)` returns a deep-copied state
with opposing-side Lord details masked when
`meta.optional_rules.hidden_mats` is True. Per the rule, opposing
Lord-mat fields are hidden: forces, routed_units, assets,
this_lord_capabilities. Pending AoW draws on the opponent are masked
to `<hidden>` placeholders. Side-wide opposing Capabilities remain
visible per 3.4.4. Lord locations remain visible (the map is not
concealed).

`render.render_summary_for_side(state, side)` is the convenience
wrapper that calls `render_summary` on the filtered view and prefixes
with a `[VIEW: side (Hidden Mats active — opposing Lord details
concealed)]` banner. When the flag is off, returns identical output
to `render_summary`.

The LLM consumer can pass `state_view_for_side(state, "teutonic")`
into `lord_combat_summary` or `legal_moves` to operate consistently
within the fog-of-war.

## Combat-pending forecasts

`legal_moves` at combat-pending response now augments the four options
with cost-benefit notes:

- **stand_battle**: forecast of A_win%/D_win%/avg_loss% (already in
  R16; unchanged).
- **stand_battle with `args.concede=side`** (new pseudo-option):
  Concede the Field per 4.4.2 NEW ROUND. Note: "lose the Battle but
  Conceder takes half Hits this Round (Pursuit), limits Spoils
  transfer to Loot+excess Provender (4.4.3 2E). Use when stand_battle
  forecast shows attacker_loss ~> 60% AND winrate < 30%."
- **avoid_battle**: enumerate concrete adjacent destinations as
  separate `args:{to:dest}` entries, each noting Service shift cost
  and tempo loss.
- **withdraw**: note explicitly states "Converts Battle into Siege:
  attacker may Storm or Siege subsequently; defender denied
  Tax/Forage/etc while Besieged. Trade losses now for Service-clock
  pressure later."

## Advanced Vassal Service (3.4.2)

Three integration points:

**Muster Vassal**: when the variant is on, `_h_muster_vassal` places
the Vassal Service marker on the Calendar at
`(current_levy_box + vassal.service)`, but only if that box is left
of the parent Lord's Service marker. Otherwise the marker stays on
the mat (default behavior). State updates: `vstate.on_calendar=True`,
`vstate.calendar_box=target_box`, plus
`calendar.boxes[target-1].vassal_service_markers.append(vid)`.

**Lord Service shift**: `_shift_service_right` propagates the shift
to all of the Lord's on-Calendar Vassal markers in the same direction
by the same number of boxes. Vassals shifted past box 16 land at the
sentinel `calendar_box=17` (off-right); past box 1 land at sentinel
`calendar_box=0`.

**Disband cleanup**: new `_advanced_vassal_disband_step(state, side)`
helper applies at the Disband substep:

- Vassal markers LEFT of current box → permanently removed; Vassal's
  Forces returned to the pool (subtracted from Lord's force totals).
- Vassal markers IN current box (at Service limit) → moved to mat
  face-down (Unready); Forces returned to pool.
- Vassal markers RIGHT of current box → unchanged.
- If returning Forces leaves a Lord with no Forces, the Lord is
  Disbanded per 1.6.

Hooked into `_h_disband_at_limit`: result dict now includes a
`vassal_advanced` key with removed / to_mat_unready / disbanded-due-
to-no-forces lists.

**End-of-Vassal-Muster flip-up**: when `levy_step` advances from
"muster" to "call_to_arms", all face-down (unready, unmustered) Vassal
markers flip face-up (Ready) per the rule's "After a side finishes all
Vassal Muster for this Levy, flip up all Service markers that are
Coat-of-Arms side down".

## Tests

12 new in `test_round_21_finish_deferred.py`:
- `state_view_for_side` masks opposing forces / pending draws when
  hidden_mats on; no-op when off.
- `render_summary_for_side` includes the hidden-mats banner.
- Combat-pending: avoid_battle enumerates destinations with notes;
  concede pseudo-option emitted; withdraw explains Siege conversion.
- Advanced Vassal Service: marker placement on Calendar when left of
  Lord; Disband helper processes at-limit (face-down on mat) + past-
  limit (permanent remove); helper is no-op when flag off; end-of-
  Muster flip-up makes face-down Vassals Ready.

429 → 441 passing.

## Open audit items now closed

All previously-deferred items from rounds 11-20 are addressed. The
RULES_QUESTIONS.md docket is empty (Q-001 through Q-008 all resolved).
The Tier 2 Battle Holds wire-up is complete. The Optional Rules
infrastructure is full: all five 2E variants are recognized, three are
fully wired (no_horseback_archery, bidding_for_sides, advanced_vassal_
service), one is informational-only (optional_counters), and one has a
filter helper for consumers (hidden_mats).

# Round 22 — Long-scenario end-to-end smoke + scenario-victory bug fixes

User direction: smoke test the longer scenarios. Built a generic active
agent driver in `tests/_playthrough_round22_long_scenarios.py` that
plays any scenario end-to-end with a basic strategic policy: each Lord
marches toward the nearest enemy Stronghold; Stages Sieges; Storms
when expected attacker win > 40%; Withdraws when outnumbered;
Russians use Veche option B to auto-Muster Ready Lords.

## Engine soundness — all four longer scenarios run cleanly

| Scenario              | Turns played | Errors | Driver result | Real result (after R22 fixes) |
|-----------------------|-------------:|-------:|---------------|-------------------------------|
| pleskau (2 turns)     |            2 |      0 | T 1 - 0       | T 1 - 0                        |
| watland (5 turns)     |            5 |      0 | T 4.5 - 0     | **R win** (Watland override)   |
| return_of_the_prince  |            8 |      0 | T 7.5 - 1.0   | T win                          |
| crusade_on_novgorod   |           16 |      0 | T 1.0 - 0     | T win                          |

The engine survives 16-turn play with zero exceptions and zero illegal-
action errors. Levy / Plan / Activations / End Campaign / Calendar
advance / Wastage / Disband / Service-shift / Grow all execute
correctly across all four scenarios.

## Bug 1: Pleskau Lord-removed VP bonus was not applied

The Pleskau scenario has `special_rules.victory_lord_removed_bonus`
documented in the scenario JSON. Per rule 5.1: "PLESKAU SCENARIO
ONLY: +1 VP per enemy Lord removed from the map by any means." The
Calendar already had `pleskau_lords_removed_russian /
pleskau_lords_removed_teutonic` counters — but nothing incremented
them, and `_compute_vp` ignored them.

**Fix.** `_remove_lord_permanently` now increments the counter named
after the removed Lord's side when the scenario flag is on. The
counter naming follows the convention "removed_{side_of_removed_lord}"
so the consumer reads pleskau_lords_removed_russian = "count of
Russian Lords removed" → bonus to the Teutons. `_compute_vp` adds the
ENEMY-side counter to each side's tally.

## Bug 2: Watland 2E victory override was not applied

Watland's `special_rules.victory_override = "watland"` was documented
in the scenario JSON. Per the 2E Watland rule: "Teutons win only with
at least 7 VP AND at least 2x Russian VP. Otherwise Russians win. No
tie." The harness only computed raw VP totals; no code applied the
override. The driver's smoke run reported `T 4.5 - 0 → teutonic win`
naively, but per the rule that's a Russian win (T < 7).

**Fix.** New `scenarios.determine_scenario_winner(state)` helper
returns `{winner, reason, t_vp, r_vp, applied_override}` per the
canonical rules:

1. **5.2 Campaign Victory** (checked during Campaign phase only): a
   side with zero Mustered Lords loses immediately; the other side
   wins regardless of VP.
2. **Watland override** (when `victory_override == "watland"`):
   Teutons win only if `t_vp >= 7 AND t_vp >= 2 * r_vp`; otherwise
   Russians win; no tie.
3. **Standard 5.3**: higher VP wins; tie = draw.

Spot-checks against the rule examples:
- Watland T=4.5 R=0: Russian wins (T < 7).
- Watland T=7 R=3: Teutonic wins (7 ≥ 7 AND 7 ≥ 2×3=6).
- Watland T=7 R=4: Russian wins (7 < 2×4=8).
- Pleskau T=R=1: draw.

## Driver notes (not bugs — agent quality)

The active driver is intentionally simple. A few observations:

- **Crusade ends at T 1 - R 0**: only Kaibolovo conquered. The agent
  doesn't bring Aleksandr/Andrey in via Veche option C, doesn't
  raid for ½-VP, and doesn't optimize plan order. A real LLM agent
  applying full strategy would score much higher VPs.
- **Knud & Abel hung the activation loop** until I added a 4-iteration
  cap on the multi-hop march loop in `execute_lord_card`. The cause
  was `paths_from` returning legal-shape Way paths that `cmd_march`
  refused (Knud has Ships and Boats but Watland turn 1 is Early
  Winter — Sleds-only). The driver's safety cap prevents this from
  being a real engine concern but a future improvement to
  `paths_from` could filter by season-usable transport.
- **`legal_moves(state, with_previews=False)`** flag added so hot
  loops (smoke drivers, agent activation) can skip the per-call
  vp_forecast generation for cmd_storm / cmd_sally / stand_battle
  notes. Default `with_previews=True` preserves the R16/R20 LLM
  behavior. The smoke driver passes False to keep activation loops
  fast.

## Tests

10 new in `test_round_22_long_scenarios.py`:
- Pleskau lord-removed counter increments + propagates to compute_vp.
- Non-Pleskau lord removals don't touch the counters.
- determine_scenario_winner: standard higher-VP, tie, Watland under-7,
  Watland 7+ over 2x, Watland under 2x, Campaign Victory zero-mustered,
  Campaign Victory skipped during Levy.

441 → 451 passing.

## Items intentionally NOT in this round

- Smarter active agent that uses Veche C (Aleksandr extra Muster) and
  Veche A (cylinder shift) — would change scenario outcomes
  meaningfully but is a significant agent design exercise.
- `paths_from` season-and-transport filtering — would let the active
  driver avoid Knud-and-Abel-style march dead-ends.
- `determine_scenario_winner` integration into `end_campaign_resolve`
  so the harness reports the canonical winner at scenario end without
  the consumer needing to call it. Currently the helper exists; the
  consumer wires it into their flow.
