# Open Questions

Format per BRIEF: ID, Context, Consultation log (5 steps), What is
ambiguous, Options, Affects, Blocking?

When resolved, MOVE the entry to RULES_DECISIONS.md with the user's
adjudication, citation, and commit hash.

---

---

## Q-R190-A — Un-implementable this_lord Capability at first Levy

*Surfaced 2026-05-17 in R190 round-trip sweep.*

### Context

In the Pleskau scenario, the `setup.removed_from_play` list includes
Aleksandr and Andrey (both Russian Lords). The Russian deck still
contains R5 (Druzhina: aleksandr/gavrilo/andrey), R6 (Druzhina:
aleksandr/gavrilo/andrey), and R11 (House of Suzdal:
aleksandr/andrey). R11 in particular has BOTH its eligible Lords
permanently removed; when drawn at first Levy as a Capability
(3.1.2), no Mustered Lord can carry it.

The handler `_h_aow_implement_card` (`actions.py:417`) currently
raises `missing_arg` when called without `lord_id`, and `bad_target`
or `ineligible_target` if called with a Lord that doesn't qualify.
There is no path to discard the card; pending_draw stays
non-empty; the Arts-of-War step blocks all further Levy progress.

The R190 sweep surfaced this as ~30 findings in pleskau seed=1..5
(each session stuck at step 5 when R11 hit pending_draw). R190's
enumerator fix (SMOKE-124) makes legal_moves emit NOTHING for
R11 in this case so the asymmetry surfaces honestly, but the
underlying game-state dead-end remains.

### Consultation log

1. Source rule cited: 3.1.2 ("First Levy: implement bottom-half =
   Capability") and 3.4.4 (capability_eligibility per Lord). Neither
   describes what happens if NO Lord is eligible.
2. Compared against T13 William of Modena precedent: Heinrich is
   also in `removed_from_play` for pleskau, but T13 has its own
   special-case hardcoded gate in `actions.py:2003` raising
   `heinrich_off_map`. T13 lives in the deck and can be "Levy
   delayed" — but R11/R5/R6 have no such per-card escape hatch.
3. Compared against `no_event=True` cards (`actions.py:459`): the
   harness already supports auto-discard for cards drawn during
   the wrong half (no-event/no-capability). The pattern is
   `deck.pending_draw = deck.pending_draw[1:]; deck.removed.append(cid)`.
4. AoW Reference Event Tips reviewed for R5/R6/R11 — no specific
   instruction for "no eligible Lord" case.
5. No precedent in the existing RULES_DECISIONS.md.

### What is ambiguous

When a this_lord scope Capability is drawn at first Levy and no
Mustered own-side Lord is eligible (because all eligible Lords are
removed_from_play or in another non-mustered state), what should
happen?

### Options

(a) **Auto-discard to deck.discard.** Treat as a draw that doesn't
   stick — pop pending_draw, append to discard. Card may be redrawn
   in a future Levy when an eligible Lord could be Mustered.
   Closest match to existing no-event auto-discard pattern.

(b) **Auto-remove permanently.** Pop pending_draw, append to
   deck.removed. Card is gone for the rest of the game. Matches
   3.1.3 (2E)'s permanent removal of no-event/no-capability cards.

(c) **Allow assignment to any Mustered own-side Lord ignoring
   eligibility.** Player picks any of their Lords. Matches the
   "you must implement something" reading of 3.1.2.

(d) **Re-shuffle into deck.** Pop pending_draw, insert back into
   deck at a random position. Player draws something else.

(e) **House rule: this is scenario data, fix at load time.** Add
   `setup.removed_capabilities` to pleskau.json listing R5/R6/R11.
   The handler stays strict; the scenario data declares the
   un-usable cards up front. No code changes to apply_action.

### Affects

- `_h_aow_implement_card` in `actions.py` (lines 482-516 capability
  branch).
- `scripts/roundtrip_sweep.py` will stop stalling on pleskau
  pending_draw R11 once a path exists.
- Self-play and strategic agent sweeps that hit R11 will progress
  through pleskau instead of stalling.
- Scenario-specific data files (option e) for pleskau and any
  similar scenario with Lords-removed-but-capability-kept.

### Blocking?

Not blocking R190 close — sweep is otherwise clean (0/15350 probes).
The pleskau stall is visible but expected. R191's sweep-extension
and R192's tournament harness would benefit from resolution.


