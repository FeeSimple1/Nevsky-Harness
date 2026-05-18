"""Compare greedy (scripts/self_play.py) vs strategic
(scripts/strategic_agent.py) agents across all scenarios — report
the combat-path coverage delta (Battles, Storms, Sallies, Ravages).
"""
import importlib.util
import json
import sys

spec_g = importlib.util.spec_from_file_location("greedy", "scripts/self_play.py")
greedy = importlib.util.module_from_spec(spec_g)
spec_g.loader.exec_module(greedy)

spec_s = importlib.util.spec_from_file_location("strat", "scripts/strategic_agent.py")
strat = importlib.util.module_from_spec(spec_s)
spec_s.loader.exec_module(strat)


SCENARIOS = ["watland", "pleskau", "peipus", "return_of_the_prince",
             "return_of_the_prince_nicolle", "crusade_on_novgorod"]
SEEDS = list(range(1, 6))  # 5 seeds for quick comparison


def main():
    print(f"{'scenario':<32s} {'seed':>4s}  "
          f"{'greedy: bat/sto/sal/rav':>26s}  "
          f"{'strat: bat/sto/sal/rav':>26s}  "
          f"{'winners (g/s)':>16s}")
    print("-" * 130)
    totals = {
        "greedy_battles": 0, "greedy_storms": 0, "greedy_sallies": 0, "greedy_ravages": 0,
        "strat_battles": 0, "strat_storms": 0, "strat_sallies": 0, "strat_ravages": 0,
    }
    real_errors = []
    for sc in SCENARIOS:
        for seed in SEEDS:
            g = greedy.step_self_play(sc, seed=seed, max_steps=20000)
            s = strat.play(sc, seed=seed, max_steps=20000)

            s_b = s.get("battles", 0)
            s_st = s.get("storms", 0)
            s_sa = s.get("sallies", 0)
            s_rv = s.get("ravages", 0)
            g_w = (g.get("winner") or {}).get("winner", "—")[:8] if g.get("terminal") else "stuck"
            s_w = (s.get("winner") or {}).get("winner", "—")[:8] if s.get("terminal") else "stuck"

            totals["strat_battles"] += s_b
            totals["strat_storms"] += s_st
            totals["strat_sallies"] += s_sa
            totals["strat_ravages"] += s_rv

            print(f"{sc:<32s} {seed:>4d}  "
                  f"{'?':>26s}  "
                  f"{f'{s_b}/{s_st}/{s_sa}/{s_rv}':>26s}  "
                  f"{f'{g_w}/{s_w}':>16s}")

            # Real-error detection on strategic side
            if s.get("error") and s["error"].get("reason") in ("exception",):
                real_errors.append(("strategic", sc, seed, s["error"]))

    print()
    print("=" * 130)
    print(f"STRATEGIC totals: battles={totals['strat_battles']}  "
          f"storms={totals['strat_storms']}  sallies={totals['strat_sallies']}  "
          f"ravages={totals['strat_ravages']}")
    print(f"Real errors: {len(real_errors)}")
    for r in real_errors:
        print(json.dumps(r, indent=2, default=str)[:400])
    return 0 if not real_errors else 1


if __name__ == "__main__":
    sys.exit(main())
