"""Replay fixed play sequences through old/new helpers and count all output.

Counts initial briefing, automatic post-action display, every fetched menu page,
selected-action metadata, printed card rules, Lord/Supply detail and one full
state request per sequence. Both sides execute identical recorded actions.

Primary metric: stdout tokens (no notebook echo); also report notebook echoes,
request-text tokens and interaction counts. No wall-clock or win-rate claims.
The baseline source comes from git, not a reconstructed approximation.
"""
from __future__ import annotations

import argparse
import contextlib
import gzip
import hashlib
import io
import json
import subprocess
import sys
import types
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from nevsky.actions import apply_action  # noqa: E402
from nevsky.llm.action_browser import encode  # noqa: E402
from nevsky.llm.compact import detail_payload  # noqa: E402
from nevsky.scenarios import load_scenario  # noqa: E402

BASE_REF = "51f73b98110dedf864fb2616ab133a19acbfbe0d"


def module(text, name):
    result = types.ModuleType(name)
    result.__file__ = str(ROOT / "scripts/chatgpt_play_helper.py")
    exec(compile(text, result.__file__, "exec"), result.__dict__)
    if hasattr(result, "_BROWSER"):
        # Reproducible opaque IDs of normal production length, unrelated to dice.
        result._BROWSER._epoch = "c4Zp7q_R9mK2xB6v"
    return result


def envelope(a):
    return {k: v for k, v in a.items() if k in ("type", "side", "args")}


def call(log, request, function, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()) as capture:
        value = function(*args, **kwargs)
    log.append({"request": request, "stdout": capture.getvalue(),
                "notebook_echo": repr(value) + "\n" if value is not None else ""})
    return value


def manual_detail(payload):
    print(encode(payload))


def compatible(row, intended):
    entry = row["action"]
    if entry["type"] != intended["type"]:
        return False
    bound = entry.get("args")
    if isinstance(bound, dict):
        return all(intended["args"].get(k) == v for k, v in bound.items())
    # Leave final authority to ActionBrowser.resolve and the real handler.
    from nevsky.llm.action_browser import _literal
    return all(not _literal(v) or intended["args"].get(k) == v
               for k, v in entry.get("args_template", {}).items())


def windows():
    prefix = ROOT / "reports/return_prince_20261028"
    logs = {name: json.loads((prefix / name / "transcript.json").read_text())
            for name in ("logistics", "combined", "maritime")}
    plan = next(i for i, r in enumerate(logs["combined"])
                if r["action"]["type"] == "plan_add_card")
    mid = next(i for i, r in enumerate(logs["logistics"])
               if r["box"] >= 11 and r["action"]["type"] == "fpd_resolve")
    ambush = next(i for i, r in enumerate(logs["maritime"])
                  if r["action"]["type"] == "play_ambush_block")
    campaign = json.loads((ROOT / "tests/data/crusade_seed_20261011/ordered_replay.json").read_text())
    campaign_log = [{"action": a} for a in campaign["actions"]]
    recruitment = next(i for i, r in enumerate(campaign_log) if i >= 400 and r["action"]["type"] == "muster_lord")
    return [("campaign_recruitment", "crusade_logistics", campaign["seed"], recruitment, 40, campaign_log),
            ("opening_levy", "logistics", 20261028, 2, 40, logs["logistics"]),
            ("plan_and_command", "combined", 20261029, plan, 32, logs["combined"]),
            ("midgame_feed_pay", "logistics", 20261028, mid, 32, logs["logistics"]),
            ("combat_interrupt", "maritime", 20261030, ambush - 8, 32, logs["maritime"]),
            ("scenario_end", "combined", 20261029, len(logs["combined"]) - 32, 32, logs["combined"])]


def run_sequence(old_text, new_text, spec, mode):
    name, policy, seed, offset, length, transcript = spec
    scenario = "crusade_on_novgorod" if policy == "crusade_logistics" else "return_of_the_prince"
    state = load_scenario(scenario, seed=seed)
    for entry in transcript[:offset]:
        apply_action(state, deepcopy(entry["action"]))
    old, new = module(old_text, "old_helper"), module(new_text, "new_helper")
    for h in (old, new):
        h._S.update(state=state.model_copy(deep=True), scenario=scenario,
                    history=[], findings=[], turn=0)
    old_log, new_log = [], []
    for h, log in ((old, old_log), (new, new_log)):
        call(log, "show()", h.show)
    common_details = 0
    menu_calls = 0
    shown_side = new._active()
    for step, record in enumerate(transcript[offset:offset + length]):
        intended = deepcopy(record["action"])
        side = intended["side"]
        s = new._S["state"]
        _, _, catalog = new._BROWSER.catalog(s, side, new._validated)
        # Exact representative first; otherwise a bound action plus optional
        # args, then the original unexpanded template. No move pruning.
        exact = [r for r in catalog if envelope(r["action"]) == intended]
        candidates = exact or [r for r in catalog if compatible(r, intended)]
        if not candidates:
            raise AssertionError(f"No catalog representation: {name} {step} {intended}")
        target = candidates[0]
        if mode == "focused":
            filters = {"category": intended["type"], "side": side}
        else:
            filters = {"side": side}
            # The old helper omits originals of expanded templates. Charge the
            # old interface a follow-up to obtain those, to compare equal access.
            originals = [r["action"] for r in catalog if r["legacy_index"] is None]
            if originals:
                call(old_log, "inspect_original_templates()", manual_detail, originals)
        page = 1
        # show() already exposes a sole complete entry in full; no redundant
        # follow-up is charged where a human/LLM can directly copy that ID.
        found = len(catalog) == 1 and side == shown_side
        if not found:
            while True:
                request = "actions(" + ",".join(f"{k}={v!r}" for k, v in filters.items()) + f",page={page})"
                reply = call(new_log, request, new.actions, page=page, **filters)
                menu_calls += 1
                if any(r["id"] == target["id"] for r in reply["items"]):
                    found = True
                    if mode == "focused":
                        break
                if reply["next_page"] is None:
                    break
                page = reply["next_page"]
        assert found
        a = target["action"]
        if any(k not in ("type", "side", "args", "note", "optional") for k in a):
            call(new_log, f"action({target['id']!r},side={side!r})", new.action, target["id"], side=side)
            call(old_log, "inspect_selected_action_metadata()", manual_detail, a)
            common_details += 1
        topics = []
        if step == 0:
            topics += [("state", {}), ("victory", {})]
        lid = intended["args"].get("by_lord") or s.campaign_turn.active_lord
        if step % 12 == 0 and lid:
            topics.append(("lord", {"lord": lid}))
        if intended["type"] in ("cmd_supply", "cmd_march") and lid and step % 4 == 0:
            topics.append(("supply", {"lord": lid}))
        cid = intended["args"].get("card_id")
        if cid and intended["type"] in ("levy_capability", "aow_play_hold", "aow_lordship_plus_2"):
            topics.append(("card", {"card_id": cid}))
        if s.combat_pending is not None:
            topics.append(("combat", {}))
        for topic, kwargs in topics:
            # Equal strategic-detail payload on both interfaces; include every
            # byte of the full state/history, not a truncated approximation.
            payload = detail_payload(s, side, topic, **kwargs)
            call(old_log, f"detail({topic!r},side={side!r},{kwargs!r})", manual_detail, payload)
            call(new_log, f"details({topic!r},side={side!r},{kwargs!r})", new.details,
                 topic, side=side, **kwargs)
            common_details += 1
        old_palette = old._validated(old._S["state"], side, log_rejects=False)
        old_indices = [i for i, candidate in enumerate(old_palette)
                       if envelope(candidate) == intended]
        old_choice = old_indices[0] if old_indices else intended
        call(old_log, f"apply({old_choice!r},side={side!r})", old.apply, old_choice, side=side)
        supplied = {} if envelope(target["action"]) == intended else {"args": intended["args"]}
        request = f"apply({target['id']!r},side={side!r}" + (f",args={intended['args']!r}" if supplied else "") + ")"
        call(new_log, request, new.apply, target["id"], side=side, **supplied)
        shown_side = new._active()
        if intended["type"] in ("stand_battle", "cmd_storm", "cmd_sally", "play_ambush_block"):
            from nevsky.llm.compact import player_view
            event = player_view(old._S["state"], side)["history"][-1]
            payload = {"actor": event["actor"], "type": event["action"]["type"], "result": event["result"]}
            call(old_log, f"inspect_full_result(side={side!r})", manual_detail, payload)
            call(new_log, f"result(side={side!r},full=True)", new.result, side=side, full=True)
            common_details += 1
        if new._S["state"].model_dump() != old._S["state"].model_dump():
            raise AssertionError(f"Game divergence at {name} {step}")
    return {"sequence": name, "scenario": scenario, "policy": policy, "seed": seed,
            "offset": offset, "actions": length, "mode": mode,
            "new_menu_requests": menu_calls, "shared_detail_requests": common_details,
            "exact_same_final_state": True}, old_log, new_log


def measure(log, encoders):
    stdout = "".join(x["stdout"] for x in log)
    echo = "".join(x["notebook_echo"] for x in log)
    requests = "\n".join(x["request"] for x in log)
    data = {"interactions": len(log), "stdout_characters": len(stdout),
            "stdout_bytes": len(stdout.encode()), "notebook_echo_characters": len(echo),
            "request_characters": len(requests)}
    for name, enc in encoders.items():
        data[name] = {label: sum(len(enc.encode(item[key], disallowed_special=())) for item in log)
                      for label, key in (("stdout_tokens", "stdout"),
                                         ("echo_tokens", "notebook_echo"),
                                         ("request_tokens", "request"))}
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-ref", default=BASE_REF)
    parser.add_argument("--baseline-file", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-tokenizer", action="store_true")
    opts = parser.parse_args()
    old_text = (opts.baseline_file.read_text() if opts.baseline_file else
                subprocess.check_output(["git", "show", f"{opts.baseline_ref}:scripts/chatgpt_play_helper.py"],
                                        cwd=ROOT).decode())
    new_text = (ROOT / "scripts/chatgpt_play_helper.py").read_text()
    encoders = {}
    try:
        import tiktoken
        encoders = {name: tiktoken.get_encoding(name) for name in ("cl100k_base", "o200k_base")}
    except ImportError:
        if opts.require_tokenizer:
            raise
    opts.output.mkdir(parents=True, exist_ok=True)
    report = {"baseline_ref": opts.baseline_ref,
              "baseline_helper_sha256": hashlib.sha256(old_text.encode()).hexdigest(),
              "new_helper_sha256": hashlib.sha256(new_text.encode()).hexdigest(),
              "tokenizers": list(encoders), "cases": []}
    for mode in ("focused", "all_pages"):
        for spec in windows():
            meta, before, after = run_sequence(old_text, new_text, spec, mode)
            meta.update(before=measure(before, encoders), after=measure(after, encoders))
            report["cases"].append(meta)
            filename = f"{mode}_{spec[0]}.json.gz"
            with gzip.open(opts.output / filename, "wt") as out:
                json.dump({"before": before, "after": after}, out)
            print(encode(meta), flush=True)
    (opts.output / "measurements.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
