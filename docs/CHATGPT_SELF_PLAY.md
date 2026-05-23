# Playing Nevsky-Harness with ChatGPT (or any OpenAI model)

`scripts/openai_self_play.py` lets an OpenAI chat model play the harness
autonomously, BOTH sides, turn by turn — the same model-agnostic LLM
interface Cowork-Claude uses (per-side natural-language briefing + a
numbered list of concrete legal actions; the model replies with one
index). A different model walks different trajectories and surfaces
different bugs (this is how the original Crusade playthrough found
SMOKE-134..137; the driver itself found SMOKE-156 on its first mock run).

## Run it (needs network + an OpenAI key)
```
export OPENAI_API_KEY=sk-...
pip install openai
PYTHONPATH=src python3 scripts/openai_self_play.py crusade_on_novgorod \
    --seed 1 --model gpt-4o --max-turns 6000 \
    --state docs/chatgpt_crusade_seed1.json \
    --findings docs/chatgpt_crusade_seed1.findings.json
```
- `--model` any OpenAI chat model (gpt-4o, gpt-4.1, o-series, ...).
- `--state` checkpoints the game every 25 turns (resumable artifact).
- `--findings` writes the full result + every anomaly as JSON.

## What it captures (so a run is a smoke test, not just a game)
Each turn, after applying the model's chosen action, it records:
- `illegal_concrete_action` — a numbered (concrete) action the handler
  rejected = an enumerator/handler mismatch (over-enumeration).
- `exception` — an unhandled engine error (with traceback excerpt).
- `no_legal_moves` — a stall/deadlock.
- `invariant` — co-location of opposing un-besieged Lords (R217/R218),
  VP over the 17.5 cap, or negative VP.
The process exit code is non-zero if any notable finding occurred.

## Smoke-test the DRIVER without a key (deterministic decider)
```
PYTHONPATH=src python3 scripts/openai_self_play.py watland --seed 1 --mock --max-turns 6000
```
`--mock` swaps the API call for a deterministic action-picker, so the
loop / parsing / instrumentation can be exercised offline (CI-friendly).

## Notes
- Hidden info is respected: each turn only the active side's briefing and
  legal actions are computed.
- The model chooses by INDEX into the concrete legal list, so its choice
  is always a legal move; the value is the fresh trajectories it walks,
  and the instrumentation flags any engine defect along the way.
- If the model returns an unparseable / out-of-range choice, the driver
  applies the phase-appropriate safe fallback and continues.
