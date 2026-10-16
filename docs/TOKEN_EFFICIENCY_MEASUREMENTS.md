# Measured helper output — October 16, 2026

Baseline source: `51f73b98110dedf864fb2616ab133a19acbfbe0d` (the actual previous helper).
Baseline helper SHA256: `2d89e5524119acb8b3684a10f1a34aea9584ac14fdee99e45527159419d6c06d`.
New helper SHA256: `d0c5304e0e03e1b139268c04a9f19bafb84a2f8c1edfd98143b835f9b2cda28e`.

## Method and scope

Six fixed 32–40-decision windows cover an established Crusade recruitment position and Return of the Prince opening Levy, planning/Command, midgame Feed/Pay/Disband, combat/interrupts and scenario end. Each workflow replays the same **208 recorded decisions**, with both sides represented. The two workflows are not independent game samples. Both old and new helpers must reach exactly the same state after every action, including dice and history.

Counts include the initial view, every post-action position/result, every fetched menu page and selected-entry metadata request, full printed card reference tips, scheduled Lord/Supply details, combat results, and a full player-filtered state/history plus victory detail at the start of each window. Equal strategic detail is printed for both interfaces; the old helper uses an explicit manual detail wrapper where it had no convenience function. Its missing original templates are also fetched in exhaustive mode. Nothing is truncated to achieve a target.

**Focused** requests the category containing the intended recorded action, paging until that entry is visible. **All pages** inspects the entire catalog at every decision. Neither needs a separate menu request when the new overview already prints its sole complete entry. The chosen actions are recorded inputs, not choices newly made by an LLM; this measures an explicit browsing protocol, not comprehension, playing strength or latency.

Tokens are counted separately for each response with the named tokenizer. They exclude message envelopes, tool schemas and network metadata; they are not a claim about the exact tokenizer or bill of any particular model. Random-looking fixed test namespaces have the same length as production IDs. Primary output excludes implicit notebook echoes (as with assignment or semicolon suppression). The separate notebook total includes a Python repr of each returned value, modeling bare notebook calls. It is not added when the caller suppresses those echoes.

## Aggregate response output

A positive saving means fewer output tokens. Negative values are a cost, not a failed correctness gate.

| Workflow | Tokenizer | Old stdout tokens | New stdout tokens | Saving | Old stdout + notebook echo | New stdout + notebook echo | Saving |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| focused | cl100k_base | 475,709 | 436,319 | 8.28% | 576,064 | 442,090 | 23.26% |
| focused | o200k_base | 477,301 | 438,273 | 8.18% | 577,339 | 444,044 | 23.09% |
| all_pages | cl100k_base | 477,739 | 508,154 | -6.37% | 578,094 | 514,794 | 10.95% |
| all_pages | o200k_base | 479,431 | 512,220 | -6.84% | 579,469 | 518,860 | 10.46% |

## Interaction and character counts

| Workflow | Decisions | Old calls | New calls | Extra calls | New menu-page requests | Old stdout characters | New stdout characters | Saving |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| focused | 208 | 253 | 369 | 116 | 116 | 1,446,343 | 1,309,392 | 9.47% |
| all_pages | 208 | 279 | 448 | 169 | 195 | 1,452,932 | 1,490,390 | -2.58% |

All common detail and result follow-ups are included in those call totals. There is no assertion that more calls are free: they can add latency and input tokens. The JSON records request text and its tokens separately. That text excludes one-time Python setup/manual-wrapper definitions and is not a complete API input-token bill.

## Per-window results

| Workflow | Window | Seed | Prefix actions | Decisions | Old stdout tokens | New stdout tokens | Saving |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| focused | campaign_recruitment | 20261011 | 462 | 40 | 118,243 | 95,595 | 19.15% |
| focused | opening_levy | 20261028 | 2 | 40 | 58,877 | 51,995 | 11.69% |
| focused | plan_and_command | 20261029 | 27 | 32 | 48,545 | 49,168 | -1.28% |
| focused | midgame_feed_pay | 20261028 | 287 | 32 | 69,323 | 68,657 | 0.96% |
| focused | combat_interrupt | 20261030 | 320 | 32 | 85,934 | 78,024 | 9.20% |
| focused | scenario_end | 20261029 | 763 | 32 | 96,379 | 94,834 | 1.60% |
| all_pages | campaign_recruitment | 20261011 | 462 | 40 | 118,383 | 135,836 | -14.74% |
| all_pages | opening_levy | 20261028 | 2 | 40 | 58,932 | 61,396 | -4.18% |
| all_pages | plan_and_command | 20261029 | 27 | 32 | 49,046 | 51,656 | -5.32% |
| all_pages | midgame_feed_pay | 20261028 | 287 | 32 | 69,800 | 72,917 | -4.47% |
| all_pages | combat_interrupt | 20261030 | 320 | 32 | 86,015 | 91,472 | -6.34% |
| all_pages | scenario_end | 20261029 | 763 | 32 | 97,255 | 98,943 | -1.74% |

Per-window token counts use `o200k_base`.

## Interpretation and reproduction

The benefit depends on how much of the action catalog a player inspects. Compact categories and a focused page avoid repeating unrelated actions; versioned IDs, richer visible resources, parameter metadata and page headers themselves cost output. Exhaustive browsing can therefore be larger than a flat menu, particularly for small menus. Keeping all parameters and supplying a fresh position take precedence over a fixed percentage target. Full-state/history requests are deliberately costly and their entire output is counted. No change-only baseline was introduced.

The notebook benefit additionally removes accidental duplication of the returned legacy list: the list data remains intact, but its implicit repr is short. It should not be attributed to the new interface when the old caller already suppressed repr output.

```sh
python -m pip install tiktoken
PYTHONPATH=src python scripts/benchmark_helper_output.py \
  --require-tokenizer --output /tmp/helper-benchmark
python scripts/report_helper_measurements.py \
  /tmp/helper-benchmark/measurements.json --output /tmp/helper-report.md
```

`reports/token_interface_20261016/measurements.json` retains the measured values and provenance. The validation artifact also contains the full before/after response logs for each sequence and workflow.

## Completed verification

- Full Python 3.12 suite on GitHub Actions: **1,884 passed**, zero failures, errors or skipped cases, checked from JUnit XML.
- Independent local Python 3.13.5 suite: **1,884 passed**, zero failures, errors or skipped cases.
- **69 new interface regression cases**; all 1,815 existing tests retained.
- **150 of 150** completion-required self-play invariant cases reached Game End without violations or step-limit exits on both environments.
- One complete **860-action Return of the Prince game** (two setup plus 858 interface-selected actions), with every action selected by a state-bound ID, exact comparison after each action and nine periodic save/resume checks.
- Each benchmark pair matched exactly after every action across both browsing protocols, with all follow-up output counted.
- Targeted Ruff, Python compilation and `git diff --check` passed.
- No existing rules handler, legal generator, validator, game-state schema, or LLMSession function was modified. The browser retains all legacy menu entries plus original parameterized templates.

These checks establish the tested interface contracts and trajectories, not a proof about every possible game position or an assessment of LLM strategy.

GitHub validation run: `38861034079`. Artifact: `nevsky-interface-validation`.
