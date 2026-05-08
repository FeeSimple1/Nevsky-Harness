"""Tests for Phase 4a combat-mod capabilities."""

from __future__ import annotations

from nevsky.battle import _absorb_hit, _hits_for_lord_strike
from nevsky.scenarios import load_scenario


def test_luchniki_grants_archery_to_light_horse_and_militia() -> None:
    """R1/R2: Lord with Luchniki: Light Horse + Militia x1/2 Archery each."""
    s = load_scenario("watland", seed=1)
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    s.lords[rus].forces = {"light_horse": 4, "militia": 2}
    # Without Luchniki: archery = 0.
    assert _hits_for_lord_strike(s, rus, "archery") == 0.0
    # Tuck R1 (Luchniki).
    s.lords[rus].this_lord_capabilities = ["R1"]
    # 4 LH * 0.5 + 2 militia * 0.5 = 3.0
    assert _hits_for_lord_strike(s, rus, "archery") == 3.0


def test_streltsy_grants_archery_to_men_at_arms() -> None:
    """R3/R13: Streltsy gives MaA Archery x1/2."""
    s = load_scenario("watland", seed=1)
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    s.lords[rus].forces = {"men_at_arms": 4}
    assert _hits_for_lord_strike(s, rus, "archery") == 0.0
    s.lords[rus].this_lord_capabilities = ["R3"]
    assert _hits_for_lord_strike(s, rus, "archery") == 2.0


def test_balistarii_grants_archery_to_men_at_arms() -> None:
    """T4-T6 Balistarii: same as Streltsy for Teutons."""
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].forces = {"men_at_arms": 3}
    assert _hits_for_lord_strike(s, teu, "archery") == 0.0
    s.lords[teu].this_lord_capabilities = ["T4"]
    assert _hits_for_lord_strike(s, teu, "archery") == 1.5


def test_halbbrueder_armor_plus_one_on_sergeants() -> None:
    """T9/T10: Halbbrueder gives Sergeants Armor +1 (1-3 -> 1-4).

    Statistical test: with Halbbrueder, absorption rate on Sergeants
    should be ~4/6; without, ~3/6. Run 600 hits each, check.
    """
    s_with = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s_with.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s_with.lords[teu].this_lord_capabilities = ["T9"]
    abs_with = sum(1 for _ in range(600) if _absorb_hit(s_with, "sergeants", "melee", lord_id=teu))
    s_without = load_scenario("watland", seed=1)
    abs_without = sum(1 for _ in range(600) if _absorb_hit(s_without, "sergeants", "melee", lord_id=teu))
    # With Halbbrueder: ~4/6 = 400/600; without: ~3/6 = 300/600.
    assert abs_with > abs_without
    assert 350 <= abs_with <= 450
    assert 250 <= abs_without <= 350


def test_warrior_monks_rerolls_failed_knights_armor() -> None:
    """T7/T15: Warrior Monks reroll Knights Armor. Statistical test:
    success rate roughly 1 - (1 - 4/6)^2 = 8/9 = ~533/600 vs 4/6 = 400/600."""
    s_with = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s_with.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s_with.lords[teu].this_lord_capabilities = ["T7"]
    abs_with = sum(1 for _ in range(600) if _absorb_hit(s_with, "knights", "melee", lord_id=teu))
    s_without = load_scenario("watland", seed=1)
    abs_without = sum(1 for _ in range(600) if _absorb_hit(s_without, "knights", "melee", lord_id=teu))
    assert abs_with > abs_without
    assert 480 <= abs_with <= 580  # ~8/9
    assert 350 <= abs_without <= 450  # ~4/6


def test_streltsy_armor_minus_2_at_target() -> None:
    """3.4.4: Streltsy/Balistarii Archery imposes target Armor -2.
    Sergeants Armor 1-3 - 2 = 1-1; absorption ~1/6."""
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    abs_minus2 = sum(1 for _ in range(600) if _absorb_hit(s, "sergeants", "archery", lord_id=teu, striker_has_armor_minus_2=True))
    abs_normal = sum(1 for _ in range(600) if _absorb_hit(s, "sergeants", "archery", lord_id=teu))
    assert abs_minus2 < abs_normal
    assert 50 <= abs_minus2 <= 150
