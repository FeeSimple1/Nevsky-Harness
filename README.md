# Nevsky Harness

Python harness for GMT's *Nevsky: Teutons and Rus in Collision, 1240-1242*
(2nd Edition). Holds full game state, validates and resolves every
rules-defined action, runs Battle and Storm engagements automatically,
rolls all dice from a seeded RNG, and exposes a structured interface
designed to be consumed by an LLM playing one or both sides.

The detailed project specification lives in [`BRIEF.md`](BRIEF.md). The
material below is an operator's guide to the codebase as it stands at
the current `main` tip.

## Where things are

The harness itself is in `src/nevsky/`. The state model is Pydantic
(`state.py`); per-action handlers are in `actions.py` and `campaign.py`;
the enumerator that produces the move palette is `legal_moves.py`. Card
event resolvers are in `events.py`. Scenario loaders and victory math
live in `scenarios.py`. Static reference data (Lord stats, Locale
metadata, card text, the Ways graph) is under `src/nevsky/data/` as
JSON.

The LLM-play interface is in `src/nevsky/llm/` — hidden-information
filter, ~3 KB curated briefing, on-demand lookups for cards / strategy
/ AoW Reference text, and an `LLMSession` that holds state and routes
actions through the same handlers as everything else. The companion
system prompt is in [`LLM_PLAY_GUIDE.md`](LLM_PLAY_GUIDE.md).

`scripts/` holds the agents and sweeps:

The greedy `self_play.py` runs a deterministic priority-ranked agent
that drives a single game to terminal. The `strategic_agent.py` is a
combat-aggressive variant tuned to exercise battle paths the greedy
agent avoids. The `roundtrip_sweep.py` is the round-trip audit from
`CROSS_PROJECT_LESSONS.md` §2 — at every state visited by self-play,
it probes every emitted move through `apply_action` on a snapshot and
reports any divergences. The `agent_compare_sweep.py` runs greedy vs
strategic across all scenarios. The `llm_tournament.py` runs
configurable agents head-to-head and emits a leaderboard.

## How to run things

Install in editable mode and run the tests:

```
pip install -e ".[dev]"
PYTHONPATH=src pytest -q
```

Test count at the current tip is 1241 (one skip). The full suite runs
in roughly 25-40 seconds depending on machine. For larger machines,
install the `parallel` extra (`pip install -e ".[parallel]"`) and run
`pytest -n auto` for parallel execution. On a 2-core VM xdist's
worker-startup overhead exceeds the parallelism benefit, but on 4+
cores it's a real speedup.

Self-play one scenario:

```
PYTHONPATH=src python3 scripts/self_play.py pleskau --seed 1
```

Round-trip sweep across all scenarios:

```
PYTHONPATH=src python3 scripts/roundtrip_sweep.py --seeds 1,2,3
```

Tournament across all four built-in agents:

```
PYTHONPATH=src python3 scripts/llm_tournament.py
```

Real-LLM play uses `src/nevsky/llm/session.py`'s `LLMSession.start_new`
plus `legal_actions` / `apply` / `briefing` / `lookup_*` — see
`LLM_PLAY_GUIDE.md` for the calling conventions.

## Documentation map

The following files in the repo root are the durable artifacts:

[`BRIEF.md`](BRIEF.md) — the project specification: scope constraints,
authoritative sources priority, what counts as a rules ambiguity and
the consultation chain for resolving one.

[`RULES_DECISIONS.md`](RULES_DECISIONS.md) — adjudicated rules calls
with the user's verbatim answer, citation, and commit hash where the
decision is encoded. Decisions are permanent; nothing is ever deleted.

[`RULES_QUESTIONS.md`](RULES_QUESTIONS.md) — open rules questions
awaiting user adjudication. Currently empty.

[`SMOKE_TEST_FINDINGS.md`](SMOKE_TEST_FINDINGS.md) — append-only log of
every SMOKE finding (currently 128) with round-by-round context. The
SMOKE numbering is the institutional memory of every bug surfaced and
how it was fixed.

[`FUTURE_PROJECTS_LESSONS.md`](FUTURE_PROJECTS_LESSONS.md) — long-form
catalog of 14 audit patterns observed across the project (dead-code
surfaces, mirror gaps, state-set-but-unreachable, rule-cite-but-no-
enforce, lifecycle leaks, etc.).

[`CROSS_PROJECT_LESSONS.md`](CROSS_PROJECT_LESSONS.md) — executive
summary of the seven highest-yield insights from this project,
targeted at sibling L&C harnesses (Almoravid, Inferno) and future
ports. Pulls in code-shape examples lifted from the Nevsky source.

[`STRATEGY_DIGEST.md`](STRATEGY_DIGEST.md) — notes on game-strategy
patterns observed during self-play sweeps. Useful as briefing material
for an LLM playing the game.

[`LLM_PLAY_GUIDE.md`](LLM_PLAY_GUIDE.md) — system prompt and calling
convention for an LLM driving the harness via the `src/nevsky/llm/`
module.

[`PASS_2_SUMMARY.md`](PASS_2_SUMMARY.md) — close-out summary of the
Pass 2 verification effort (10-consecutive-clean-rounds protocol that
ran from R131 through R140).

[`docs/llm_interface_playthrough.md`](docs/llm_interface_playthrough.md)
— annotated transcript of a full Pleskau game played through the LLM
interface, demonstrating end-to-end correctness.

## Recent rounds

The harness has been through 193 rounds of bug-hunting at the time of
this writing. The most recent arc focused on the LLM-play surface and
the enumerator/handler round-trip audit:

R188 added the LLM-play interface end-to-end playthrough and SMOKE-122
(cmd_ravage own-territory filter, surfaced by the playthrough).

R189 wrote the cross-project lessons document — the executive-summary
companion to FUTURE_PROJECTS_LESSONS.md, targeted at sibling harnesses.

R190 implemented the round-trip enumerator/handler sweep recommended in
CROSS_PROJECT_LESSONS §2 and used it to surface six new SMOKEs
(123-128: T13/Heinrich, aow_implement_card-needs-lord_id,
cmd_tax/forage/march filters). Pre-fix sweep: 456 findings; post-fix:
0.

R191 converted the sweep into a pytest CI gate
(`test_round_191_roundtrip_property.py`) so the SMOKE-118/119/122/
123..128 enumerator family can never silently regress, and verified
that the R187 1-of-300 stuck case was transitively fixed by R190.

R192 added the LLM-vs-LLM tournament harness with four built-in
agent personas. Plug a real LLM in by implementing the same
`pick(state, side, recent) -> action` interface.

R193 closed out Q-R190-A: when a `this_lord` Capability is drawn at
first Levy with no Mustered eligible Lord, the handler now auto-
discards to `deck.discard` (preserving the card's Event half for later
Levies). Resolves the pleskau-R11 stall and the canonical
Watland-Druzhina-Domash-only case in one path.

R194 refreshed this README to reflect R188-R193 and added the
`parallel` dev extra for pytest-xdist.

Test count trajectory across this arc: 1213 → 1241. SMOKE total:
121 → 128.

## Provenance

This is a private project. Code quality is sufficient for the user to
maintain; it is not optimized for external readers. Per the BRIEF, the
authoritative rules sources in priority order are the 2nd Edition
Changes document, the curated `.txt` references in the source tree
(the FIRST stop for any card or capability question — the Tips
sections in particular contain Volko Ruhnke's clarifications), the
Rules of Play PDF, and the Playbook PDF (examples only, not a rules
source).
