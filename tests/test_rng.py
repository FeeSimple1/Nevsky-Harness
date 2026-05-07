"""Tests for the seeded RNG (BRIEF: every dice roll reproducible from seed)."""

from __future__ import annotations

from nevsky.rng import roll_d6, shuffle
from nevsky.scenarios import load_scenario


def test_roll_d6_in_range_and_advances_state() -> None:
    s = load_scenario("pleskau", seed=42)
    start = s.meta.rng_state
    r = roll_d6(s)
    assert 1 <= r <= 6
    assert s.meta.rng_state == start + 1


def test_roll_d6_deterministic_for_same_seed_and_state() -> None:
    s1 = load_scenario("pleskau", seed=42)
    s2 = load_scenario("pleskau", seed=42)
    rolls1 = [roll_d6(s1) for _ in range(20)]
    rolls2 = [roll_d6(s2) for _ in range(20)]
    assert rolls1 == rolls2


def test_roll_d6_differs_across_seeds() -> None:
    s_a = load_scenario("pleskau", seed=1)
    s_b = load_scenario("pleskau", seed=2)
    a = [roll_d6(s_a) for _ in range(10)]
    b = [roll_d6(s_b) for _ in range(10)]
    assert a != b  # vanishingly unlikely to collide


def test_shuffle_deterministic_and_doesnt_mutate_input() -> None:
    s = load_scenario("pleskau", seed=42)
    items = ["a", "b", "c", "d", "e"]
    out = shuffle(s, items)
    assert sorted(out) == sorted(items)
    assert items == ["a", "b", "c", "d", "e"]  # not mutated


def test_shuffle_repeats_same_with_same_state() -> None:
    s1 = load_scenario("pleskau", seed=42)
    s2 = load_scenario("pleskau", seed=42)
    items = list("abcdefgh")
    assert shuffle(s1, items) == shuffle(s2, items)
