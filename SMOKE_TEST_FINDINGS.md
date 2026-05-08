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
