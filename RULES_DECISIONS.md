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
