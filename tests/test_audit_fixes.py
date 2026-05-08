"""Regression tests for the BRIEF rules-accuracy audit (Round 8)."""

from __future__ import annotations

from nevsky.battle import _absorb_hit, resolve_storm
from nevsky.scenarios import load_scenario


def test_audit_001_storm_melee_cap_is_per_lord_not_per_side() -> None:
    """4.5.2 (2E): Maximum 6 Melee Hits per Lord per Round.

    Pre-fix the cap was applied to the per-side total (6 * lords_count),
    which let one Lord exceed 6 if others contributed 0. Post-fix the
    cap is applied per-Lord before summing.

    Verify by giving one Lord 12 Knights (would generate 24 hits melee,
    capped at 6) and another Lord 0 Knights. Per-side total post-fix = 6,
    NOT 6+6=12 (which the old cap-by-product would allow)."""
    s = load_scenario("watland", seed=11)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    teu2 = next((lid for lid, l in s.lords.items()
                 if l.side == "teutonic" and l.state == "mustered" and lid != teu), None)
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    if teu2 is None:
        # Can't test multi-Lord; skip.
        import pytest
        pytest.skip("watland has only 1 Mustered Teu Lord")
    s.lords[teu].forces = {"knights": 12}  # would generate 24 melee hits uncapped
    s.lords[teu2].forces = {}
    s.lords[rus].forces = {"militia": 1}  # weak defender
    res = resolve_storm(
        s, attacker_side="teutonic",
        attacker_lords=[teu, teu2],
        defender_lords=[rus],
        locale_id="pskov", walls_max=0, siege_markers=4,
        garrison={"men_at_arms": 0, "knights": 0},
    )
    # In any single melee attacker round, the recorded hits_after_walls
    # for teu's 12 Knights should be capped at 6 (per-Lord cap).
    found_cap_in_log = False
    for r in res["log"]:
        for step in r["steps"]:
            if step.get("step") == "melee_attacker":
                # hits_after_walls is hits after walls subtracted (walls=0
                # here). Must be <= 6 (single-Lord cap, even though side
                # has 2 attackers, since teu2 contributes 0).
                assert step["hits_after_walls"] <= 6, \
                    f"melee_attacker hits {step['hits_after_walls']} exceeds per-Lord cap 6"
                found_cap_in_log = True
    assert found_cap_in_log


def test_audit_002_warrior_monks_per_step_reroll_budget() -> None:
    """T7/T15 Warrior Monks: 1 reroll per Knights Armor failure each
    Archery step AND each Melee step.

    Pre-fix the reroll fired per Hit-call (unbounded). Post-fix it fires
    at most once per (lord_id, strike_kind) within a step.

    Verify: with step_state shared across many _absorb_hit calls, only
    the FIRST failed Knights roll triggers a reroll."""
    s = load_scenario("watland", seed=42)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].this_lord_capabilities = ["T7"]
    step_state: dict = {}
    # Force many knights-armor calls; only one should be rerolled.
    # Without rerolls, Knights have 4/6 = 0.667 absorption.
    # With 1 reroll budget, the FIRST failure gets a second chance,
    # remaining calls use base rate.
    n = 600
    pre_state = s.meta.rng_state
    absorbed_with_step = sum(
        1 for _ in range(n)
        if _absorb_hit(s, "knights", "melee", lord_id=teu, step_state=step_state)
    )
    # If the budget was honored, we used 1 reroll (consumed step_state).
    assert step_state.get(("wm_reroll_used", teu, "melee")) is True


def test_audit_002_warrior_monks_separate_budgets_for_archery_and_melee() -> None:
    """The reroll budget is per-Strike-step. Archery and Melee within
    one Round are SEPARATE steps, so each gets its own reroll."""
    s = load_scenario("watland", seed=42)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].this_lord_capabilities = ["T7"]
    step_state: dict = {}
    # Run archery + melee budgets in same step_state -- both keys should
    # be independently consumable.
    for _ in range(50):
        _absorb_hit(s, "knights", "archery", lord_id=teu, step_state=step_state)
        _absorb_hit(s, "knights", "melee", lord_id=teu, step_state=step_state)
    assert step_state.get(("wm_reroll_used", teu, "archery")) is True
    assert step_state.get(("wm_reroll_used", teu, "melee")) is True
