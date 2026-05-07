# Open Questions

Format per BRIEF: ID, Context, Consultation log (5 steps), What is
ambiguous, Options, Affects, Blocking?

When resolved, MOVE the entry to RULES_DECISIONS.md with the user's
adjudication, citation, and commit hash.

---

## Q-001 — Transport-(any) choice at scenario setup

**Context.**
Phase 1 scenario loader (`src/nevsky/scenarios.py::_build_lords`)
materializes Mustered Lords' starting Forces and Assets from
`src/nevsky/data/static/lords.json`. Several Lords' mats specify
starting Transport as "Transport x1 (any)" or "Transport x2 (any)" —
where "any" means the player at setup chooses Transport types
(Boat / Cart / Sled / Ship) up to the count, subject to the Lord's
Ships authorization. The harness needs to materialize concrete
Transport counts so the GameState model is fully populated; how should
the choice be resolved at scenario load?

**Consultation log.**

1. *Curated reference.* `reference/Nevsky_Lords.txt` documents each
   Lord's Transport line. For example, Andreas: "Transport x2 (any)
   [exception to the standard '(no Ships)' default — 'any' means the
   player at setup selects any single Transport type INCLUDING Ship,
   per Rule 3.4.1 procedure]". The reference defers to Rule 3.4.1 and
   does not specify a default.
2. *Rules of Play, primary section.* Rule 3.4.1 cited but not read —
   the user instructed not to read PDFs in `sources/` for this work
   (acknowledged in the chat). Reference text quotes "per Rule 3.4.1
   procedure" without giving the rule body.
3. *Rules of Play, related sections.* Not read (PDF restriction).
4. *Playbook examples.* Not read (PDF restriction).
5. *Second Edition Changes.* `reference/Nevsky_Second_Edition_Changes
   .txt` does not address Transport-of-any choice; the only Transport-
   adjacent 2E changes are the Hermann/Knud&Abel force/asset
   adjustments (already applied in `lords.json`).

No external/historical sources consulted.

**What is ambiguous.**
The rules treat Transport-of-any as a player choice at setup. The
harness has no policy for resolving the choice at scenario-load time.
A scenario JSON could specify it, the loader could default it, or the
loader could record it as a pending decision and require resolution
before Levy proceeds.

**Options.**

a. *Pending decision (current Phase 1 behavior).* Loader emits a
   `setup_transport_choice` PendingDecision per any-slot, owed by the
   Lord's side. State is internally consistent and Phase 2 (Levy
   mechanics) wires up the resolution flow. Argument: matches the
   rules' "player chooses at setup" language; nothing is silently
   pre-picked by the harness.

b. *Default to Cart.* Loader picks Cart for any-slots (most generic;
   Trackway-usable; not a Ship). Argument: removes a player decision
   from setup; LLM/user can edit state JSON if they want a different
   choice. Drawback: silently overrides player agency at setup.

c. *Per-scenario override.* Each scenario JSON specifies the
   Transport choice for each Mustered Lord. Argument: scenario data
   becomes fully self-describing. Drawback: all six scenarios + Nicolle
   need authored choices; data balloons.

d. *Pick to maximize Ship for ships-authorized Lords (as the rules
   imply for fleet-heavy mats), Cart otherwise.* Argument: matches
   designer intent; minimizes "wasted" capacity. Drawback: still a
   silent choice without rules basis.

**Affects.**

- `src/nevsky/scenarios.py::_build_lords` (where pending decisions are
  currently emitted).
- All seven scenarios via load_scenario.
- `tests/test_scenario_loader.py::test_setup_pending_transport_choices_match_lord_count`.
- Phase 2 will need a `do` action to resolve setup choices before Levy
  starts — or Phase 2 starts with the assumption that any pending
  setup choices have already been resolved.

**Blocking?**
No. Option (a) is the current behavior and produces a valid state
file; Phase 1 deliverables work without resolution. Phase 2 will need
a decision to know how Levy interacts with un-resolved setup choices.
