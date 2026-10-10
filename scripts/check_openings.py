#!/usr/bin/env python3
"""Audit First-Levy implementation across scenario/seed opening positions.

These are opening prefixes, never reported as completed games. Every offered
concrete choice is checked, and the chosen trajectory must reach Pay.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nevsky.actions import apply_action  # noqa: E402
from nevsky.legal_moves import legal_moves  # noqa: E402
from nevsky.scenarios import SCENARIO_IDS, load_scenario  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seeds", type=int, default=500, help="check integer seeds 1 through this number"
    )
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    checked = choices = 0
    failures = []
    for scenario in SCENARIO_IDS:
        if scenario == "quickstart":  # no loadable setup is supplied for this ID
            continue
        for seed in range(1, args.seeds + 1):
            state = load_scenario(scenario, seed=seed)
            for side in ("teutonic", "russian"):
                apply_action(
                    state, {"type": "confirm_all_setup_transports", "side": side, "args": {}}
                )
            try:
                for _ in range(40):
                    if state.meta.levy_step != "arts_of_war":
                        assert not state.decks.teutonic.pending_draw
                        assert not state.decks.russian.pending_draw
                        assert state.meta.aow_drawn_t and state.meta.aow_drawn_r
                        break
                    before = state.model_dump_json()
                    menu = legal_moves(state, with_previews=False)
                    assert state.model_dump_json() == before, "menu mutated the opening"
                    assert menu, "no opening choices"
                    for move in menu:
                        assert isinstance(move.get("args"), dict), "unresolved opening template"
                        apply_action(
                            state.model_copy(deep=True),
                            {key: move[key] for key in ("type", "side", "args")},
                        )
                        choices += 1
                    apply_action(state, {key: menu[0][key] for key in ("type", "side", "args")})
                else:
                    raise AssertionError("opening step limit")
            except Exception as exc:
                failures.append(
                    {"scenario": scenario, "seed": seed, "error": f"{type(exc).__name__}: {exc}"}
                )
            checked += 1
        print(f"{scenario}: checked {args.seeds} openings", flush=True)
    report = {
        "opening_prefixes": checked,
        "offered_choices_checked": choices,
        "completed_games_claimed": 0,
        "failures": failures,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
