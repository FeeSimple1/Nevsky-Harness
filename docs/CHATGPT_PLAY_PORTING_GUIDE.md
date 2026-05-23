# Porting the "ChatGPT plays your harness" bug-hunt to your L&C engine

**Audience:** maintainers of sibling L&C rules-engines (Almoravid, Inferno, Seljuk, …).
**What this enables:** zip your harness, upload it to a ChatGPT Project, and let ChatGPT (GPT‑5.x) **play it in its own Python sandbox** — no API key, no network — while a baked-in instrumentation layer auto-captures every engine anomaly (illegal action, crash, stall, broken invariant). It's the same setup Nevsky used; a *different model walking different trajectories* is what surfaces bugs scripted sweeps miss.

Two files ship with this guide:
- `chatgpt_play_helper_TEMPLATE.py` — a harness-agnostic helper; you fill in ~6 adapter functions.
- this guide.

Companion: `LC_HARNESS_ADVISORY.md` explains *why* (the bug classes). This explains *how* (the wiring).

---

## The model in one paragraph

ChatGPT itself is the player. It runs your harness in its sandbox, calls `nv.show()` to see the active side's briefing + a **numbered list of legal actions**, decides, calls `nv.apply(N)`, and loops. The helper validates every offered action against your executor on a throwaway copy, so the model is **never shown an illegal move**, and any filtered move is logged as a bug. At the end, `nv.findings_report()` prints the triage queue you collect.

You do **not** need the `openai_self_play.py`-style API driver — that's for headless local runs and would mean ChatGPT calling itself.

---

## What your harness must expose (the contract)

The helper needs five primitives. Most L&C engines already have all of them; you just wire them into the ADAPTER block at the top of `chatgpt_play_helper_TEMPLATE.py`.

1. **`load_scenario(scenario_id, seed) -> state`** and a `SCENARIO_IDS` collection. Deterministic from the seed.
2. **`briefing_for_side(state, side) -> str`** — a natural-language summary of the current position **for that side only** (respect hidden information). If you don't have one, a plain dump of that side's Lords/forces/VP/phase is enough to start.
3. **`legal_actions_for_side(state, side) -> list[dict]`** — every legal action for `side`, each a dict `{"type": str, "args": dict, ...}`, **concrete** (expand any templated/parameterized moves here) and **hidden-info-filtered**. This is the menu the model picks from.
4. **`apply_action(state, {"type","side","args"})`** — applies in place; raises a typed `IllegalAction` on an illegal move (a *normal* rejection, not a crash).
5. **`is_terminal(state) -> bool`** (and optionally `determine_winner(state)`).

Plus two small adapters: `active_side(state)`, and `deep_copy(state)` (see the RNG note — it's the one real prerequisite).

If your enumerator and executor are *the same code path*, great — but they almost never are, and the gap between them is the #1 bug class (see the advisory). The validated palette below turns that gap from a player-facing failure into a logged diagnostic.

---

## §RNG — the one real prerequisite

The validated palette works by `deep_copy(state) → apply candidate → discard`. That is only safe if the **RNG is part of the state**, so mutating the copy can't perturb the real game's dice.

- **If your RNG lives in the state** (e.g. a `seed` + an incrementing counter, with each roll a pure function of them — Nevsky does this): a structural deep copy isolates it perfectly. `deep_copy` = `state.model_copy(deep=True)` (pydantic v2) or `copy.deepcopy(state)`. Keep `VALIDATE = True`.
- **If your RNG is a module global** (`random.random()` etc.): a deep copy will **not** isolate it, and validation would advance the real dice. Either (a) refactor the RNG into the state (strongly recommended — it also unlocks reproducibility and lookahead), or (b) set `VALIDATE = False` in the adapter and rely on apply-time catching (you lose the "never show an illegal move" guarantee, but the loop and findings still work).

This is the single most important architectural check. If you're unsure, grep your action handlers for how a die roll is obtained.

---

## §Invariants — paste and adapt the co-location check

`invariants(state)` runs after every applied action and returns a list of violation strings. The canonical L&C invariant (from Inferno, confirmed across engines) is: **no Locale holds opposing mustered units, both outside a Stronghold, with no Approach/Battle pending.** Reference implementation to adapt:

```python
def invariants(state):
    out = []
    from collections import defaultdict
    by_loc = defaultdict(set)
    for u in your_mustered_units(state):                 # ADAPT: iterate on-map units
        if u.location is not None and not u.inside_stronghold:   # ADAPT field names
            by_loc[u.location].add(u.side)
    bad = [loc for loc, sides in by_loc.items() if len(sides) > 1]
    # exclude the locale where a battle/approach is mid-resolution (LEGAL transient):
    cp = getattr(state, "combat_pending", None)           # ADAPT
    if cp is not None:
        bad = [loc for loc in bad if loc != cp.to_locale] # ADAPT
    if bad:
        out.append(f"co_located_enemies:{bad}")
    # add edition-specific ones: VP within cap, markers in bounds, etc.
    return out
```

Notes that bit every engine:
- Key on the **per-unit "inside Stronghold" flag**, not on the presence of a Siege marker (besieged-inside vs besiegers-outside is legal).
- **Exclude the pending-combat locale** — a March creates contact one step before the defender responds; that co-location is legal and transient. Everyone hits this as a false positive first.
- If your edition has a **Bypass** flag, exclude bypassing units too.

Start with co-location + a VP-cap check; add more as you learn your engine's failure modes. It's fine to ship `invariants` returning `[]` and add them later, but the co-location one is high-yield — write it.

---

## Step-by-step

1. Copy `chatgpt_play_helper_TEMPLATE.py` into your repo as `scripts/chatgpt_play_helper.py`.
2. Edit the ADAPTER block: the 5 imports, `active_side`, `is_terminal`, `determine_winner`, `deep_copy`, `setup_actions` (any post-load setup confirmations; `[]` if none), `invariants`, and `VALIDATE`.
3. Smoke-test it locally (no ChatGPT needed) — a deterministic stand-in loop:
   ```python
   import sys; sys.path.insert(0, "src"); sys.path.insert(0, "scripts")
   import chatgpt_play_helper as nv
   nv.start("<your_shortest_scenario>", seed=1)
   for _ in range(50):
       acts = nv.auto()
       if not acts: break
       nv.apply(0)            # greedy stand-in for the model
   nv.findings_report()
   ```
   This proves the wiring runs end to end and exercises the validator. (Nevsky's first such run immediately flagged a real over-enumeration.)
4. Zip the repo (runtime essentials: your `src/` package + `scripts/chatgpt_play_helper.py`; tests/docs not needed) and upload to a ChatGPT **Project**.
5. Paste the project instructions below.
6. Collect `nv.findings_report()` output after each session and triage the **notable** entries.

---

## ChatGPT Project instructions (paste into the Project's custom instructions)

> You are playtesting a GMT *Levy & Command* wargame via a Python rules engine in this project, working in your Python tool. Unzip the uploaded repo if needed, then run:
> ```python
> import sys; sys.path.insert(0, "src"); sys.path.insert(0, "scripts")
> import chatgpt_play_helper as nv
> nv.start("<SCENARIO_ID>", seed=1)
> ```
> Play turn by turn:
> - `nv.show()` prints the active side's briefing and a NUMBERED list of legal actions. You control BOTH sides; play each turn to win for whichever side is active. You only see the active side's information.
> - Decide, then `nv.apply(N)` to play action number N (or `nv.apply({"type":..., "args":{...}})` for a raw action).
> - `nv.auto()` fast-forwards purely-forced turns; call it between decisions to skip boilerplate.
> Play to win (advance on objectives, attack/siege, keep your forces supplied, use special capabilities); pass only when best.
> The harness auto-records any engine anomaly. Periodically and at the end, run `nv.findings_report()` and paste its output back to the maintainer — that list is the goal of the exercise.

(Replace `<SCENARIO_ID>` with one of your scenarios; start with your shortest.)

---

## What you get back

`nv.findings_report()` prints `N total, M notable`. Each **notable** entry is a real engine defect to triage:

- `over_enum_filtered` / `illegal_action` — the menu offered a move the executor rejects (enumerator/handler asymmetry — the dominant class).
- `exception` / `exception_in_probe` — applying an offered move *crashes* (worse than an illegal: a real engine bug).
- `no_legal_moves` — a stall/deadlock (the side had no legal action).
- `invariant` / `invariant_crash` — an illegal board state slipped through (e.g. co-located enemies).

For each, fix the **root** (don't just rely on the validator hiding it) and add a **negative test**: assert the *enumerator does not offer* the bad move, not only that the handler rejects it. See `LC_HARNESS_ADVISORY.md` for the bug-class breakdown and a self-check checklist.

---

## Practical tips

- **Start with your shortest scenario** (fewest decisions = fewest API turns) before a long campaign. Even a partial game finds bugs — Nevsky's first deep playthrough reached ~1/4 of a campaign and found four.
- **Vary the seed and re-run**, and try more than one model — different decision policies walk different trajectories.
- **The sandbox is ephemeral.** If the chat/sandbox resets, re-run the setup cell; `nv.save("game.json")` checkpoints.
- **Only dependency** should be whatever your engine already needs (Nevsky: just `pydantic`). ChatGPT's sandbox has no network, so if your engine needs a package the sandbox lacks, you'll need to vendor it or trim the import.
- **Long games run slower with validation** (a deep copy per candidate per turn). That's fine for interactive play; if you want a fast headless over-enum sweep instead, run your existing scripted/round-trip sweeps with the co-location invariant active.
