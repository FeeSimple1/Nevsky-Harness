#!/usr/bin/env python3
"""Run completion-required multi-policy Crusade games and audit the evidence.

This is an external test player, not a rule or strategy inside the engine.
A step-limited, crashed, unreplayable or flagged case never counts as clean.
Example:
  python scripts/convergence_suite.py --seeds 20261012-20261019 --workers 3
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
POLICIES = ("logistics", "combined", "maritime")


def source_digest() -> str:
    digest = hashlib.sha256()
    paths = sorted((ROOT / "src" / "nevsky").rglob("*.py"))
    paths += [ROOT / "scripts" / name for name in ("convergence_play.py", "fuzz_invariants.py")]
    for path in paths:
        digest.update(str(path.relative_to(ROOT)).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def evaluate_runs(records: list[dict[str, Any]], minimum_full_length: int = 8) -> dict[str, Any]:
    failures = []
    counts: Counter[str] = Counter()
    completed = full_length = actions = reloads = 0
    for row in records:
        label = f"{row.get('seed')}/{row.get('policy')}"
        issues = []
        if row.get("driver_error"):
            issues.append(str(row["driver_error"]))
        if not row.get("terminal"):
            issues.append("did not reach Game End")
        if row.get("finding_groups", 0):
            issues.append(f"{row['finding_groups']} diagnostic groups")
        if row.get("replay_errors"):
            issues.append("replay mismatch")
        if issues:
            failures.append({"case": label, "issues": issues})
        else:
            completed += 1
            full_length += int(row.get("last_box") == 16)
        actions += row.get("actions_including_setup", 0)
        reloads += row.get("save_reload_checks", 0)
        counts.update(row.get("action_counts", {}))
    if full_length < minimum_full_length:
        failures.append(
            {
                "case": "coverage",
                "issues": [
                    f"only {full_length} clean turn-16 games; {minimum_full_length} required"
                ],
            }
        )
    exercised = {row.get("policy") for row in records}
    if exercised != set(POLICIES):
        failures.append({"case": "coverage", "issues": ["all three policies are required"]})
    return {
        "clean": not failures,
        "cases": len(records),
        "clean_completed": completed,
        "clean_full_16_turn": full_length,
        "actions": actions,
        "save_reload_checks": reloads,
        "failures": failures,
        "action_counts": dict(counts),
        "records": records,
    }


def run_case(seed: int, policy: str, output: Path, label: str, timeout: int) -> dict[str, Any]:
    folder = output / f"{seed}_{policy}"
    folder.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    try:
        with (folder / "play.log").open("w") as log:
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "convergence_play.py"),
                    "--seed",
                    str(seed),
                    "--policy",
                    policy,
                    "--out",
                    str(folder),
                    "--label",
                    label,
                ],
                cwd=ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
            )
        path = folder / "summary.json"
        row = json.loads(path.read_text()) if path.exists() else {}
        if result.returncode or not path.exists():
            row["driver_error"] = f"exit={result.returncode}; summary={path.exists()}"
    except (subprocess.TimeoutExpired, OSError, ValueError) as exc:
        row = {"driver_error": f"{type(exc).__name__}: {exc}"}
    row.update(seed=seed, policy=policy, seconds=round(time.monotonic() - started, 2))
    row.pop("final", None)
    return row


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", default="20261012-20261019")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=450)
    parser.add_argument("--minimum-full-length", type=int, default=8)
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "convergence")
    options = parser.parse_args(argv)
    if options.workers < 1 or options.timeout < 1:
        parser.error("workers and timeout must be positive")
    try:
        if "-" in options.seeds:
            start, end = (int(part) for part in options.seeds.split("-", 1))
            seeds = list(range(start, end + 1))
        else:
            seeds = [int(part) for part in options.seeds.split(",")]
    except ValueError:
        parser.error("seeds must be an inclusive range or comma-separated integers")
    if not seeds or len(set(seeds)) != len(seeds):
        parser.error("provide one or more distinct seeds")
    output = options.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any((output / f"{seed}_{policy}").exists() for seed in seeds for policy in POLICIES):
        parser.error("case folders already exist; choose a new output directory")
    before = source_digest()
    records = []
    futures = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=options.workers) as pool:
        for seed in seeds:
            for policy in POLICIES:
                future = pool.submit(run_case, seed, policy, output, before, options.timeout)
                futures[future] = (seed, policy)
        for future in concurrent.futures.as_completed(futures):
            seed, policy = futures[future]
            try:
                row = future.result()
            except Exception as exc:
                row = {"seed": seed, "policy": policy, "driver_error": repr(exc)}
            records.append(row)
            print(
                json.dumps(
                    {
                        key: row.get(key)
                        for key in (
                            "seed",
                            "policy",
                            "terminal",
                            "last_box",
                            "finding_groups",
                            "replay_errors",
                            "driver_error",
                        )
                    }
                ),
                flush=True,
            )
            (output / "progress.json").write_text(json.dumps(records, indent=2) + "\n")
    report = evaluate_runs(records, options.minimum_full_length)
    report["source_sha256"] = before
    report["source_unchanged"] = before == source_digest()
    if not report["source_unchanged"]:
        report["clean"] = False
        report["failures"].append({"case": "source", "issues": ["code changed during the batch"]})
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key != "records"}, indent=2))
    return 0 if report["clean"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
