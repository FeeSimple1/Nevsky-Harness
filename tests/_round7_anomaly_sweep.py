"""Round 7: anomaly-detection smoke test for Battle outcomes.

For each scenario we run N battles with varied seeds and equal forces
on each side. Statistical anomalies flag potential hidden bugs.

Specifically:
  - Equal Knights vs Knights: expect ~50/50 win rate (attacker has
    initiative parity; defenders strike first per Battle initiative).
    Per the Battle reference: defender strikes FIRST in each step
    (archery defender -> attacker -> melee horse defender -> attacker
    -> melee foot defender -> attacker). So defender has slight edge.
    Win rate around 55/45 for defender is normal; 90/10 is suspect.
  - Equal Sergeants vs Sergeants: similar.
  - Symmetric scenarios (T vs R with same forces) should be ~50/50
    after averaging over many seeds, since the harness should be
    side-agnostic except for initiative.
  - Round count distribution: expect 1-4 rounds typically; very
    high counts (>10 always) signal a stalemate detection bug.
"""

from __future__ import annotations

from collections import Counter
from statistics import mean, stdev

from nevsky.battle import resolve_battle
from nevsky.scenarios import load_scenario


def reset_battle(seed: int, t_forces: dict, r_forces: dict):
    s = load_scenario("watland", seed=seed)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    s.lords[teu].forces = dict(t_forces)
    s.lords[rus].forces = dict(r_forces)
    return s, teu, rus


def run_n_battles(n: int, t_forces: dict, r_forces: dict, attacker: str = "teutonic"):
    """Run n battles with same forces but seeds 1..n. Return stats."""
    wins = Counter()
    rounds = []
    for seed in range(1, n + 1):
        s, teu, rus = reset_battle(seed, t_forces, r_forces)
        if attacker == "teutonic":
            res = resolve_battle(s, "teutonic", [teu], [rus])
        else:
            res = resolve_battle(s, "russian", [rus], [teu])
        wins[res["winner"]] += 1
        rounds.append(res["rounds"])
    return wins, rounds


def report(label, wins, rounds, n):
    t = wins["teutonic"]
    r = wins["russian"]
    avg_rounds = mean(rounds)
    sd = stdev(rounds) if len(rounds) > 1 else 0
    max_r = max(rounds)
    min_r = min(rounds)
    print(f"\n[{label}] n={n}: T={t}/{n} ({100*t/n:.1f}%), R={r}/{n} ({100*r/n:.1f}%); "
          f"rounds avg={avg_rounds:.2f} sd={sd:.2f} min={min_r} max={max_r}")
    # Anomaly: <5% or >95% win rate is suspicious for symmetric setups.
    skew = abs(t - r) / n
    if skew > 0.6:
        print(f"  ! ANOMALY: skew {skew:.2f} > 0.6 (lopsided)")
        return False
    return True


def main():
    print("=" * 60)
    print("Round 7 anomaly sweep")
    print("=" * 60)
    N = 200

    issues = []

    # 1. Symmetric Knights vs Knights, T attacks R.
    wins, rounds = run_n_battles(N, {"knights": 3}, {"knights": 3}, "teutonic")
    if not report("3K vs 3K, T attacks", wins, rounds, N):
        issues.append("3K vs 3K T attacks lopsided")

    # 2. Symmetric Knights vs Knights, R attacks T.
    wins, rounds = run_n_battles(N, {"knights": 3}, {"knights": 3}, "russian")
    if not report("3K vs 3K, R attacks", wins, rounds, N):
        issues.append("3K vs 3K R attacks lopsided")

    # 3. Symmetric Sergeants vs Sergeants.
    wins, rounds = run_n_battles(N, {"sergeants": 3}, {"sergeants": 3}, "teutonic")
    if not report("3S vs 3S, T attacks", wins, rounds, N):
        issues.append("3S vs 3S lopsided")

    # 4. Mixed symmetric.
    wins, rounds = run_n_battles(
        N, {"knights": 2, "men_at_arms": 2}, {"knights": 2, "men_at_arms": 2}, "teutonic"
    )
    if not report("Mixed sym, T attacks", wins, rounds, N):
        issues.append("Mixed sym lopsided")

    # 5. Asymmetric: 2x knights vs 1x knights, T should win heavily.
    wins, rounds = run_n_battles(N, {"knights": 4}, {"knights": 2}, "teutonic")
    if wins["teutonic"] / N < 0.7:
        print(f"  ! ANOMALY: 4K vs 2K T attack T win rate {wins['teutonic']/N:.2f} < 0.7")
        issues.append("4K vs 2K T not winning consistently")
    else:
        print(f"  OK 4K vs 2K T wins {wins['teutonic']}/{N} ({100*wins['teutonic']/N:.1f}%)")

    # 6. Light Horse only (Unarmored melee, no archery without LUCHNIKI).
    # Symmetric LH vs LH.
    wins, rounds = run_n_battles(N, {"light_horse": 4}, {"light_horse": 4}, "teutonic")
    if not report("4LH vs 4LH", wins, rounds, N):
        issues.append("4LH vs 4LH lopsided")

    # 7. Asiatic Horse vs Knights (AH has Archery; K has Armor 1-4).
    wins, rounds = run_n_battles(N, {"asiatic_horse": 6}, {"knights": 3}, "teutonic")
    print(f"\n[6AH vs 3K] T win rate {wins['teutonic']}/{N}")
    # AH only has Archery; K has Armor 1-4 (high) and Melee 2 each.
    # K should win.
    if wins["russian"] > wins["teutonic"]:
        print(f"  ! Note: Russian forces won despite T being attacker; check if expected")

    # 8. Round count distribution: should peak at low rounds, not stalemate.
    print(f"\n[Round count distribution from runs above]")
    all_rounds = []
    for case in [
        ({"knights": 3}, {"knights": 3}),
        ({"sergeants": 3}, {"sergeants": 3}),
        ({"knights": 2, "men_at_arms": 2}, {"knights": 2, "men_at_arms": 2}),
    ]:
        _, rs = run_n_battles(N, case[0], case[1], "teutonic")
        all_rounds.extend(rs)
    counter = Counter(all_rounds)
    for k in sorted(counter):
        print(f"  {k} rounds: {counter[k]} battles")
    # Stalemate detection: max_rounds=10. If many battles hit 10, that\'s
    # suspicious.
    pct_at_max = counter.get(10, 0) / len(all_rounds) * 100
    if pct_at_max > 5:
        print(f"  ! ANOMALY: {pct_at_max:.1f}% battles hit max-rounds=10 (stalemate)")
        issues.append(f"{pct_at_max:.1f}% stalemate rate")

    # 9. d6 fairness: sample 10000 rolls.
    print(f"\n[d6 fairness]")
    from nevsky.rng import _make_rng
    rolls = []
    for seed in range(1, 100):
        rng = _make_rng(seed, 0)
        for state in range(100):
            sub = _make_rng(seed, state)
            rolls.append(sub.randint(1, 6))
    counter = Counter(rolls)
    expected = len(rolls) / 6
    for face in range(1, 7):
        cnt = counter[face]
        dev = abs(cnt - expected) / expected
        flag = " !" if dev > 0.05 else ""
        print(f"  d6={face}: {cnt} ({cnt/len(rolls)*100:.1f}%, expected {1/6*100:.1f}%){flag}")

    # 10. Storm with realistic forces should not always favor attacker.
    print(f"\n[Storm 3-attackers vs 1-besieged + Garrison]")
    from nevsky.battle import resolve_storm
    storm_wins = Counter()
    storm_rounds = []
    for seed in range(1, 51):
        s = load_scenario("pleskau", seed=seed)
        s.lords["hermann"].location = "pskov"
        s.lords["yaroslav"].location = "pskov"
        s.lords["knud_and_abel"].location = "pskov"
        s.lords["gavrilo"].location = "pskov"
        s.lords["gavrilo"].in_stronghold = True
        s.lords["hermann"].forces = {"knights": 5, "men_at_arms": 3}
        s.lords["yaroslav"].forces = {"knights": 3, "men_at_arms": 2}
        s.lords["knud_and_abel"].forces = {"knights": 4, "men_at_arms": 3}
        s.lords["gavrilo"].forces = {"knights": 2, "men_at_arms": 2}
        res = resolve_storm(
            s, attacker_side="teutonic",
            attacker_lords=["hermann", "yaroslav", "knud_and_abel"],
            defender_lords=["gavrilo"],
            locale_id="pskov", walls_max=3, siege_markers=4,
            garrison={"men_at_arms": 3, "knights": 0},
        )
        storm_wins[res["winner"]] += 1
        storm_rounds.append(res["rounds"])
    print(f"  Storm: attacker wins {storm_wins['attacker']}/50 ({storm_wins['attacker']*2}%); "
          f"defender wins {storm_wins['defender']}/50; avg rounds {mean(storm_rounds):.2f}")

    print(f"\n=== ANOMALIES: {len(issues)} ===")
    for i in issues:
        print(f"  {i}")


if __name__ == "__main__":
    import sys
    sys.exit(main())
