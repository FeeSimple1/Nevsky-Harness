"""SMOKE-015 regression: garrison-only defense (defender_lords=[])
must (a) not short-circuit the steps loop after the first strike step
because _all_routed([]) returns True vacuously, and (b) still let the
garrison strike in melee.

Documented in SMOKE_TEST_FINDINGS.md Round 13. Found while running the
Round 13 statistical smoke driver: Storm with garrison-only defense
showed defender win rate ~100% across all configurations because
attacker melee was never delivered.
"""

from __future__ import annotations

from nevsky.battle import resolve_storm
from nevsky.scenarios import load_scenario


def _setup_garrison_only(seed: int = 1):
    s = load_scenario("watland", seed=seed)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic")
    s.lords[teu].state = "mustered"
    s.lords[teu].location = "pskov"
    return s, teu


def test_smoke_015a_garrison_only_storm_runs_all_steps() -> None:
    """A 1-Lord attacker with strong melee against a garrison-only
    Fort must actually deliver melee. Pre-fix: melee_attacker step
    never appeared because _all_routed(state, []) was True and broke
    the steps_data loop after archery_defender."""
    s, teu = _setup_garrison_only()
    # Stack the deck so the attacker is overwhelming: the only way
    # for the attacker to lose is through dice variance, but in any
    # case the melee_attacker step MUST appear at least once.
    s.lords[teu].forces = {"knights": 6}  # 6 knights * 1 storm melee = 6 (capped)
    res = resolve_storm(
        s, attacker_side="teutonic",
        attacker_lords=[teu], defender_lords=[],
        locale_id="pskov", walls_max=2, siege_markers=3,
        garrison={"men_at_arms": 1},
    )
    # Verify: melee_attacker step MUST appear in at least one round.
    melee_atk_appearances = sum(
        1 for rd in res["log"]
        for st in rd["steps"]
        if st.get("step") == "melee_attacker"
    )
    assert melee_atk_appearances >= 1, (
        f"melee_attacker step never fired in {res['rounds']} rounds; "
        f"_all_routed(state, []) probably short-circuited the loop"
    )


def test_smoke_015a_garrison_only_storm_attacker_can_win() -> None:
    """With overwhelming Forces, attacker should regularly win
    against a garrison-only Fort. Pre-fix the attacker won 0% because
    no melee was delivered."""
    teu_wins = 0
    trials = 100
    for seed in range(trials):
        s, teu = _setup_garrison_only(seed=seed)
        s.lords[teu].forces = {"knights": 6}
        res = resolve_storm(
            s, attacker_side="teutonic",
            attacker_lords=[teu], defender_lords=[],
            locale_id="pskov", walls_max=2, siege_markers=3,
            garrison={"men_at_arms": 1},
        )
        if res["winner"] == "attacker":
            teu_wins += 1
    # Should be a majority. Pre-fix this was 0; post-fix expect very high.
    assert teu_wins > trials // 2, (
        f"attacker won only {teu_wins}/{trials} despite overwhelming forces"
    )


def test_smoke_015b_garrison_melee_still_strikes_no_defender_lord() -> None:
    """Garrison units strike in melee even with no defender Lord
    present. Pre-fix: def_melee was built inside `for lid in
    def_front_lords:` and dropped to 0 on empty list."""
    s, teu = _setup_garrison_only(seed=1)
    # Attacker with very weak forces; garrison should be able to
    # damage them. Use a Knight-heavy garrison so the melee is
    # noticeable.
    s.lords[teu].forces = {"light_horse": 1}  # 1 unit, weak armor
    res = resolve_storm(
        s, attacker_side="teutonic",
        attacker_lords=[teu], defender_lords=[],
        locale_id="pskov", walls_max=0, siege_markers=3,
        garrison={"knights": 4},  # 4 knights * 1 storm melee = 4
    )
    melee_def_appearances = sum(
        1 for rd in res["log"]
        for st in rd["steps"]
        if st.get("step") == "melee_defender"
    )
    assert melee_def_appearances >= 1, (
        "garrison melee never fired with empty defender_lords"
    )


def test_smoke_015_with_defender_lord_unchanged() -> None:
    """Smoke check: a normal Storm with a defender Lord still works
    the same way (the fix shouldn't break the established path)."""
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic")
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian")
    for l in (s.lords[teu], s.lords[rus]):
        l.state = "mustered"
        l.location = "pskov"
    s.lords[rus].in_stronghold = True
    s.lords[teu].forces = {"knights": 3, "sergeants": 2}
    s.lords[rus].forces = {"men_at_arms": 3}
    res = resolve_storm(
        s, attacker_side="teutonic",
        attacker_lords=[teu], defender_lords=[rus],
        locale_id="pskov", walls_max=3, siege_markers=2,
        garrison={"men_at_arms": 1},
    )
    # Both melee step types should appear in the log.
    steps = {st.get("step") for rd in res["log"] for st in rd["steps"]}
    assert "melee_attacker" in steps
    # melee_defender should appear because Lord + garrison both melee.
    assert "melee_defender" in steps
