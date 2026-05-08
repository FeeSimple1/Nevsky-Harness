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
