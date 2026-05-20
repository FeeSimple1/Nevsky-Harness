# Open Questions

Format per BRIEF: ID, Context, Consultation log (5 steps), What is
ambiguous, Options, Affects, Blocking?

When resolved, MOVE the entry to RULES_DECISIONS.md with the user's
adjudication, citation, and commit hash.

---

## Q-R201-A — May a player decline a *targetable* immediate Event?

*Surfaced 2026-05-19 in R201.*

### Context

At a subsequent Levy (3.1.3) drawn cards are revealed as Events; an
immediate Event resolves at once. R201 made a BARE implement
(`aow_implement_card {card_id}` with no target supplied) of an immediate
Event that cannot resolve reveal-and-discard with no effect, so
`pending_draw` can always be cleared (this is what lets the SMOKE-131
advance-block apply at all Levies without deadlocking).

That bare-implement-discard is unambiguously correct when NO legal
target exists (the Event simply has no effect). It is ALSO how the
harness currently treats a bare implement when a legal target DOES
exist — i.e. a bare implement of a targetable Event discards it with no
effect, as if the player declined.

### What is ambiguous

When an immediate Event has at least one legal target, is the player
*required* to resolve it (pick a target and apply the effect), or *may*
they decline and discard it with no effect? L&C Event text varies —
some Events read "you may," others are mandatory. The current harness
behavior effectively allows declining any targetable immediate Event
(via a bare implement). For mandatory Events that is too permissive;
for optional Events it is correct.

### Options

(a) **Per-card mandatory/optional flag.** Tag each immediate Event as
    mandatory-when-targetable or optional. A bare implement of a
    mandatory Event with a legal target raises (must pick); only
    optional Events (or no-legal-target cases) bare-discard.
(b) **Treat all immediate Events as optional-to-apply.** Current R201
    behavior. Simplest; deadlock-free. May under-apply mandatory Events
    if an agent/LLM bare-implements.
(c) **Treat all as mandatory-when-targetable.** A bare implement raises
    whenever a legal target exists; legal_moves must then always offer
    an arg-populated implement so the card can still be cleared.

### Affects

- `_h_aow_implement_card` immediate / this_levy branches (the R201
  no-op-discard).
- Possibly `legal_moves` event enumeration (option c needs
  arg-populated implements offered).
- Per-card data tagging (option a).

### Blocking?

Not blocking. R201's behavior is deadlock-free and correct for the
no-legal-target case (the only case that caused the deadlock). This
question only refines fidelity for *targetable* immediate Events.

