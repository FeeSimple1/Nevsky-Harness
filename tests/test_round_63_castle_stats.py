"""Round 63 — SMOKE-054 regression tests.

T17 Stonemasons Tip: "The Castle marker REPLACES the Fort or Town at
its Locale." A locale with a Castle marker should use Castle stats
(capacity 2, walls 1-4, garrison 1 MaA + 1 Knight, vp 1) for
Siege/Storm/Withdraw purposes, not its static-type Fort stats.
"""

import nevsky.actions  # noqa
from nevsky.scenarios import load_scenario
from nevsky.campaign import _effective_stronghold, _stronghold_at


def test_fort_without_castle_marker_uses_fort_stats():
    """Sanity baseline: static Fort with no Castle uses Fort stats."""
    st = load_scenario("pleskau", seed=1)
    base = _stronghold_at("kaibolovo")
    eff = _effective_stronghold(st, "kaibolovo")
    assert eff["capacity"] == base["capacity"] == 1
    assert eff["walls_max"] == base["walls_max"] == 3
    assert eff["vp"] == 1


def test_fort_with_teutonic_castle_marker_uses_castle_stats():
    """T17 Stonemasons converted a Russian Fort: Castle stats apply."""
    st = load_scenario("pleskau", seed=1)
    st.locales["kaibolovo"].teutonic_castle = True
    eff = _effective_stronghold(st, "kaibolovo")
    assert eff["capacity"] == 2  # Castle
    assert eff["walls_max"] == 4  # Castle
    assert eff["vp"] == 1
    # Side stays static (the locale's territory owner) — not the Castle
    # marker's color (Stonemasons doesn't transfer ownership).
    assert eff["side"] == "russian"


def test_fort_with_russian_castle_marker_uses_castle_stats():
    st = load_scenario("pleskau", seed=1)
    st.locales["kaibolovo"].russian_castle = True
    eff = _effective_stronghold(st, "kaibolovo")
    assert eff["capacity"] == 2
    assert eff["walls_max"] == 4


def test_castle_garrison_overlay():
    """Castle Garrison: 1 MaA + 1 Knight (vs Fort 1 MaA + 0 Knight)."""
    st = load_scenario("pleskau", seed=1)
    st.locales["kaibolovo"].teutonic_castle = True
    eff = _effective_stronghold(st, "kaibolovo")
    assert eff["garrison"].get("knights", 0) == 1
    assert eff["garrison"].get("men_at_arms", 0) == 1


def test_locale_without_stronghold_unchanged():
    """A non-Stronghold locale (region/trade_route/etc) returns None
    regardless of Castle bool state."""
    st = load_scenario("pleskau", seed=1)
    # Find a non-Stronghold locale (region or trade_route)
    from nevsky.static_data import load_locales
    for lid, lc in load_locales().items():
        if lc.get("type") == "region" and lid in st.locales:
            # Setting castle on a non-Stronghold is nonsensical, but the
            # helper should still cope (base is None → return None).
            eff = _effective_stronghold(st, lid)
            assert eff is None
            return


# -----------------------------------------------------------------
# SMOKE-054 follow-up: Withdraw capacity respects Castle marker.
# -----------------------------------------------------------------

import pytest
from nevsky.actions import IllegalAction, apply_action
from nevsky.state import CombatPending


def _setup_withdraw(target_locale):
    st = load_scenario("pleskau", seed=1)
    # Russian Lord at target Stronghold; Teutonic attacker arrived from
    # neighbor.
    g = st.lords["gavrilo"]
    g.location = target_locale
    h = st.lords["hermann"]
    h.location = target_locale  # arrived at the locale
    st.combat_pending = CombatPending(
        attacker_side="teutonic", attacker_group=["hermann"],
        from_locale="pskov",
        to_locale=target_locale,
        way_type="trackway",
        defender_side="russian",
        defender_lords=["gavrilo"],
        pending_response_by="russian",
        laden=False,
    )
    return st


def test_castle_marker_doubles_withdraw_capacity():
    """A Castle-marked Russian Fort should accept a 2-Lord Withdraw
    (capacity 2 from Castle, not Fort's capacity 1)."""
    st = _setup_withdraw("kaibolovo")
    st.locales["kaibolovo"].teutonic_castle = True
    # Add a 2nd defender
    v = st.lords["vladislav"]
    v.location = "kaibolovo"
    st.combat_pending.defender_lords = ["gavrilo", "vladislav"]
    # 2 defenders, Castle capacity 2 → should succeed
    res = apply_action(st, {"type": "withdraw", "side": "russian", "args": {}})
    assert res["capacity"] == 2


def test_no_castle_keeps_fort_capacity():
    """Without Castle marker, Fort capacity 1 limits Withdraw."""
    st = _setup_withdraw("kaibolovo")
    # 2 defenders, Fort capacity 1 → should fail
    v = st.lords["vladislav"]
    v.location = "kaibolovo"
    st.combat_pending.defender_lords = ["gavrilo", "vladislav"]
    with pytest.raises(IllegalAction) as exc:
        apply_action(st, {"type": "withdraw", "side": "russian", "args": {}})
    assert exc.value.code == "over_capacity"
