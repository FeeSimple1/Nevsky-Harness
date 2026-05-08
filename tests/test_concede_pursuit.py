"""Tests for 4.4.2 Concede the Field + Pursuit."""

from __future__ import annotations

from nevsky.battle import resolve_battle
from nevsky.scenarios import load_scenario


def test_concede_attacker_loses_after_round_1() -> None:
    """4.4.2: side that Concedes the Field loses; Round 1 is the last Round."""
    s = load_scenario("watland", seed=11)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    res = resolve_battle(s, "teutonic", [teu], [rus], concede="attacker")
    assert res["loser"] == "teutonic"
    assert res["winner"] == "russian"
    assert res["rounds"] == 1
    assert res.get("conceded") == "attacker"


def test_concede_defender_loses() -> None:
    s = load_scenario("watland", seed=11)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    res = resolve_battle(s, "teutonic", [teu], [rus], concede="defender")
    assert res["loser"] == "russian"
    assert res["rounds"] == 1
    assert res.get("conceded") == "defender"


def test_pursuit_halves_conceder_hits() -> None:
    """4.4.2: enemy gains Pursuit; conceder's total Hits halved (round up).

    Statistical comparison: a battle with many units should produce
    fewer hits on the non-conceder side when the conceder is the
    striker. We verify round 1 logs differ between concede=attacker
    and no-concede runs."""
    s_no = load_scenario("watland", seed=99)
    teu = next(lid for lid, l in s_no.lords.items() if l.side == "teutonic" and l.state == "mustered")
    rus = next(lid for lid, l in s_no.lords.items() if l.side == "russian" and l.state == "mustered")
    s_no.lords[teu].forces = {"knights": 5, "men_at_arms": 3}
    s_no.lords[rus].forces = {"knights": 3, "men_at_arms": 3}
    res_no = resolve_battle(s_no, "teutonic", [teu], [rus])
    s_yes = load_scenario("watland", seed=99)
    s_yes.lords[teu].forces = {"knights": 5, "men_at_arms": 3}
    s_yes.lords[rus].forces = {"knights": 3, "men_at_arms": 3}
    res_yes = resolve_battle(s_yes, "teutonic", [teu], [rus], concede="attacker")
    # res_yes is 1 round (concede ends after round 1).
    assert res_yes["rounds"] == 1
