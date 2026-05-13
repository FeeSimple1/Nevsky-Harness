"""Round 57 — SMOKE-045 regression tests.

Re-Conquest of an already-Conquered locale by the same side should
not stack the conquered count past sh_vp (City = 2 markers; Novgorod
= 3; Fort = 1). Practically rare due to siege-state gating but a
latent defensive bug if a flow ever reaches it.
"""

import nevsky.actions  # noqa
from nevsky.scenarios import load_scenario
from nevsky.campaign import _apply_conquest_or_liberation


def test_city_double_conquest_caps_at_vp():
    st = load_scenario("pleskau", seed=1)
    loc = st.locales["pskov"]
    # First Conquest: 0 → 2
    change1 = _apply_conquest_or_liberation(st, "pskov", "teutonic", 2)
    assert loc.teutonic_conquered == 2
    assert change1["vp"] == 2
    # Second Conquest: should stay at 2, emit delta=0
    teu_vp_before = st.calendar.teutonic_vp
    change2 = _apply_conquest_or_liberation(st, "pskov", "teutonic", 2)
    assert loc.teutonic_conquered == 2
    assert change2["vp"] == 0
    assert st.calendar.teutonic_vp == teu_vp_before


def test_novgorod_single_conquest_full_vp():
    st = load_scenario("pleskau", seed=1)
    loc = st.locales["novgorod"]
    change = _apply_conquest_or_liberation(st, "novgorod", "teutonic", 3)
    assert loc.teutonic_conquered == 3
    assert change["vp"] == 3


def test_partial_conquest_then_full_emits_correct_delta():
    """Defensive: if conquered=1 (partial) and full sh_vp=2 hits, delta=1."""
    st = load_scenario("pleskau", seed=1)
    loc = st.locales["pskov"]
    loc.teutonic_conquered = 1  # artificially partial
    teu_vp_before = st.calendar.teutonic_vp
    change = _apply_conquest_or_liberation(st, "pskov", "teutonic", 2)
    assert loc.teutonic_conquered == 2
    assert change["vp"] == 1
    assert st.calendar.teutonic_vp == teu_vp_before + 1.0
