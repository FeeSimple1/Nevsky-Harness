# Have GPT-5.5 play Nevsky-Harness in a ChatGPT Project (no API key)

This is the key-free path: drop the repo into a ChatGPT **Project**, and
GPT-5.5 runs the harness in its own Python sandbox and decides every move
itself. (The `openai_self_play.py` driver is for *headless* local runs and
is NOT used here — when ChatGPT is the player, calling the API would be
calling itself.) Only dependency is `pydantic`, already in the sandbox.

## 1. Zip & upload
Zip the repo and upload it to the Project's files (or attach in a chat).
Runtime essentials, if you want a minimal zip: `src/` and `scripts/`
(the helper imports `scripts/llm_self_play.py` and `scripts/self_play.py`).
`reference/` is needed for full printed Arts of War tips and reference lookups;
include it for informed play. Tests and other docs are optional at runtime.

## 2. Project instructions (paste into the Project's custom instructions)
> You are playing the GMT game *Nevsky: Teutons and Rus in Collision* via
> a Python rules engine in this project. Work in your Python tool. First
> unzip the uploaded repo if needed, then run:
> ```python
> import sys; sys.path.insert(0, "src"); sys.path.insert(0, "scripts")
> import chatgpt_play_helper as nv
> nv.start("crusade_on_novgorod", seed=1)
> ```
> Then play turn by turn:
> - `nv.show()` prints a fresh compact position and category counts, not the
>   whole menu. You control BOTH sides, with each view filtered for its owner.
> - Browse the categories with `page = nv.actions("cmd_march", lord="hermann")`
>   or `nv.actions(page=2)`, using categories/pages actually available now.
>   Use `nv.action(ID)` to inspect the full entry and its parameter choices.
> - Decide, then `nv.apply(ID)` using the displayed state-bound identifier.
>   Templates require explicit `args={...}`. Old IDs reject without changing
>   state. Legacy integer/raw-dictionary calls remain available for scripts.
> - Use `nv.details("supply", lord=...)`, `nv.details("card", card_id=...)`, or
>   `nv.full_state()` for the owner's full information. `nv.result(full=True)`
>   returns all fields of the last result. Browse, do not infer missing choices.
> - `nv.auto()` fast-forwards genuinely forced actions but stops for templates,
>   candidate parameters and optional Hold interruptions. Inspect another
>   owner's interruption explicitly with `side="russian"` or `"teutonic"`.
> Play toward winning (March on objectives, Siege/Storm enemy Strongholds,
> Tax/Forage to stay supplied, use Capabilities); Pass only when best.
> The harness auto-records any engine anomaly (illegal action, exception,
> stall, or an illegal board state). Periodically, and at the end, run
> `nv.findings_report()` and paste its output back to the maintainer — that
> list is the whole point of the exercise.

## 3. Tips
- **Short scenario first:** `nv.start("pleskau", seed=1)` (~a few dozen
  decisions) before the full `crusade_on_novgorod` (long; many turns).
  Even a partial game surfaces bugs — the prior Claude playthrough only
  reached box 4 of 16 and still found 3.
- **Vary it:** different `seed=` values and re-runs walk different
  trajectories (that's where new bugs hide).
- **Sandbox is ephemeral:** if the chat/sandbox resets, re-run the setup
  cell; use `nv.save("game.json")` to checkpoint and `nv.load("game.json")` to
  resume. Loading prints a fresh position; request new action IDs.
- **What to send back:** the `nv.findings_report()` output. Anything under
  "notable" (illegal_concrete_action / exception / no_legal_moves /
  invariant) is a real engine defect to triage.

Full interface contract and examples: [TOKEN_EFFICIENT_INTERFACE.md](TOKEN_EFFICIENT_INTERFACE.md).
