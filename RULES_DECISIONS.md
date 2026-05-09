# Decision Log

Decisions are PERMANENT. Never delete an entry.

When the user adjudicates a question from RULES_QUESTIONS.md, MOVE the
entry here with:

- The user's answer (verbatim).
- Any rules citation provided.
- The commit hash where the answer is encoded.
- `[HOUSE RULE]` tag if the rules were silent on the question.

---

## Q-001 — Transport-(any) choice at scenario setup
*Adjudicated 2026-05-08. Encoded in commit (this PR).*

**User adjudication (verbatim):**

> Transport (any) — Setup Default & Override Spec
>
> Resolves: Q-001 (Transport-(any) choice at scenario setup,
> _build_lords).
>
> Purpose
> Several Lords' mats specify Transport x1 (any) or Transport x2 (any)
> — the player picks Boat / Cart / Sled / Ship at setup, subject to
> the Lord's "Ships" authorization (Rule 3.4.1). The harness needs a
> fully-populated GameState at scenario load and a clean way to let
> the player override.
>
> Approach (hybrid of options a + b)
>   - Loader computes a default per the heuristic below and writes
>     the concrete Transport pieces into the Lord's Assets. State is
>     internally consistent immediately after load.
>   - Loader also emits a setup_transport_choice PendingDecision per
>     "any" slot, with the default pre-populated as current_value.
>     This preserves player agency.
>   - Before the first Levy action for that side, the player may
>     accept defaults or override. Unresolved decisions auto-confirm
>     to the default at first Levy action and the PendingDecision is
>     removed.
>   - The two override hotspots (Vladislav at Neva; Aleksandr at
>     Novgorod in Summer scenarios) should explicitly ask the player
>     rather than auto-confirming. Everything else default-confirms.
>
> Heuristic (decision tree). Apply per "any" slot, in order; stop at
> first match.
>   1. Winter rule. Scenario start season is Early Winter or Late
>      Winter -> Sled for every slot. Per RoP 1.7.4, Sleds are the
>      only Transport usable in Winter. (Watland Playbook, p.5:
>      Andreas and Yaroslav both chose Sleds at Watland setup —
>      canonical precedent.)
>   2. Summer/Rasputitsa start, 2-slot Lord. Pick exactly one
>      Ship-or-Boat slot and one Cart slot:
>        2a. Start Locale is a Seaport (Riga, Reval, Pernau, Leal,
>            Narwia, Neva, Luga, Koporye) AND Lord's mat authorizes
>            Ships -> Ship + Cart.
>        2b. Start Locale is Novgorod (Russian river-spine hub) ->
>            Boat + Cart.
>   3. Summer/Rasputitsa start, 1-slot Lord. Pick the single
>      most-used Way class at the start Locale:
>        3a. Locale is on the Russian river spine (Volkhov, Ladoga,
>            Neva, Novgorod, Rusa, Lovat) -> Boat.
>        3b. Locale is interior with Trackway-dominated approaches
>            (Pskov, Ladoga with Karelians' role, etc.) -> Cart.
>      Ship is not the 1-slot default even at Seaports — the slot
>      has to double as supply transport, and Boat covers Waterway
>      supply chains better than Ship covers a single isolated Seaport.
>
> Per-scenario default table (canonical):
>
>   Pleskau:
>     Gavrilo @ Pskov  x1: Cart   (rule 3b)
>     Vladislav @ Neva x1: Boat   (rule 3a)
>   Watland:
>     Andreas @ Fellin x2: Sled, Sled (rule 1)
>     Domash @ Novgorod x1: Sled  (rule 1)
>     Vladislav @ Ladoga x1: Sled (rule 1)
>   Return of the Prince:
>     Andreas @ Koporye x2: Ship, Cart (rule 2a)
>     Aleksandr @ Novgorod x2: Boat, Cart (rule 2b)
>   Nicolle Variant:
>     Andreas @ Riga x2: Ship, Cart (rule 2a)
>     Aleksandr @ Novgorod x2: Boat, Cart (rule 2b)
>     Gavrilo @ Pskov x1: Cart (rule 3b)
>   Peipus:
>     Aleksandr @ Novgorod x2: Sled, Sled (rule 1)
>     Andrey @ Novgorod x2: Sled, Sled (rule 1)
>     Domash @ Novgorod x1: Sled (rule 1)
>     Karelians @ Novgorod x1: Sled (rule 1)
>   Crusade on Novgorod:
>     Gavrilo @ Pskov x1: Cart (rule 3b)
>     Vladislav @ Neva x1: Boat (rule 3a)
>
> Knud & Abel always start with Ship x2 (Lords reference and Playbook
> p.5); their slot is not an "any" slot and is fixed at load.
>
> Override mechanism. Each "any" slot emits a PendingDecision with
> default_value/current_value pre-populated. allowed_values always
> includes Boat/Cart/Sled and includes Ship iff the Lord's mat states
> "Ships". Three actions: confirm_setup_transport, set_setup_transport,
> confirm_all_setup_transports.
>
> Levy proceeds normally for a side. Any unresolved
> setup_transport_choice decisions for that side auto-confirm at first
> Levy action (per auto_confirm_on_levy) and are removed silently.
>
> Player-prompt cases (do NOT silently auto-confirm — affirmatively
> prompt):
>   - Vladislav at Neva (Pleskau, Crusade on Novgorod). Default Boat;
>     reasonable alternate Ship.
>   - Aleksandr at Novgorod in Summer scenarios (Return of the Prince,
>     Nicolle). Default Boat+Cart; reasonable alternate Ship+Boat.
>
> Sources cited: RoP 1.7.4 / 3.4.1 / 4.6.3 / 4.7.3 / 4.9.3;
> Nevsky_Map.txt; Nevsky_Lords.txt; Nevsky_Scenario_Reference.txt;
> Nevsky_PLAYBOOKFINAL.pdf p.5; Nevsky_Strategy.txt.

**Affected files (this PR):**
- `src/nevsky/scenarios.py::_build_lords` — apply per-scenario default
  table, populate Lord.assets immediately, emit PendingDecision with
  default_value/current_value.
- `src/nevsky/actions.py` — three new actions: `confirm_setup_transport`,
  `set_setup_transport`, `confirm_all_setup_transports`. Auto-confirm
  hook on first Levy action per side.
- `tests/test_scenario_loader.py` — extend to assert defaults match
  the table.
- `tests/test_q_001_setup_transport.py` (new) — table-driven verification
  of every scenario / lord / slot default; override and auto-confirm
  flows.

## Q-002 — Hermann / Rudolf / Yaroslav Transport-(any) slot status
*Adjudicated 2026-05-08. Encoded in commit (this PR).*

**User adjudication (verbatim, summarized):**

> Transport (no Ship) — Setup Default & Override Spec
>
> Resolves: Q-002. Extends Q-001.
>
> Finding. Nevsky_Lords.txt shows Hermann, Rudolf, Yaroslav each
> carry Transport x1 (no Ship). lords.json is correct; the Q-001
> spec was incomplete by missing the (no Ship) inventory.
>
> Complete setup-choice inventory (10 Lords):
>   (any)     -> {Boat, Cart, Sled, Ship}: Andreas, Vladislav, Andrey,
>                Domash, Gavrilo, Karelians, Aleksandr.
>   (no Ship) -> {Boat, Cart, Sled}:        Hermann, Rudolf, Yaroslav.
>   Fixed (no choice): Knud & Abel (Ship x2), Heinrich (Ship x2).
>
> Mechanism. Identical to Q-001. The only difference is allowed_values:
> read mat.ships_authorized to determine whether Ship is allowed.
>
> Per-scenario default table additions (8 rows):
>   Pleskau:                Hermann@Dorpat=Cart (3b), Yaroslav@Odenpah=Cart (3b)
>   Watland:                Yaroslav@Pskov=Sled (rule 1, EW start)
>   Nicolle Variant:        Hermann@Dorpat=Cart (3b)
>   Peipus:                 Hermann@Dorpat=Sled (rule 1, LW),
>                           Yaroslav@Pskov=Sled (rule 1, LW)
>   Crusade on Novgorod:    Hermann@Dorpat=Cart (3b),
>                           Yaroslav@Odenpah=Cart (3b)
>
> Rudolf carve-out. Rudolf NEVER starts Mustered. He is on the
> Calendar at scenario load in every scenario:
>   Pleskau box 1, Watland box 4, Return of the Prince box 9,
>   Nicolle box 9, Peipus box 13, Crusade on Novgorod box 1.
>
> _build_lords MUST NOT materialize Rudolf's starting Transport at
> load and MUST NOT emit a setup_transport_choice PendingDecision for
> him. The PendingDecision is emitted at the moment Rudolf is
> Mustered during play (Phase 2 Levy mechanics responsibility).
>
> Heuristic in code, alongside the table. Both: (1) lookup table for
> known scenarios; (2) heuristic fallback (Q-001 decision tree)
> when a Lord is Mustered at a Locale not covered. Heuristic depends
> on a Locale -> way-class classifier (Trackway / Waterway / Seaport).
> Cover the heuristic with a unit test that asserts running it on
> the table's inputs yields the table's outputs.

**Encoded behavior:**
- `_Q001_DEFAULTS` -> renamed `_SETUP_TRANSPORT_DEFAULTS`; covers
  both (any) and (no Ship) slot types; 24 rows total (16 + 8).
- `_build_lords` skips Lords who are NOT in `setup.mustered_lords`
  (i.e., on the Calendar). Their setup_transport_choice slots are
  not materialized at load.
- Phase 2 Muster (`_place_lord_on_map`) emits a
  `setup_transport_choice` PendingDecision when a Calendar-at-start
  Lord with starting_transport_choice is brought onto the map.
- New `nevsky.map` module exposes way-class classification helpers
  reused by Supply / Sail / Ravage adjacency in later phases.
- Heuristic function `_heuristic_setup_transport_default(scenario_id,
  lord_id, locale_id, season)` re-derives the table's defaults; the
  heuristic-vs-table consistency test prevents drift.

**Affected files (this PR):**
- `src/nevsky/scenarios.py` — rename `_Q001_DEFAULTS` ->
  `_SETUP_TRANSPORT_DEFAULTS`; add 8 rows; skip non-Mustered Lords;
  call heuristic for fallback.
- `src/nevsky/map.py` (new) — way-class helpers.
- `src/nevsky/actions.py::_place_lord_on_map` — emit
  setup_transport_choice for Calendar-at-start Lords on Muster.
- `tests/test_q_001_setup_transport.py` -> renamed
  `tests/test_setup_transport_defaults.py`; +8 rows; +heuristic test.
- `RULES_QUESTIONS.md` — Q-002 cleared.

---

## Q-003 — Lieutenants and Marshals (4.1.3)

**Adjudication (verbatim from user, Round 10):**

> Implement the permissive interpretation of "neither may currently
> be a Marshal":
>
> * Lords with `marshal_role: "permanent"` (Andreas, Aleksandr) are
>   always barred from Lieutenant pairings.
> * Lords with `marshal_role: "secondary"` (Hermann, Andrey) are
>   barred only when actively filling the Marshal role at the time
>   the pairing is checked.
> * Lords with `marshal_role: null` are never barred on Marshal
>   grounds.
>
> Note: "actively filling the Marshal role" requires knowing the
> current Marshal, which depends on the Q-005 work below. Until that
> lands, secondary Marshals should be treated as inactive (accepted)
> outside of Battle Array context.

**Citation.**
Rules of Play 2E, 4.1.3 ("Lieutenants ... Neither Lord may currently
be a Marshal"); 1.5.1 (Marshal definitions, permanent vs secondary);
clarified per Q-003 user adjudication.

**Encoded.**
- `src/nevsky/campaign.py::_is_currently_marshal` — helper that
  returns True for permanent-role Lords on map; False for secondary
  (until Q-005); False for null. The function carries a TODO comment
  marking the Q-005 integration point (secondary Marshal becomes
  active when permanent counterpart off-map AND Lord at Front Center).
- `src/nevsky/campaign.py::_h_place_lieutenant` — applies the helper
  to BOTH the lieutenant and lower_lord candidates.

**Tests.**
- `tests/test_lieutenants.py::test_q003_permanent_marshal_rejected_as_lieutenant`
- `tests/test_lieutenants.py::test_q003_permanent_marshal_rejected_russian_side`
- `tests/test_lieutenants.py::test_q003_secondary_marshal_accepted_when_inactive`
- `tests/test_lieutenants.py::test_q003_non_marshal_lord_accepted`
- `tests/test_lieutenants.py::test_q003_is_currently_marshal_helper`

**Side effects.**
- Existing Lieutenant tests that paired Andreas (permanent Marshal)
  as Lieutenant were updated to use non-Marshal Lord pairs (yaroslav
  + knud_and_abel; or hermann + yaroslav for secondary-active tests).

---

## Q-005 — Battle Array three-front-positions and Flanking (4.4.1, 4.4.2)

**Adjudication (verbatim from user, Round 10):**

> Refactor the Battle module to faithfully implement the 2E
> three-position Array. Engine handles all structure and math; the
> LLM operator makes genuine player choices.
>
> Engine responsibilities: track per-Lord Front position; enforce
> Active at Front center; Defender fills center first then left/right;
> per-position Strikes with Flanking ('directly opposite or, if
> Flanking, closest enemy in that row'); Reposition at start of
> Round 2+ (advance Reserves, fill empty center); re-evaluate
> Flanking after mid-round Routs.
>
> LLM operator responsibilities: initial non-center Front placements;
> Reserve advancement when ambiguous; Hit allocation when a Lord is
> Flanked and the choice exists; Rout responses where the rules
> permit.
>
> Tests: every battle test must pin operator decisions. Provide a
> scripted_decisions parameter; deterministic_fallback picks the
> leftmost legal option whenever a scripted decision is missing.

**Citation.**
Rules of Play 2E, 4.4.1 (Battle Array, three Front positions),
4.4.2 (Rounds, Reposition, Strike target rules), page 14-15.

**Encoded.**
- `src/nevsky/state.py::CombatPending` — `attacker_positions` and
  `defender_positions: dict[str, str]` map each participating Lord to
  one of `"left" | "center" | "right" | "reserve"`.
- `src/nevsky/battle.py::BattleDecisionContext` — funnel for operator
  decisions: scripted FIFO list, optional callback, or leftmost
  fallback. Decision types: `initial_placement_attacker`,
  `initial_placement_defender`, `reserve_advance`, `center_fill`,
  `flanker_target`.
- `src/nevsky/battle.py::_init_battle_array` — Active at center;
  Attacker fills left/right; Defender fills center first then left
  then right (rule 4.4.1).
- `src/nevsky/battle.py::_remove_routed_from_array` — A Lord Routs
  the moment his last Unrouted unit Routs; his slot opens (4.4.2).
- `src/nevsky/battle.py::_reposition` — Round 2+ Advance Lords (Reserves
  into empty Front slots) then Center Fill (slide left or right Lord
  into empty center) — 4.4.2.
- `src/nevsky/battle.py::_strike_target` — directly-opposed, or
  Flanking → closest enemy in row, with operator tie-break for ties.
- `src/nevsky/battle.py::resolve_battle` — refactored to compute
  per-striker raw Hits, route via `_strike_target`, aggregate per
  target Lord, round up per target, apply through `_resolve_hits`.
  Returns include `attacker_positions`, `defender_positions`, and
  `decisions` trace.
- `src/nevsky/campaign.py::cmd_stand_battle` — accepts
  `args.scripted_decisions` and `args.decision_callback`; threads them
  through resolve_battle alongside the existing concede/holds args.
- `BRIEF.md` — added an "Engine / Operator Split — Battle decisions"
  section that documents the protocol.

**Tests.**
- `tests/test_q005_battle_array.py` — 11 dedicated regressions:
  Active-at-center; one-extra-Lord placement; Defender center-first
  fill; Reposition Advance; Reposition Center Fill; directly-opposed
  target; Flanking closest-in-row; Flanking tie-break via decision;
  scripted decisions logged in result; leftmost fallback;
  type-mismatch raises.
- All previously-existing Battle tests (314 of them) re-pass
  unmodified under the new positions-aware engine via the leftmost
  deterministic fallback. Total: 325 passing.

**Out of scope for this PR.**
- Storm Reposition (4.5.2 page 17): Storm has its own one-Lord-Front
  Array with a Reposition step that is "switch Front and any Reserve
  Lord". The current `resolve_storm` does not implement this; should
  be a follow-up question (Q-007 if needed).
- Q-006 Relief Sally Array depends on this PR. Plan: implement after
  this PR is merged.
- Q-003 Marshal-at-Front-Center integration (`_is_currently_marshal`
  for secondary Marshals). The Q-003 PR added a TODO marker; once
  both Q-003 and Q-005 land, a small follow-up commit can make
  secondary Marshals at Front Center count as currently-active.

**Commit.** _to be filled after push._

---

## Q-006 — Relief Sally Array (4.4.1, 4.4.2)

**Adjudication (verbatim from user, Round 10):**

> Implement after Q-005 is merged and green. Extends the Array
> machinery:
>
> * Sallying Attacker Lords arrayed in a row behind the Defender's
>   Front.
> * Defender Reserve Lords form a Rearguard row opposite the Sallying
>   row. If no Rearguard exists, Sallying Lords Flank Front Defenders,
>   all considered equally close.
> * Siegeworks rolled separately, applied only against Strikes by
>   Sallying Attackers against Front Defenders. Front Attackers'
>   Strikes ignore Siegeworks as before.
> * On Attacker loss: Withdraw Sallying Lords back into the Stronghold,
>   reduce Siege markers there to one (Rules of Play 2E p. 14).
>
> Same engine-vs-operator split as Q-005: engine handles row geometry,
> Siegework math, and the Withdraw path; operator chooses placements
> and Hit directions.

**Citation.**
Rules of Play 2E, 4.4.1 (Relief Sally Array, page 14), 4.4.2 (Adjust
Rows / Reposition references), 4.5.3 (Sally / Raid effect on Siege
markers).

**Encoded.**
- `src/nevsky/battle.py::_array_sally_lords` — places Sallying Lords
  in `sally_center` first then `sally_left` / `sally_right` /
  `sally_reserve`. Operator picks per slot when multiple candidates.
- `src/nevsky/battle.py::_shift_defender_reserves_to_rearguard` —
  when Sallying Lords are present, Defender Reserves shift into
  `rearguard_center` first then `rearguard_left` / `rearguard_right`.
- `src/nevsky/battle.py::_init_battle_array(sallying_lords=...)` —
  optional sallying_lords parameter triggers the Relief Sally
  extensions: sally_* in attacker_positions, rearguard_* in
  defender_positions.
- `src/nevsky/battle.py::_strike_target` — extended to handle the
  Sally row (targets Rearguard if any; else Flanks Front Defenders
  all equally closely with operator choice) and the Rearguard row
  (targets Sally row directly-opposed or Flanking).
- `src/nevsky/battle.py::resolve_battle(sallying_lords, siegeworks_for_sally)` —
  new params. Sally-row strikers' Hits are tracked separately so a
  per-Hit Walls roll (Walls 1..siegeworks_for_sally) absorbs Hits
  before they reach the Defender Front Lord. Marching-attacker Hits
  bypass Siegeworks as before.
- `src/nevsky/campaign.py::cmd_stand_battle` — detects Relief Sally:
  any Lords on the attacker side at to_locale who are
  `in_stronghold=True` with siege_markers > 0 are Sallying. The
  to_locale's siege_markers count becomes `siegeworks_for_sally`.
- `src/nevsky/campaign.py::cmd_stand_battle` aftermath — when
  attackers lose AND Sallying Lords joined: each Sallying Lord
  Withdraws back inside (in_stronghold=True at to_locale; not a
  Retreat); Siege markers at the locale reduce to 1.

**Tests.**
- `tests/test_q006_relief_sally.py` — 8 dedicated regressions:
  single-Sally placement, two-Sally with operator pick, Defender
  Reserve → Rearguard shift, Sally-targets-directly-opposed-Rearguard,
  Sally-Flanks-Front-when-no-Rearguard, Rearguard-strikes-Sally,
  init_battle_array-with-Sally populates both rows, attacker-loss
  Sally Withdraw + Siege → 1.
- All 325 tests from the Q-005 baseline continue to pass. Total: 333.

**Out of scope.**
- Storm Reposition (4.5.2 page 17): Storm has its own Reposition rule
  ("switch Front and any Reserve Lord"). Not in Q-006 scope; future
  Q-NNN.
- Multi-round Reposition with Sally rows. The "Adjust Rows" rule
  (4.4.2 page 15) covers what happens when an entire row Routs in
  Relief Sally; the current implementation removes Routed Lords from
  the Array but does not yet promote Rearguard → Reserve nor flip
  Sallying-vs-Front-Defenders dynamics. Future enhancement; not
  triggered by the Q-006 test scenarios but is documented as a
  known gap in the resolve_battle docstring.

**Commit.** _to be filled after push._

---

## Q-004 — T12 Ordensburgen: which Strongholds are Commanderies? (1.3.1)
*Adjudicated 2026-05-08. Encoded in commit (Round 12 PR).*

**User adjudication (verbatim):**

> Question four should already be resolved - the commandaries are
> just those four spaces.

**The four Commanderies are:** Wenden (Bishopric), Fellin (Castle),
Adsel (Castle), Leal (Bishopric). These are the only Strongholds with
the Order seat symbol on the canonical 2E map. No others bear the
symbol; option (a) from the question is the canonical answer, not a
conservative subset.

**Consequences for the harness.**
- `locales.json` `commandery: true` flag remains exactly the four
  Locales above; no expansion needed.
- `actions.py::_seats_of` already grants T12 extra Seats correctly.
- `campaign.py::_effective_command_rating` already triggers the +1
  Command bonus at exactly these four Locales.

The Q-004 entry has been removed from RULES_QUESTIONS.md.

---

## Q-007 — Russian Archery special rounding (4.4.2)
*Adjudicated 2026-05-08. Encoded in commit (Round 18 PR).*

**User adjudication (verbatim):**

> Both questions resolve to the same underlying issue: the Arts of War
> Reference (Nevsky_Arts_of_War_Reference.txt) has the canonical
> designer-clarified text for everything Cowork is calling "ambiguous,"
> but the consultation log skipped it in favor of the PDFs (which it
> can't read). The .txt reference is authoritative and unrestricted.
> Worth a process note to Cowork: when the question is about card text
> or capability mechanics, that file is the answer first, before
> invoking the PDF restriction.
>
> Q-007 — Russian Archery rounding
>
> Recommendation: option (c), with the specific algorithm below.
>
> Nevsky_Arts_of_War_Reference.txt line 234 (R1/R2 Luchniki Tips) is
> the controlling text:
>
>   "When Luchniki Archer units combine with Garrison or Streltsy
>   Crossbowmen units, any Hit that includes at least ½ a Hit from
>   Crossbowmen does cause the reduction to enemy Armor Protection.
>   That is, when rounding units with Archery, round in favor of
>   Crossbowmen."
>
> This resolves the rounding-granularity question. The current
> behavior (option a) over-applies in mixed cases. The fix:
>
>   # Per target per step
>   crossbow_raw = sum of raw Hits from -2-Armor strikers
>   normal_raw   = sum of raw Hits from non--2-Armor strikers
>   total_hits        = ceil(crossbow_raw + normal_raw)
>   crossbow_hits     = ceil(crossbow_raw)             # rounds in favor
>   normal_hits       = total_hits - crossbow_hits     # the remainder
>
> Sanity check against the rule's worded examples:
>
>   Crossbow raw  Normal raw  total_hits  -2-Armor Hits  Normal Hits
>   0.5           1.0         2           1              1
>   0.5           0.5         1           1              0
>   0.5           2.0         3           1              2
>   1.5           0.5         2           2              0
>   1.5           1.5         3           2              1
>   0.0           1.5         2           0              2
>
> Storm has the same logic — Garrison MaA carry the -2 Armor flag and
> combine with other Russian Archery the same way.
>
> Implementation deltas:
>
> _resolve_hits accumulates crossbow_raw and normal_raw separately per
>   target, then computes the two ceilings as above.
> _absorb_hit takes is_crossbow_hit: bool per Hit instead of reading a
>   per-target boolean. The Hit list per target becomes ordered:
>   crossbow Hits first, then normal Hits.
> The per-target boolean striker_has_armor_minus_2 becomes redundant;
>   remove it.
> New parametrized test covering the table above for Battle and for
>   Storm-Garrison cases.
>
> Conservative-toward-Russian over-application currently inflates
> Russian win rates; tightening this is correct even though it slightly
> lowers the smoke-test 84%. The smoke driver is a sanity check, not a
> balance target.

**Citation.** `reference/Nevsky_Arts_of_War_Reference.txt` line 234,
R1/R2 Luchniki Tips: "round in favor of Crossbowmen."


## Q-008 — Tier 2 Battle Hold mechanical effects (4.4.2)
*Adjudicated 2026-05-08. Encoded in commit (Round 18 PR).*

**User adjudication (verbatim):**

> Q-008 — Tier 2 Battle Holds
>
> Recommendation: option (a) — wire each per the Arts of War Reference
> designer tips. None of these is genuinely ambiguous; the .txt
> reference resolves every case Cowork flagged.
>
> The relevant Tips from Nevsky_Arts_of_War_Reference.txt:
>
> T4/R1 Bridge: "In Round 1, only two of his units may Strike in
>   Melee; in Round 2, four may do so, and so on." Front-center enemy
>   Lord only, non-Winter, Melee only. Archery and Hit absorption
>   unaffected. Doesn't impede Relief-Sallying Lord.
>   Implementation: Per-Lord melee_strike_unit_cap = 2 * round_number
>   modifier on the targeted enemy Lord. Q-005 modeled front-center,
>   so this is now wirable. Cap applies to Melee step only.
>
> T5/R2 Marsh: "All enemy Horse's Melee and Archery are blocked for
>   two Rounds; its ability to absorb Melee Hits is not." Defending
>   only, non-Winter, Rounds 1-2.
>   Implementation: Side-level flag blocking Horse units from
>   Striking (both Archery and Melee) for Rounds 1-2 of the attacker.
>   Horse can still absorb.
>
> T6/R6 Ambush: "Lords of that side who are at left or right front
>   would Flank the enemy's center Lord, while any enemy Lords at left
>   or right front would be uninvolved (so could not absorb Hits nor
>   Rout in Round 1)." Round 1 only. Two play modes: block Avoid
>   Battle, OR Round 1 ignore.
>   Implementation: Round 1 modifier: enemy left/right Lords don't
>   strike, don't absorb, don't Rout. Block-Avoid mode is a separate
>   gate at Avoid-Battle resolution.
>
> T9/R5 Hill: "Round 1 and 2 [side] Archery is x1 (not x½). Melee is
>   unaffected." Defending only.
>   Implementation: Side-level Archery multiplier 1.0 (instead of 0.5
>   default) for the playing side, Rounds 1-2. Single capability on
>   the player's whole side, not per-Lord.
>
> T10 Field Organ: "Each of that Lord's Knights and Sergeants units
>   when Striking in Melee during Round 1 cause one added Hit—three
>   Hits each for Knights in Battle or two Hits each in Storm or for
>   Sergeants. Against Russian #R1 Bridge Event, only the units
>   Striking cause the added Hits. Horse units blocked from Striking
>   by #R2 Marsh or #R6 Ambush add no Hits."
>   Implementation: Per-Lord, Round 1, Melee step only. +1 Hit per
>   striking Knight or Sergeant unit. Critical: bonus applies only to
>   units that actually Strike (so it interacts correctly with Bridge
>   cap and with Horse-blocking Holds).
>
> R4 Raven's Rock: Already wired per Cowork.
>
> Specific clarifications Cowork's note got wrong or marked TBD:
>
> Hill is side-wide Archery x1 (not x½), not per-Lord. The card text
>   says "[side]ic Archery is x1" with no Lord scoping. Defender's
>   side, Rounds 1-2. Melee unaffected.
> Ambush Round 1 mode means enemy left/right Lords are uninvolved —
>   they don't strike, don't absorb, don't Rout. The playing side's
>   left/right Lords get to flank-strike the enemy center.
> Field Organ's effect is +1 Melee Hit per striking Knight or Sergeant
>   unit, Round 1, on the targeted friendly Lord. Important
>   interaction: must check the actual strike list at resolution time
>   (post-Bridge-cap, post-Marsh, post-Ambush), not the unit count on
>   the mat.
>
> Implementation deltas:
>
> resolve_battle per-Round Strike phase needs three new modifier
>   hooks: per-Lord Melee unit cap (Bridge), side-level Horse-Strike
>   block (Marsh), Round-1 left/right-Lord disable (Ambush).
> resolve_battle per-Round Archery phase needs a side-level Archery
>   multiplier override (Hill).
> _apply_strike_bonuses needs a per-Lord, per-unit-type Round-1 +1 Hit
>   modifier (Field Organ), evaluated on the post-cap strike list.
> _consume_battle_holds already validates and discards correctly; no
>   change there beyond removing the "no-op" doc comments.
>
> Tests: one focused test per Hold, covering the explicit interaction
> edges (Bridge cap × Field Organ, Marsh blocks Horse but not
> absorption, Ambush left/right disabled including absorption, Hill
> defender vs attacker side scoping).

**Citation.** `reference/Nevsky_Arts_of_War_Reference.txt` Tips
sections for T4/R1, T5/R2, T6/R6, T9/R5, T10.

