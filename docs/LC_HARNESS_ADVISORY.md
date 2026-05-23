# Cross-Harness Advisory: Lessons from Hardening an LLM-Playable L&C Rules Engine

**From:** Nevsky-Harness (GMT *Levy & Command* Vol. II, 2nd Ed.)
**For:** Maintainers of sibling L&C rules-engines (Almoravid, Inferno, Seljuk, and any wargame harness meant to be played/tested by an LLM or scripted agent).
**Builds on:** Inferno Advisories #1 (Retreat-that-doesn't-relocate) and #2 (the co-location bug *class*), and Seljuk's confirming reply. This consolidates what a ~20-round hardening pass over Nevsky (rounds R203–R222) reproduced, generalized, and added.

**One-line takeaway:** In an agent-driven L&C harness, the authoritative *executor* is usually correct; the bugs cluster in the **legal-move menu drifting away from it**, and in **branches no default auto-player ever walks**. Two cheap structural changes — a *validated action palette* and a handful of *always-on invariants* — neutralize most of that class and turn the rest into self-reporting diagnostics.

---

## 1. The dominant bug class: enumerator/handler asymmetry

Every L&C harness has (at least) two descriptions of "what is legal": the **enumerator** that builds the menu of actions, and the **handler/executor** that applies one and enforces the rules. They drift. In Nevsky this single class produced the large majority of findings.

It drifts in **both** directions:

- **Over-enumeration** — the menu offers a move the handler rejects. The agent looks like it broke a rule when it merely trusted the harness. Nevsky examples: a Besieged Lord offered March/Tax/Forage; Withdraw offered into a non-Friendly Stronghold; Veche "slide cylinder" offered for an off-board cylinder; a Lieutenant's March emitted without its required Lower-Lord group; Ravage offered when its 2-action cost was unaffordable; a parallel-Ways March that didn't pin which Way.
- **Under-enumeration** — the menu omits a legal move, so a menu-driven player can *never* take it. Nevsky examples: an entire capability action (Stone Kremlin, Stonemasons, Smerdi, Raiders) with a working handler but no menu entry; the Papal Legate's +1-Command bonus (the rule existed, the engine offered nothing, and a code comment wrongly *denied* the rule existed); the Ambush-block response window.

**Recommendations**

1. **Define each legality predicate once.** When the enumerator must mirror a handler precondition, share a function rather than re-deriving the logic inline. Every place the menu re-derives "is this legal?" is a future drift point.
2. **Hunt under-enumeration explicitly.** Enumerate every dispatchable action/handler and cross-check that the menu can actually produce each one. A working handler nobody can reach is invisible to behavioral testing.
3. **Mind cost/variant-gated actions.** Many over-enumerations were *conditional* costs the menu ignored: 2-action Ravage vs 1, Laden vs Unladen March cost, parallel Ways with different transport costs, once-per-turn capability flags, "blocked this turn" flags. The menu must compute the same gate the handler does.

---

## 2. The single highest-leverage fix: a validated action palette

This is the structural change that pays for itself immediately. For the **agent-facing** action list (not the fast internal hot loops), wrap enumeration with a validator:

```
for each concrete candidate the enumerator produced:
    probe = deepcopy(state)
    try: apply(probe, candidate)        # discard probe
    except IllegalAction as e:          # over-enumeration
        record {candidate, reason}      # structured diagnostic
        drop it from the menu
    else:
        keep it
templated/parameterized candidates that can't be probed → keep, mark "unvalidated"
```

Why it's worth it:

- The LLM/agent **never sees an illegal move**, so it never wastes a turn or looks like it made a rules error.
- Every dropped candidate is logged as an actionable **over-enumeration diagnostic** — so you still find and fix the root menu bug; this is a safety net, not a substitute.
- It probes **every** candidate each turn, not just the one the agent picks, so it is a *stronger* detector than catching `IllegalAction` at apply-time. (On Nevsky's first validated run it caught a parallel-Ways March bug no agent had ever selected.)

**Two prerequisites / caveats**

- **RNG must live in the state**, not in a module global. Nevsky stores `seed` + an incrementing `rng_state` counter in the state and derives each roll as a pure function of them. That makes `deepcopy → apply → discard` perfectly safe: probing advances only the copy's counter; the real game's dice are untouched. *If your RNG is a global, validation (and any lookahead) will corrupt determinism.* This is the most important architectural enabler — adopt it if you haven't.
- **Cost.** A deep-copy-and-apply per candidate is fine for an interactive/LLM-paced path (API latency dominates) but too slow for hot loops (fuzz sweeps, tournament agents). Keep validation on the agent-facing path; leave the fast paths unvalidated.

---

## 3. Invariants beat trajectories. Write them first.

The most reproducible lesson across all three harnesses: **"green" only means "no violation of the invariants you happened to write."** A missing invariant launders every future bug of its class as passing.

The canonical one (from Inferno, confirmed by Seljuk and Nevsky):

> **No Locale may contain mustered units from both sides that are both *outside* a Stronghold, when no Approach/Battle is pending.**

Run it after **every** applied action. Implementation notes the family converged on:

- Key on the per-unit **"inside Stronghold" flag**, not on the presence of a Siege marker. Besieged-inside vs besiegers-outside is legal and is excluded automatically because the inside unit carries the flag. "Skip Locales with a Siege marker" is too coarse and hides real bugs.
- **Exclude the active combat Locale while a response is pending.** A March creates contact one step before the defender chooses Avoid/Withdraw/Stand; that transient co-location is legal. Every project (including Nevsky) hit this as a false positive first — the predicate is "opposing, mustered, both-outside, **and no pending combat**."
- **Exclude a "Bypassing" flag** if your edition has one (Nevsky Vol. II does not; later volumes do).

Add other cheap always-on invariants too: VP within its cap and non-negative; markers/counters within bounds; no card in two zones at once; service/initiative markers on-track. They cost microseconds and catch corruption from unrelated subsystems.

---

## 4. The illegal-co-location state has *independent* doors. Audit each.

Inferno Advisory #2's framing held up exactly on Nevsky. The same illegal board state is reachable from unrelated subsystems; fixing one door tells you nothing about the others.

- **Door A — Combat disposition.** A losing Lord that survives must *relocate* (Retreat), not merely take a penalty. Verify the loser's map position actually changes, and that destination rules are enforced (adjacent; no enemy Lord/Stronghold at the destination; defender may not retreat back along the attacker's approach Way; a marching attacker retreats to where it came from; no naval-Way retreat). Enforcing these requires the **approach breadcrumb** (which Way / from where) to survive from the March step to the loss step — it's commonly recorded for the Avoid step and dropped before disposition. *(Nevsky was correct here; Inferno/Seljuk were not.)*
- **Door B — Marker lifecycle leak.** A Siege/Bypass marker set on entry must be cleared whenever the Stronghold becomes free of enemy Lords — on **every** departure path, not just post-combat: March-out, Disband, permanent Removal, Bypass-move. And clear the inside defender's "besieged" flag too, or it stays besieged forever and corrupts every `siege_markers` read (Forage/Supply/Tax legality, join-vs-besiege). **Also handle the empty-Stronghold case** (a besieger that took an *undefended* Stronghold then left) — Nevsky had fixed the defended case but the empty case slipped through (R218/SMOKE-159's sibling). The fix is one shared "Stronghold becomes free of enemies" sweep invoked from all departure paths.
- **Door C — Placement onto a contested Locale.** Every on-board placement path (Muster, auto-Muster, event/capability summons, reinforcement) must reject an enemy-occupied / besieged / Conquered destination unless a named exception applies — and when an exception *does* apply (e.g. a Lord who musters inside his besieged Seat), set the inside flag and honor capacity rather than dropping him in the open. **Centralize this in one free-Seat/eligibility predicate** that every placement door calls; a single shared gate is why one audit covered Muster, Legate-auto-Muster, and Veche-auto-Muster at once.

---

## 5. Cold paths hide behind choices the auto-player never makes

A first-legal/greedy/leftmost auto-resolver **never Concedes, never Withdraws-when-it-could-Stand, never picks the rare option** — so the branches those choices unlock are untested even by millions of fuzz steps. The "loser survives → Retreat" path is the textbook case (it only fires when a battle ends with the loser's units alive, i.e. after a Concede or a round-cap).

**Exercise the cold paths deliberately:**

- Fuzz with a **random** or **scripted-adversarial** policy, not just first-legal. Nevsky's greedy self-play sweep was clean for ~15 rounds; an *aggressive* agent that pursued combat/capabilities immediately surfaced fresh bugs.
- Add explicit reproductions that force Concede / early termination / the rarely-chosen option, with your invariants active.

---

## 6. Different decision-makers find different bugs — rotate them

This was the strongest empirical pattern of the whole effort. Holding the engine fixed, each new *kind* of player surfaced bugs the previous ones never reached:

| Player | What it found |
|---|---|
| Scripted **greedy** self-play (300 games) | clean — walked too narrow a path |
| Scripted **aggressive/strategic** agent | a batch of over-enumerations (combat, capabilities) |
| **Claude** full playthrough (longest scenario) | 4 material bugs in rarely-walked corners |
| **GPT-5.5** playthrough (first run) | 2 more over-enumerations + a sharp architecture report |
| Even a **deterministic mock** decider | 2 over-enumerations (it favored actions other agents deprioritized) |

Practical implication: make the harness **model-agnostic at the interface** (a plain-text per-side briefing + a numbered legal-action list in, an index or action-dict out — no model-specific assumptions). Then drive it with several models/policies. The cost of a second model is near zero and the marginal bug yield is high.

---

## 7. A clause-by-clause rules audit catches what no trajectory will

Behavioral testing only exercises *reachable* trajectories. A **static, clause-by-clause pass** — read every numbered rule in the reference, map it to the code that implements it and the test that proves it, and log every clause with no mapping — is the one lens that doesn't depend on an agent walking into the corner.

On Nevsky this found the **Papal Legate Command +1 bonus**: a real, default-active rule that was *entirely unimplemented* and even *explicitly denied* by a stale code comment — and that ~100+ agent games had never hit because the engine simply never offered it. Do this pass once per reference document; it's a complement to, not a replacement for, fuzzing.

---

## 8. When two authoritative references conflict, adjudicate — don't guess

Reference documents disagree. Nevsky's Feed scope was specified two ways: a glossary + rules-reference gave a closed list of "Moved/Fought" actions (March/Avoid/Battle/Siege/Storm/Sail), while a one-line note in another file said "any acted Lord." The engine had followed the loose note, producing a starvation spiral (a garrison couldn't Tax its own city without starving — the *symptom* was the tell). The right move was to surface it as an explicit open question with the consultation log and let the human adjudicate, not to silently pick a reading. Keep a permanent decision log so the call (and its citation) is never re-litigated.

---

## 9. Operational enablers worth copying

- **RNG-in-state** (see §2): the precondition for cheap validation, lookahead, and reproducibility. Highest-value architectural choice.
- **Structured anomaly logging.** The agent driver catches `IllegalAction`/exceptions/stalls, records a structured finding (kind, turn, action, reason, side, box), applies a safe fallback, and keeps the game alive. This turns "the model seemed to make a mistake mid-game" into a clean triage queue you can hand back. It is what made remote/async LLM playtests productive.
- **A "find → fix-root → regression-test → re-run" loop per finding.** Every bug above became a numbered round: branch → fix → add a *negative* test (assert the enumerator does *not* offer the bad move, not just that the handler rejects it) → run the full battery → merge. Negative enumerator tests are the ones that actually guard this bug class.
- **Keep both a fast path and a correct path.** Fast unvalidated enumeration for hot loops; validated enumeration for the agent-facing menu. Don't make one serve both.

---

## 10. A self-check checklist for your engine

1. Can you point to the line where a *losing surviving* Lord's **map position** changes on Retreat? (Not just a service/initiative track.) Are the destination constraints enforced, and does the approach breadcrumb survive to the loss step?
2. Is your Siege/Bypass-marker clear-sweep invoked on **March-out, Disband, Removal, and Bypass-move** — and does it clear the inside unit's besieged flag, including for an **empty** Stronghold?
3. Does **every** placement path share one eligibility gate that rejects enemy-occupied/besieged/Conquered destinations, and place exception-units *inside* with capacity honored?
4. Do you have an **always-on co-location invariant** (keyed on the inside flag, excluding pending combat and any bypass)? Plus VP-cap / marker-bound invariants?
5. Does your auto-resolver ever **Concede / early-terminate / pick the rare option**? If not, schedule a random-policy fuzz pass with the invariants active.
6. Is your **RNG in the state** so you can deep-copy-and-probe without corrupting the real game?
7. Is there a **validated agent-facing palette** that filters handler-rejected moves and logs them?
8. Have you done a **clause-by-clause** pass of each reference doc, logging unmapped clauses?
9. For every fix, is there a **negative enumerator test** (menu does not offer the illegal move), not only a handler-rejection test?
10. Do your "advertised" dev/test dependencies actually install the full suite? (A property-test dependency missing from the dev extras silently disables coverage.)

---

*Happy to share concrete diffs, the validated-palette implementation, the co-location invariant, or the model-agnostic play interface on request.*
