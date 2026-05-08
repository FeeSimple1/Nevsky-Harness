"""Round 13 — Battle and Storm statistical smoke.

Per user direction: deep statistical pass on combat outcomes only.
Don't run whole scenarios. Vary lord counts and force compositions for
Battle; vary stronghold types and attacker counts for Storm. Aggregate
defender win rate, average rounds, average force losses.

User priors (2026-05-08):
  - Storm should strongly favor defenders.
  - Battle should favor defenders moderately.

Run: PYTHONPATH=src python3 tests/_playthrough_round13_combat_smoke.py
Outputs JSON-ish summary tables on stdout.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from copy import deepcopy
from typing import Any

from nevsky.battle import (
    BattleDecisionContext,
    resolve_battle,
    resolve_storm,
)
from nevsky.scenarios import load_scenario


# =====================================================================
# Setup helpers
# =====================================================================


# Force compositions (each totals ~6 units, the practical Lord force cap
# in a typical mid-game state). Each composition is a single name -> dict.
COMPOSITIONS: dict[str, dict[str, int]] = {
    "balanced":          {"knights": 1, "sergeants": 2, "men_at_arms": 2, "light_horse": 1},
    "knight_heavy":      {"knights": 3, "sergeants": 2, "men_at_arms": 1},
    "sergeants_heavy":   {"sergeants": 4, "men_at_arms": 2},
    "light_horse_heavy": {"light_horse": 4, "sergeants": 2},
    "militia_heavy":     {"militia": 4, "men_at_arms": 2},
    "asiatic_heavy":     {"asiatic_horse": 4, "light_horse": 2},
}


def _make_state(seed: int):
    """Fresh scenario state with deterministic RNG seed."""
    return load_scenario("watland", seed=seed)


def _take_lords(s, side: str, count: int, location: str, composition: dict[str, int]):
    """Force the first `count` Lords on `side` to be Mustered at
    `location` with `composition` forces. Returns their lord_ids.

    Notes:
    - Watland scenario has 4 Russian and 4 Teutonic Lords mustered or
      ready by default. We don't care about scenario realism: we
      override their state, location, and forces.
    """
    chosen: list[str] = []
    for lid, l in s.lords.items():
        if l.side != side:
            continue
        chosen.append(lid)
        if len(chosen) >= count:
            break
    if len(chosen) < count:
        raise RuntimeError(f"need {count} {side} Lords, have {len(chosen)}")
    for lid in chosen:
        s.lords[lid].state = "mustered"
        s.lords[lid].location = location
        s.lords[lid].forces = dict(composition)
        s.lords[lid].routed_units = {}
        s.lords[lid].in_stronghold = False
    return chosen


def _force_total(forces: dict[str, int]) -> int:
    return sum(forces.values())


def _aggregate_lord_units_remaining(state, lord_ids: list[str]) -> int:
    return sum(_force_total(state.lords[lid].forces) for lid in lord_ids)


# =====================================================================
# Battle smoke
# =====================================================================


def _run_battle_trial(
    seed: int,
    attacker_count: int,
    defender_count: int,
    attacker_comp: dict[str, int],
    defender_comp: dict[str, int],
) -> dict[str, Any]:
    """Run a single resolve_battle and return summary metrics."""
    s = _make_state(seed)
    teus = _take_lords(s, "teutonic", attacker_count, "pskov", attacker_comp)
    rus = _take_lords(s, "russian", defender_count, "pskov", defender_comp)

    # Pre-battle force totals.
    pre_atk = _aggregate_lord_units_remaining(s, teus)
    pre_def = _aggregate_lord_units_remaining(s, rus)

    res = resolve_battle(
        s,
        attacker_side="teutonic",
        attacker_lords=teus,
        defender_lords=rus,
        max_rounds=10,
    )

    post_atk = _aggregate_lord_units_remaining(s, teus)
    post_def = _aggregate_lord_units_remaining(s, rus)

    # resolve_battle returns winner as a Side ("teutonic" / "russian").
    # Normalize to "attacker" / "defender" for the smoke driver.
    raw_winner = res["winner"]
    if raw_winner == "teutonic":
        winner = "attacker"
    elif raw_winner == "russian":
        winner = "defender"
    else:
        winner = raw_winner

    return {
        "winner": winner,
        "rounds": res["rounds"],
        "atk_loss": pre_atk - post_atk,
        "def_loss": pre_def - post_def,
        "pre_atk": pre_atk,
        "pre_def": pre_def,
    }


def smoke_battle(trials: int = 500) -> list[dict[str, Any]]:
    """Run Battle smoke across attacker/defender counts and compositions."""
    counts = [(1, 1), (2, 1), (1, 2), (2, 2), (3, 3), (4, 4)]
    comp_pairs = [
        ("balanced", "balanced"),
        ("knight_heavy", "balanced"),
        ("balanced", "knight_heavy"),
        ("sergeants_heavy", "sergeants_heavy"),
        ("light_horse_heavy", "balanced"),
        ("balanced", "light_horse_heavy"),
        ("balanced", "militia_heavy"),
        ("asiatic_heavy", "balanced"),
        ("balanced", "asiatic_heavy"),
    ]
    rows: list[dict[str, Any]] = []
    for atk_n, def_n in counts:
        for atk_c, def_c in comp_pairs:
            stats = {"def_wins": 0, "atk_wins": 0, "draws": 0,
                     "rounds_sum": 0,
                     "atk_loss_sum": 0, "def_loss_sum": 0,
                     "pre_atk": 0, "pre_def": 0}
            for t in range(trials):
                seed = t * 977 + atk_n * 31 + def_n * 17 + hash((atk_c, def_c)) % 9973
                tr = _run_battle_trial(
                    seed, atk_n, def_n,
                    COMPOSITIONS[atk_c], COMPOSITIONS[def_c],
                )
                if tr["winner"] == "defender":
                    stats["def_wins"] += 1
                elif tr["winner"] == "attacker":
                    stats["atk_wins"] += 1
                else:
                    stats["draws"] += 1
                stats["rounds_sum"] += tr["rounds"]
                stats["atk_loss_sum"] += tr["atk_loss"]
                stats["def_loss_sum"] += tr["def_loss"]
                stats["pre_atk"] += tr["pre_atk"]
                stats["pre_def"] += tr["pre_def"]
            rows.append({
                "atk_n": atk_n, "def_n": def_n,
                "atk_comp": atk_c, "def_comp": def_c,
                "trials": trials,
                "def_winrate": stats["def_wins"] / trials,
                "atk_winrate": stats["atk_wins"] / trials,
                "draw_rate": stats["draws"] / trials,
                "avg_rounds": stats["rounds_sum"] / trials,
                "avg_atk_loss": stats["atk_loss_sum"] / trials,
                "avg_def_loss": stats["def_loss_sum"] / trials,
                "avg_atk_loss_pct": stats["atk_loss_sum"] / max(1, stats["pre_atk"]),
                "avg_def_loss_pct": stats["def_loss_sum"] / max(1, stats["pre_def"]),
            })
    return rows


# =====================================================================
# Storm smoke
# =====================================================================


# Stronghold parameters from data/static/strongholds.json:
STRONGHOLDS = {
    "fort":      {"walls_max": 3, "garrison": {"men_at_arms": 1}},
    "city":      {"walls_max": 3, "garrison": {"men_at_arms": 3}},
    "novgorod":  {"walls_max": 3, "garrison": {"men_at_arms": 3}},
    "castle":    {"walls_max": 4, "garrison": {"men_at_arms": 1, "knights": 1}},
    "bishopric": {"walls_max": 4, "garrison": {"men_at_arms": 2, "knights": 1}},
}

# Side mapping: who would normally be inside?
DEFENDER_SIDE = {
    "fort": "russian",
    "city": "russian",
    "novgorod": "russian",
    "castle": "teutonic",
    "bishopric": "teutonic",
}


def _run_storm_trial(
    seed: int,
    stronghold_type: str,
    attacker_count: int,
    defender_count: int,
    siege_markers: int,
    walls_max: int,
    attacker_comp: dict[str, int],
    defender_comp: dict[str, int],
    locale_id: str = "pskov",
) -> dict[str, Any]:
    """Run a single resolve_storm and return summary metrics."""
    s = _make_state(seed)
    def_side = DEFENDER_SIDE[stronghold_type]
    atk_side = "teutonic" if def_side == "russian" else "russian"
    teus_label = "teutonic" if atk_side == "teutonic" else "russian"

    # Attacker lords on atk_side; defender lords on def_side. We're using
    # "pskov" as a generic placeholder locale because resolve_storm
    # doesn't actually consult locale type; it uses the provided
    # walls_max / garrison.
    attackers = _take_lords(s, atk_side, attacker_count, locale_id, attacker_comp)
    defenders: list[str] = []
    if defender_count > 0:
        defenders = _take_lords(s, def_side, defender_count, locale_id, defender_comp)
        for d in defenders:
            s.lords[d].in_stronghold = True

    # Pre-storm totals (excluding garrison; we report garrison separately).
    pre_atk = _aggregate_lord_units_remaining(s, attackers)
    pre_def = _aggregate_lord_units_remaining(s, defenders)
    pre_garrison = sum(STRONGHOLDS[stronghold_type]["garrison"].values())

    res = resolve_storm(
        s,
        attacker_side=atk_side,
        attacker_lords=attackers,
        defender_lords=defenders,
        locale_id=locale_id,
        walls_max=walls_max,
        siege_markers=siege_markers,
        garrison=dict(STRONGHOLDS[stronghold_type]["garrison"]),
    )

    post_atk = _aggregate_lord_units_remaining(s, attackers)
    post_def = _aggregate_lord_units_remaining(s, defenders)
    post_garrison = sum(res.get("garrison_remaining", {}).values())

    return {
        "winner": res["winner"],
        "rounds": res["rounds"],
        "atk_loss": pre_atk - post_atk,
        "def_loss": pre_def - post_def,
        "garrison_loss": pre_garrison - post_garrison,
        "pre_atk": pre_atk,
        "pre_def": pre_def,
        "pre_garrison": pre_garrison,
    }


def smoke_storm(trials: int = 500) -> list[dict[str, Any]]:
    """Run Storm smoke across stronghold types, attacker counts, defender
    counts (including garrison-only). Walls_max and siege_markers per
    stronghold type."""
    rows: list[dict[str, Any]] = []
    # Configurations: stronghold type x attacker count x (defender_count, siege_markers).
    # siege_markers caps Storm rounds; siege_markers+1 is the round limit.
    configs = []
    for sh_type in STRONGHOLDS:
        sh = STRONGHOLDS[sh_type]
        for atk_n in (1, 2, 3):
            for def_n in (0, 1, 2):  # 0 = garrison-only defense
                # Try both 1-marker (single round) and full-walls siege.
                for sm in (1, 3):
                    configs.append((sh_type, atk_n, def_n, sm, sh["walls_max"]))
    # Compositions: attacker balanced or knight_heavy; defender balanced.
    comp_pairs = [
        ("balanced", "balanced"),
        ("knight_heavy", "balanced"),
    ]
    for sh_type, atk_n, def_n, sm, wm in configs:
        for atk_c, def_c in comp_pairs:
            stats = {"def_wins": 0, "atk_wins": 0, "draws": 0,
                     "rounds_sum": 0,
                     "atk_loss_sum": 0, "def_loss_sum": 0,
                     "garrison_loss_sum": 0,
                     "pre_atk": 0, "pre_def": 0, "pre_garrison": 0}
            for t in range(trials):
                seed = (
                    t * 911 + atk_n * 41 + def_n * 23 + sm * 7
                    + hash((sh_type, atk_c, def_c)) % 9973
                )
                tr = _run_storm_trial(
                    seed, sh_type, atk_n, def_n, sm, wm,
                    COMPOSITIONS[atk_c], COMPOSITIONS[def_c],
                )
                if tr["winner"] == "defender":
                    stats["def_wins"] += 1
                elif tr["winner"] == "attacker":
                    stats["atk_wins"] += 1
                else:
                    stats["draws"] += 1
                stats["rounds_sum"] += tr["rounds"]
                stats["atk_loss_sum"] += tr["atk_loss"]
                stats["def_loss_sum"] += tr["def_loss"]
                stats["garrison_loss_sum"] += tr["garrison_loss"]
                stats["pre_atk"] += tr["pre_atk"]
                stats["pre_def"] += tr["pre_def"]
                stats["pre_garrison"] += tr["pre_garrison"]
            rows.append({
                "stronghold": sh_type, "walls_max": wm,
                "atk_n": atk_n, "def_n": def_n, "siege_markers": sm,
                "atk_comp": atk_c, "def_comp": def_c,
                "trials": trials,
                "def_winrate": stats["def_wins"] / trials,
                "atk_winrate": stats["atk_wins"] / trials,
                "draw_rate": stats["draws"] / trials,
                "avg_rounds": stats["rounds_sum"] / trials,
                "avg_atk_loss": stats["atk_loss_sum"] / trials,
                "avg_def_loss": stats["def_loss_sum"] / trials,
                "avg_garrison_loss": stats["garrison_loss_sum"] / trials,
                "avg_atk_loss_pct": stats["atk_loss_sum"] / max(1, stats["pre_atk"]),
                "avg_def_loss_pct": stats["def_loss_sum"] / max(1, stats["pre_def"]),
                "avg_garrison_loss_pct": (
                    stats["garrison_loss_sum"] / max(1, stats["pre_garrison"])
                ),
            })
    return rows


# =====================================================================
# Reporting
# =====================================================================


def _fmt_battle_table(rows: list[dict[str, Any]]) -> str:
    out = []
    out.append("=" * 88)
    out.append("BATTLE SMOKE")
    out.append("=" * 88)
    hdr = (
        f"{'A_n':>3} {'D_n':>3} | {'atk_comp':<18} {'def_comp':<18} | "
        f"{'D_win%':>7} {'A_win%':>7} {'draw%':>6} | "
        f"{'rounds':>7} {'atk_loss%':>10} {'def_loss%':>10}"
    )
    out.append(hdr)
    out.append("-" * len(hdr))
    for r in rows:
        out.append(
            f"{r['atk_n']:>3} {r['def_n']:>3} | "
            f"{r['atk_comp']:<18} {r['def_comp']:<18} | "
            f"{r['def_winrate']*100:>6.1f}% {r['atk_winrate']*100:>6.1f}% "
            f"{r['draw_rate']*100:>5.1f}% | "
            f"{r['avg_rounds']:>7.2f} {r['avg_atk_loss_pct']*100:>9.1f}% "
            f"{r['avg_def_loss_pct']*100:>9.1f}%"
        )
    return "\n".join(out)


def _fmt_storm_table(rows: list[dict[str, Any]]) -> str:
    out = []
    out.append("=" * 100)
    out.append("STORM SMOKE")
    out.append("=" * 100)
    hdr = (
        f"{'stronghold':<10} {'W':>2} {'A':>2} {'D':>2} {'sm':>2} | "
        f"{'atk_comp':<14} {'def_comp':<14} | "
        f"{'D_win%':>7} {'A_win%':>7} | "
        f"{'rounds':>6} {'a_loss%':>8} {'d_loss%':>8} {'g_loss%':>8}"
    )
    out.append(hdr)
    out.append("-" * len(hdr))
    for r in rows:
        out.append(
            f"{r['stronghold']:<10} {r['walls_max']:>2} "
            f"{r['atk_n']:>2} {r['def_n']:>2} {r['siege_markers']:>2} | "
            f"{r['atk_comp']:<14} {r['def_comp']:<14} | "
            f"{r['def_winrate']*100:>6.1f}% {r['atk_winrate']*100:>6.1f}% | "
            f"{r['avg_rounds']:>6.2f} {r['avg_atk_loss_pct']*100:>7.1f}% "
            f"{r['avg_def_loss_pct']*100:>7.1f}% {r['avg_garrison_loss_pct']*100:>7.1f}%"
        )
    return "\n".join(out)


def main() -> None:
    trials_battle = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    trials_storm = int(sys.argv[2]) if len(sys.argv) > 2 else 500
    if trials_battle > 0:
        print(f"Battle smoke: {trials_battle} trials per cell", file=sys.stderr)
        battle_rows = smoke_battle(trials_battle)
        print(_fmt_battle_table(battle_rows))
    else:
        battle_rows = []
    if trials_storm > 0:
        print(f"\nStorm smoke: {trials_storm} trials per cell", file=sys.stderr)
        storm_rows = smoke_storm(trials_storm)
    else:
        storm_rows = []
    if storm_rows:
        print(_fmt_storm_table(storm_rows))
    # Also dump JSON to a side-file for downstream analysis.
    with open("round13_smoke_results.json", "w") as f:
        json.dump({"battle": battle_rows, "storm": storm_rows}, f, indent=2)
    print("\nJSON results written to round13_smoke_results.json", file=sys.stderr)


if __name__ == "__main__":
    main()
