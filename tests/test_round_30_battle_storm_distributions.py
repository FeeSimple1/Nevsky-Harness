"""Round 30: battle/storm outcome distribution sanity (regression).

These tests lock the *qualitative* shape of combat outcomes so future
regressions in initiative, hit-cap, walls absorption, or side-symmetry
get caught. They are fast (small N=50 per case) and use deterministic
seeds, but assertions are loose-banded to remain stable under benign
RNG-stream changes.

Findings audited in Round 30:

  - Battle is side-symmetric: T-attacks-R and R-attacks-T with
    identical forces produce statistically identical attacker-win
    rates. (Earlier in Round 30, an apparent asymmetry traced to
    Crusade-on-Novgorod having 2 mustered Russian Lords instead of 3,
    so 3v3 became 3v2 in the test fixture. Once Lords are explicitly
    mustered in equal counts, symmetry holds exactly.)

  - Defender-strikes-first produces a strong baseline defender bias
    in pure-symmetric setups (1v1 3K vs 3K: ~85% defender wins). This
    is rule-correct (Battle initiative: archery defender, archery
    attacker, melee horse defender, melee horse attacker, ...). In
    real play the attacker offsets this with capabilities, terrain,
    and force imbalance; the symmetric baseline is a worst case.

  - Storm with realistic stronghold params (City/Novgorod walls 1-3,
    garrison 3 MaA, siege markers 3) produces ~100% defender wins
    against a 1-lord defender even when the attacker has 3 lords --
    consistent with "Storm strongly favors defender".

  - Pursuit (concede) makes the conceder lose unconditionally.
"""
from __future__ import annotations

from collections import Counter

from nevsky.battle import resolve_battle, resolve_storm
from nevsky.scenarios import load_scenario


def _muster_n(seed, scenario, t_forces_list, r_forces_list):
    """Force-muster the first N Lords on each side with given forces."""
    s = load_scenario(scenario, seed=seed)
    teu_ids: list[str] = []
    rus_ids: list[str] = []
    for lid, l in s.lords.items():
        if l.side == "teutonic" and len(teu_ids) < len(t_forces_list):
            l.state = "mustered"
            l.location = "novgorod"
            l.in_stronghold = False
            l.forces = dict(t_forces_list[len(teu_ids)])
            teu_ids.append(lid)
        elif l.side == "russian" and len(rus_ids) < len(r_forces_list):
            l.state = "mustered"
            l.location = "novgorod"
            l.in_stronghold = False
            l.forces = dict(r_forces_list[len(rus_ids)])
            rus_ids.append(lid)
    return s, teu_ids, rus_ids


def _battle_winrates(t_forces_list, r_forces_list, attacker, n=50):
    wins: Counter = Counter()
    for seed in range(1, n + 1):
        s, t_ids, r_ids = _muster_n(seed, "watland", t_forces_list, r_forces_list)
        if attacker == "teutonic":
            res = resolve_battle(s, "teutonic", t_ids, r_ids)
        else:
            res = resolve_battle(s, "russian", r_ids, t_ids)
        wins[res["winner"]] += 1
    atk_w = wins["teutonic" if attacker == "teutonic" else "russian"]
    return atk_w / n


def _storm_winrates(t_forces_list, r_forces_list, walls, siege, gar, n=50):
    wins: Counter = Counter()
    for seed in range(1, n + 1):
        s, t_ids, r_ids = _muster_n(
            seed, "crusade_on_novgorod", t_forces_list, r_forces_list,
        )
        for lid in r_ids:
            s.lords[lid].in_stronghold = True
        res = resolve_storm(
            s, "teutonic", t_ids, r_ids,
            "novgorod", walls, siege, dict(gar),
        )
        wins[res["winner"]] += 1
    return wins["attacker"] / n


# ---------------------------------------------------------------------------
# Battle: side-symmetry
# ---------------------------------------------------------------------------


def test_battle_is_side_symmetric_at_3v3_parity():
    """T-atk and R-atk attacker-win rates must agree to within ~5pp at
    matched 3v3 (3K+2MaA per Lord). With 200 trials the error is ~1pp;
    we use 50 here for speed and check a 10pp band."""
    sym = [{"knights": 3, "men_at_arms": 2}] * 3
    t_atk_rate = _battle_winrates(sym, sym, "teutonic", n=50)
    r_atk_rate = _battle_winrates(sym, sym, "russian", n=50)
    assert abs(t_atk_rate - r_atk_rate) < 0.10, (
        f"Side-symmetric at 3v3 parity should produce equal attacker-win "
        f"rates; got T-atk={t_atk_rate:.2f}, R-atk={r_atk_rate:.2f}"
    )


def test_battle_is_side_symmetric_at_1v1_3K():
    sym = [{"knights": 3}]
    t_atk_rate = _battle_winrates(sym, sym, "teutonic", n=50)
    r_atk_rate = _battle_winrates(sym, sym, "russian", n=50)
    assert abs(t_atk_rate - r_atk_rate) < 0.10


# ---------------------------------------------------------------------------
# Battle: defender bias from defender-strike-first
# ---------------------------------------------------------------------------


def test_battle_defender_advantaged_at_1v1_3K_parity():
    """3K vs 3K: defender should win majority of trials (rule-correct
    consequence of defender-strike-first per 4.4.2 initiative)."""
    sym = [{"knights": 3}]
    atk_rate = _battle_winrates(sym, sym, "teutonic", n=50)
    # Defender win rate > 60% at minimum; observed ~85-87% in 200-seed sweep.
    assert atk_rate < 0.40, (
        f"Defender should be favored at 1v1 3K parity; observed atk win "
        f"rate {atk_rate:.2f}"
    )


def test_battle_defender_advantaged_at_3v3_parity():
    sym = [{"knights": 3, "men_at_arms": 2}] * 3
    atk_rate = _battle_winrates(sym, sym, "teutonic", n=50)
    assert atk_rate < 0.40, (
        f"Defender should be favored at 3v3 parity; atk win rate "
        f"{atk_rate:.2f}"
    )


# ---------------------------------------------------------------------------
# Storm: defender strongly advantaged with realistic stronghold params
# ---------------------------------------------------------------------------


def test_storm_strongly_favors_defender_at_city_with_garrison():
    """City: walls 1-3, garrison 3 MaA, siege 3 markers. 3 atk lords vs
    1 def lord. Defender should win > 90% of trials."""
    atk_rate = _storm_winrates(
        [{"knights": 3, "men_at_arms": 3}] * 3,
        [{"knights": 3, "men_at_arms": 3}],
        walls=3, siege=3,
        gar={"men_at_arms": 3, "knights": 0},
        n=50,
    )
    assert atk_rate < 0.10, (
        f"City-tier Storm should strongly favor defender; atk win rate "
        f"{atk_rate:.2f}"
    )


def test_storm_strongly_favors_defender_at_castle_with_garrison():
    """Castle: walls 1-4, garrison 1 MaA + 1 K, capacity 2, siege 2."""
    atk_rate = _storm_winrates(
        [{"knights": 3, "men_at_arms": 3}] * 2,
        [{"knights": 3, "men_at_arms": 3}],
        walls=4, siege=2,
        gar={"men_at_arms": 1, "knights": 1},
        n=50,
    )
    assert atk_rate < 0.20, (
        f"Castle Storm should favor defender; atk win rate {atk_rate:.2f}"
    )


# ---------------------------------------------------------------------------
# Pursuit / Concede: conceder loses unconditionally (4.4.2)
# ---------------------------------------------------------------------------


def test_concede_defender_makes_attacker_win():
    sym = [{"knights": 3}]
    wins: Counter = Counter()
    for seed in range(1, 21):
        s, t_ids, r_ids = _muster_n(seed, "watland", sym, sym)
        res = resolve_battle(s, "teutonic", t_ids, r_ids, concede="defender")
        wins[res["winner"]] += 1
    assert wins["teutonic"] == 20, (
        f"Defender concede must make attacker win every trial; "
        f"got {wins}"
    )


def test_concede_attacker_makes_defender_win():
    sym = [{"knights": 3}]
    wins: Counter = Counter()
    for seed in range(1, 21):
        s, t_ids, r_ids = _muster_n(seed, "watland", sym, sym)
        res = resolve_battle(s, "teutonic", t_ids, r_ids, concede="attacker")
        wins[res["winner"]] += 1
    assert wins["russian"] == 20


# ---------------------------------------------------------------------------
# Round-count distribution: no stalemate at long-tail
# ---------------------------------------------------------------------------


def test_battle_round_distribution_does_not_stalemate():
    """3K2MaA vs 3K2MaA: rounds should fall well under max_rounds=10."""
    sym = [{"knights": 3, "men_at_arms": 2}]
    rounds = []
    for seed in range(1, 51):
        s, t_ids, r_ids = _muster_n(seed, "watland", sym, sym)
        res = resolve_battle(s, "teutonic", t_ids, r_ids)
        rounds.append(res["rounds"])
    # Average rounds well under 5; max well under 10.
    avg = sum(rounds) / len(rounds)
    assert avg < 5.0, f"avg rounds {avg:.2f} suspiciously high (stalemate?)"
    assert max(rounds) < 10, f"max rounds {max(rounds)} hit cap (stalemate)"
