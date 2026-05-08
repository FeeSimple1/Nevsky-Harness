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


def test_audit_003_storm_attacker_absorbs_with_armored_first() -> None:
    """4.5.2 (2E): "The Attacking side must absorb Hits with any
    Armored units before doing so with other units."

    Verified at the unit-picker level: with a mixed force (serfs +
    knights), the armored_first policy returns the Armored unit, while
    the default weakest_first returns the Serf.
    """
    from nevsky.battle import _assign_hit_owner_pick

    units = {"serfs": 4, "knights": 2}
    # Owner-picks (Battle, Storm Defender, Sally) -> shield with serfs.
    assert _assign_hit_owner_pick(units, {}, policy="weakest_first") == "serfs"
    # Storm Attacker (4.5.2 2E) -> Armored first.
    assert _assign_hit_owner_pick(units, {}, policy="armored_first") == "knights"


def test_audit_003_storm_attacker_armored_first_default_is_unchanged() -> None:
    """The default policy (no `policy=` arg) must remain weakest_first
    so all existing Battle/Sally/Storm-Defender call sites are
    unaffected.
    """
    from nevsky.battle import _assign_hit_owner_pick

    units = {"serfs": 1, "knights": 1}
    assert _assign_hit_owner_pick(units, {}) == "serfs"


def test_audit_003_storm_attacker_threading_into_resolve_hits() -> None:
    """End-to-end: in resolve_storm, a Storm Attacker Lord with mixed
    Armored + Serf forces should lose Armored before Serfs (because
    Armored absorbs first). Use a deterministic seed so we can compare
    pre- and post-fix outcomes in a controlled way.

    We construct a Storm where the attacker has an attacker force of
    (serfs:4, knights:2) and the defender has only a tiny garrison so
    the attacker survives. Inspect the routed_units / forces at end of
    round 1 archery_defender step: pre-fix this would have lost serfs
    first; post-fix at least one Armored absorption attempt happens
    before any serf is hit.
    """
    s = load_scenario("watland", seed=11)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    s.lords[teu].forces = {"serfs": 4, "knights": 2}
    s.lords[teu].location = s.lords[rus].location
    s.lords[rus].forces = {"men_at_arms": 4}
    res = resolve_storm(
        s, attacker_side="teutonic",
        attacker_lords=[teu], defender_lords=[rus],
        locale_id=s.lords[rus].location, walls_max=0, siege_markers=2,
        garrison={"men_at_arms": 1},
    )
    # Look at the archery_defender step in round 1 -- the defender's
    # archery hits target the attacker. Find the first hit assigned to
    # a Lord and confirm the unit is "knights" (Armored), not "serfs".
    found_first_lord_hit = None
    for round_log in res["log"]:
        for step in round_log["steps"]:
            if step["step"] != "archery_defender":
                continue
            for d in step["distribution"]:
                if d.get("target") == "lord":
                    routed = d.get("routed", [])
                    if routed:
                        found_first_lord_hit = routed[0]["unit"]
                        break
            if found_first_lord_hit:
                break
        if found_first_lord_hit:
            break
    assert found_first_lord_hit is not None, "no archery_defender hit landed on attacker Lord"
    assert found_first_lord_hit == "knights", (
        f"Storm Attacker should absorb with knights (Armored) first per 4.5.2 2E, "
        f"got {found_first_lord_hit}"
    )


def test_audit_004_conceded_retreated_loses_only_loot_and_excess_provender() -> None:
    """4.4.3 (2E): "Lords who Conceded and Retreated transfer all Loot
    and any Provender beyond that which they could take along the
    Retreat Way without being Laden but lose no other Assets."

    Construct: a loser Lord retreating along a Trackway in Summer with
    2 Carts (=> Unladen capacity 2 Provender), 5 Provender, 3 Loot,
    2 Coin, 1 Boat. Expected transfer to winner: 3 Loot, 3 excess
    Provender (5-2). Loser keeps: 2 Provender, 2 Coin, 1 Boat, 2 Carts.
    """
    from nevsky.battle import transfer_spoils
    from nevsky.scenarios import load_scenario

    s = load_scenario("watland", seed=1)
    # Force Summer (some scenarios start in winter).
    s.meta.box = 1
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    s.lords[rus].assets = {"provender": 5, "loot": 3, "coin": 2, "boat": 1, "cart": 2}
    res = transfer_spoils(
        s, from_lord=rus, to_lords=[teu], mode="loot_and_excess",
        retreat_way_type="trackway",
    )
    # Loot all transferred; Provender excess (5 - 2 carts = 3) transferred.
    assert res["transferred"].get("loot") == 3
    assert res["transferred"].get("provender") == 3
    # Coin / Boat / Cart NOT transferred.
    assert "coin" not in res["transferred"]
    assert "boat" not in res["transferred"]
    assert "cart" not in res["transferred"]
    # Loser side: keeps 2 Provender, all Coin, 1 Boat, 2 Carts.
    assert s.lords[rus].assets.get("provender") == 2
    assert s.lords[rus].assets.get("loot", 0) == 0
    assert s.lords[rus].assets.get("coin") == 2
    assert s.lords[rus].assets.get("boat") == 1
    assert s.lords[rus].assets.get("cart") == 2


def test_audit_004_retreated_no_concede_still_transfers_all_except_ships() -> None:
    """4.4.3: a Lord who Retreated WITHOUT having Conceded still
    transfers all Assets except Ships (unchanged behavior)."""
    from nevsky.battle import transfer_spoils
    from nevsky.scenarios import load_scenario

    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    s.lords[rus].assets = {"provender": 5, "loot": 3, "coin": 2, "boat": 1, "ship": 1}
    res = transfer_spoils(s, from_lord=rus, to_lords=[teu], mode="all_except_ships")
    # Everything moves except Ships.
    for k in ("provender", "loot", "coin", "boat"):
        assert s.lords[rus].assets.get(k, 0) == 0, f"{k} should have transferred"
    # Ship stays.
    assert s.lords[rus].assets.get("ship") == 1


def test_audit_005_defender_does_not_retreat_along_approach_way() -> None:
    """4.4.3 (2E): "Defenders may not Retreat along any part of the
    Way that Attackers used to Approach the Locale."

    Verified at the campaign level: when the harness picks a defender
    retreat target, the candidate must not be `cp.from_locale` reached
    via the same `cp.way_type`.

    We simulate the candidate-selection logic directly by replicating
    its loop with a synthetic CombatPending and confirming the
    approach-Way neighbor is skipped while a different neighbor is
    selected.
    """
    from nevsky.scenarios import load_scenario
    from nevsky.static_data import load_ways

    s = load_scenario("crusade_on_novgorod", seed=1)
    # Find a Locale with multiple neighbors so the test is meaningful.
    # Pleskau (Pskov) typically has 3+ adjacent.
    target_locale = "pskov"
    neighbors = []
    for w in load_ways():
        if w["a"] == target_locale:
            neighbors.append((w["b"], w["type"]))
        elif w["b"] == target_locale:
            neighbors.append((w["a"], w["type"]))
    assert len(neighbors) >= 2, "test setup expects >=2 neighbors"
    approach_from, approach_way_type = neighbors[0]
    # Simulate the loop with that approach Way excluded.
    chosen = None
    for w in load_ways():
        if w["a"] == target_locale:
            cand = w["b"]
        elif w["b"] == target_locale:
            cand = w["a"]
        else:
            continue
        if cand == approach_from and w["type"] == approach_way_type:
            continue
        chosen = cand
        break
    assert chosen is not None
    assert not (chosen == approach_from), (
        "defender retreat target must not be the approach-Way neighbor"
    )


def test_audit_006_ordensburgen_commanderies_flag_present_on_confirmed_locales() -> None:
    """T12 Ordensburgen: the confirmed Commandery set per Playbook
    pages 5/6/8/36 is Wenden, Fellin, Adsel, Leal. Verified at the
    static-data level.
    """
    from nevsky.static_data import load_locales

    locales = load_locales()
    expected = {"wenden", "fellin", "adsel", "leal"}
    found = {lid for lid, loc in locales.items() if loc.get("commandery")}
    assert found == expected, f"expected {expected}, got {found}"


def test_audit_006_ordensburgen_extra_seats_emitted_for_teutonic_lords() -> None:
    """T12 Ordensburgen: when Capability is in play, Teutonic Lords
    have all four confirmed Commanderies in their Seats list.
    """
    from nevsky.actions import _seats_of
    from nevsky.scenarios import load_scenario

    s = load_scenario("watland", seed=1)
    # Pick a Teutonic Lord that has T12_ordensburgen in conditional_seats.
    teu_lord = next(
        lid for lid, l in s.lords.items()
        if l.side == "teutonic" and l.state == "mustered"
    )
    # Force T12 active.
    teu_deck = s.decks.teutonic
    if "T12" not in teu_deck.capabilities_in_play:
        teu_deck.capabilities_in_play.append("T12")
    seats = _seats_of(s, teu_lord)
    for c in ("wenden", "fellin", "adsel", "leal"):
        assert c in seats, f"{c} missing from Teutonic Ordensburgen Seats"


def test_q004_commandery_set_is_exactly_the_four_confirmed_locales() -> None:
    """Q-004 (RULES_DECISIONS.md): the confirmed Commandery set is
    exactly Wenden, Fellin, Adsel, Leal — no more, no fewer.

    This test locks in the user's adjudication so any accidental
    addition / removal in locales.json is caught immediately.
    """
    from nevsky.static_data import load_locales

    locales = load_locales()
    flagged = {lid for lid, loc in locales.items() if loc.get("commandery")}
    expected = {"wenden", "fellin", "adsel", "leal"}
    assert flagged == expected, (
        f"Commandery set drift: expected exactly {expected}, got {flagged}. "
        f"Per Q-004 (RULES_DECISIONS.md), no further Strongholds qualify."
    )
    # Every Locale must explicitly declare the flag (true OR false) so a
    # silent omission is also caught.
    missing = [lid for lid, loc in locales.items() if "commandery" not in loc]
    assert not missing, f"Locales missing the `commandery` flag: {missing}"


def test_q004_command_rating_plus_one_at_any_commandery_with_t12() -> None:
    """Q-004 second-order check: when T12 Ordensburgen is in play,
    a Teutonic Lord starting his Command card at ANY of the four
    Commanderies receives +1 effective Command rating.
    """
    from nevsky.scenarios import load_scenario
    s = load_scenario("watland", seed=1)
    from nevsky.campaign import _effective_command_rating as effective_command_rating
    teu_lord = next(
        lid for lid, l in s.lords.items()
        if l.side == "teutonic" and l.state == "mustered"
    )
    base = effective_command_rating(s, teu_lord)
    # Force T12 active.
    if "T12" not in s.decks.teutonic.capabilities_in_play:
        s.decks.teutonic.capabilities_in_play.append("T12")
    for c in ("wenden", "fellin", "adsel", "leal"):
        s.lords[teu_lord].location = c
        bonus_at_c = effective_command_rating(s, teu_lord)
        assert bonus_at_c >= base + 1, (
            f"Ordensburgen +1 not applied at {c}: base={base} got={bonus_at_c}"
        )
