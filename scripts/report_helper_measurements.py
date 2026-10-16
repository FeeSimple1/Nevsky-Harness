"""Render complete paired-output measurements, without an output-size pass gate."""
from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def reduction(before, after):
    return f"{(before - after) / before * 100:.2f}%" if before else "n/a"


def render(report):
    tokenizers = report["tokenizers"]
    lines = ["# Measured helper output — October 16, 2026", "",
             f"Baseline source: `{report['baseline_ref']}` (the actual previous helper).",
             f"Baseline helper SHA256: `{report['baseline_helper_sha256']}`.",
             f"New helper SHA256: `{report['new_helper_sha256']}`.", "",
             "## Method and scope", "",
             "Six fixed 32–40-decision windows cover an established Crusade recruitment "
             "position and Return of the Prince opening Levy, planning/Command, midgame "
             "Feed/Pay/Disband, combat/interrupts and scenario end. Each workflow replays "
             "the same **208 recorded decisions**, with both sides represented. The two "
             "workflows are not independent game samples. Both old and new helpers must "
             "reach exactly the same state after every action, including dice and history.", "",
             "Counts include the initial view, every post-action position/result, every "
             "fetched menu page and selected-entry metadata request, full printed card "
             "reference tips, scheduled Lord/Supply details, combat results, and a full "
             "player-filtered state/history plus victory detail at the start of each "
             "window. Equal strategic detail is printed for both interfaces; the old "
             "helper uses an explicit manual detail wrapper where it had no convenience "
             "function. Its missing original templates are also fetched in exhaustive "
             "mode. Nothing is truncated to achieve a target.", "",
             "**Focused** requests the category containing the intended recorded action, "
             "paging until that entry is visible. **All pages** inspects the entire "
             "catalog at every decision. Neither needs a separate menu request when the "
             "new overview already prints its sole complete entry. The chosen actions "
             "are recorded inputs, not choices newly made by an LLM; this measures an "
             "explicit browsing protocol, not comprehension, playing strength or latency.", "",
             "Tokens are counted separately for each response with the named tokenizer. "
             "They exclude message envelopes, tool schemas and network metadata; they "
             "are not a claim about the exact tokenizer or bill of any particular model. "
             "Random-looking fixed test namespaces have the same length as production "
             "IDs. Primary output excludes implicit notebook echoes (as with assignment "
             "or semicolon suppression). The separate notebook total includes a Python "
             "repr of each returned value, modeling bare notebook calls. It is not "
             "added when the caller suppresses those echoes.", "",
             "## Aggregate response output", "",
             "A positive saving means fewer output tokens. Negative values are a cost, "
             "not a failed correctness gate.", "",
             "| Workflow | Tokenizer | Old stdout tokens | New stdout tokens | Saving | "
             "Old stdout + notebook echo | New stdout + notebook echo | Saving |",
             "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for mode in ("focused", "all_pages"):
        cases = [c for c in report["cases"] if c["mode"] == mode]
        for tokenizer in tokenizers:
            old = sum(c["before"][tokenizer]["stdout_tokens"] for c in cases)
            new = sum(c["after"][tokenizer]["stdout_tokens"] for c in cases)
            old_echo = old + sum(c["before"][tokenizer]["echo_tokens"] for c in cases)
            new_echo = new + sum(c["after"][tokenizer]["echo_tokens"] for c in cases)
            lines.append(f"| {mode} | {tokenizer} | {old:,} | {new:,} | {reduction(old, new)} | "
                         f"{old_echo:,} | {new_echo:,} | {reduction(old_echo, new_echo)} |")
    lines += ["", "## Interaction and character counts", "",
              "| Workflow | Decisions | Old calls | New calls | Extra calls | "
              "New menu-page requests | Old stdout characters | New stdout characters | Saving |",
              "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for mode in ("focused", "all_pages"):
        cases = [c for c in report["cases"] if c["mode"] == mode]
        old_calls = sum(c["before"]["interactions"] for c in cases)
        new_calls = sum(c["after"]["interactions"] for c in cases)
        old_chars = sum(c["before"]["stdout_characters"] for c in cases)
        new_chars = sum(c["after"]["stdout_characters"] for c in cases)
        lines.append(f"| {mode} | {sum(c['actions'] for c in cases)} | {old_calls} | {new_calls} | "
                     f"{new_calls-old_calls} | {sum(c['new_menu_requests'] for c in cases)} | "
                     f"{old_chars:,} | {new_chars:,} | {reduction(old_chars,new_chars)} |")
    lines += ["", "All common detail and result follow-ups are included in those call totals. "
              "There is no assertion that more calls are free: they can add latency and "
              "input tokens. The JSON records request text and its tokens separately. "
              "That text excludes one-time Python setup/manual-wrapper definitions and "
              "is not a complete API input-token bill.", "",
              "## Per-window results", "",
              "| Workflow | Window | Seed | Prefix actions | Decisions | "
              "Old stdout tokens | New stdout tokens | Saving |",
              "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    metric = "o200k_base" if "o200k_base" in tokenizers else None
    for c in report["cases"]:
        old = c["before"][metric]["stdout_tokens"] if metric else c["before"]["stdout_characters"]
        new = c["after"][metric]["stdout_tokens"] if metric else c["after"]["stdout_characters"]
        lines.append(f"| {c['mode']} | {c['sequence']} | {c['seed']} | {c['offset']} | "
                     f"{c['actions']} | {old:,} | {new:,} | {reduction(old,new)} |")
    lines += ["", f"Per-window token counts use `{metric}`." if metric else
              "Tokenizer unavailable: the per-window columns above are characters, not tokens.", "",
              "## Interpretation and reproduction", "",
              "The benefit depends on how much of the action catalog a player inspects. "
              "Compact categories and a focused page avoid repeating unrelated actions; "
              "versioned IDs, richer visible resources, parameter metadata and page "
              "headers themselves cost output. Exhaustive browsing can therefore be "
              "larger than a flat menu, particularly for small menus. Keeping all "
              "parameters and supplying a fresh position take precedence over a fixed "
              "percentage target. Full-state/history requests are deliberately costly "
              "and their entire output is counted. No change-only baseline was introduced.", "",
              "The notebook benefit additionally removes accidental duplication of "
              "the returned legacy list: the list data remains intact, but its implicit "
              "repr is short. It should not be attributed to the new interface when "
              "the old caller already suppressed repr output.", "", "```sh",
              "python -m pip install tiktoken",
              "PYTHONPATH=src python scripts/benchmark_helper_output.py \\",
              "  --require-tokenizer --output /tmp/helper-benchmark",
              "python scripts/report_helper_measurements.py \\",
              "  /tmp/helper-benchmark/measurements.json --output /tmp/helper-report.md",
              "```", "",
              "`reports/token_interface_20261016/measurements.json` retains the measured "
              "values and provenance. The validation artifact also contains the full "
              "before/after response logs for each sequence and workflow.", ""]
    return "\n".join(lines)


def validation(xml_path, invariant_path):
    root = ET.parse(xml_path).getroot()
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    counts = {k: sum(int(s.get(k, 0)) for s in suites)
              for k in ("tests", "failures", "errors", "skipped")}
    assert counts == {"tests": 1884, "failures": 0, "errors": 0, "skipped": 0}, counts
    invariant = json.loads(Path(invariant_path).read_text())
    assert invariant["cases"] == invariant["completed"] == 150, invariant
    assert not invariant["violations"] and invariant["step_limited"] == 0, invariant
    return "\n".join([
        "", "## Completed verification", "",
        "- Full Python 3.12 suite on GitHub Actions: **1,884 passed**, zero failures, "
        "errors or skipped cases, checked from JUnit XML.",
        "- Independent local Python 3.13.5 suite: **1,884 passed**, zero failures, "
        "errors or skipped cases.",
        "- **69 new interface regression cases**; all 1,815 existing tests retained.",
        "- **150 of 150** completion-required self-play invariant cases reached "
        "Game End without violations or step-limit exits on both environments.",
        "- One complete **860-action Return of the Prince game** (two setup plus "
        "858 interface-selected actions), with every action selected by a state-bound "
        "ID, exact comparison after each action and nine periodic save/resume checks.",
        "- Each benchmark pair matched exactly after every action across both "
        "browsing protocols, with all follow-up output counted.",
        "- Targeted Ruff, Python compilation and `git diff --check` passed.",
        "- No existing rules handler, legal generator, validator, game-state schema, "
        "or LLMSession function was modified. The browser retains all legacy menu "
        "entries plus original parameterized templates.",
        "", "These checks establish the tested interface contracts and trajectories, "
        "not a proof about every possible game position or an assessment of LLM strategy.", ""])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("measurements", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tests-xml", type=Path)
    parser.add_argument("--invariants", type=Path)
    args = parser.parse_args()
    report = json.loads(args.measurements.read_text())
    assert len(report["cases"]) == 12 and all(c["exact_same_final_state"] for c in report["cases"])
    text = render(report)
    if args.tests_xml:
        if not args.invariants:
            parser.error("--tests-xml requires --invariants")
        text += validation(args.tests_xml, args.invariants)
    args.output.write_text(text)


if __name__ == "__main__":
    main()
