"""Round 46 — SMOKE-033 regression tests.

Lord permanent removal (3.3.1) and at-limit Disband (3.3.2) must
dissolve any Lieutenant/Lower-Lord stack the Lord was part of.
Per Sequence of Play 4.1.3: "if either is removed/Disbanded, the
survivor reverts to a normal Lord."
"""

import pytest

from nevsky.scenarios import load_scenario
from nevsky.actions import _disband_at_limit, _remove_lord_permanently
from nevsky.static_data import load_lords


def _two_mustered_same_side(state, side):
    return [lid for lid, L in state.lords.items() if L.side == side and L.state == "mustered"][:2]


def test_remove_lieutenant_clears_marshal_pointer():
    """Removing the Lieutenant (Lower Lord position) clears the Marshal's has_lower_lord."""
    st = load_scenario("pleskau", seed=1)
    static = load_lords()
    a, b = _two_mustered_same_side(st, "teutonic")
    # b is Marshal (has_lower_lord = a), a is Lieutenant (lieutenant_of = b)
    st.lords[b].has_lower_lord = a
    st.lords[a].lieutenant_of = b
    _remove_lord_permanently(st, a, static[a])
    assert st.lords[a].state == "removed"
    assert st.lords[a].lieutenant_of is None
    assert st.lords[b].has_lower_lord is None


def test_remove_marshal_clears_lieutenant_pointer():
    """Removing the Marshal clears the Lieutenant's lieutenant_of."""
    st = load_scenario("pleskau", seed=1)
    static = load_lords()
    a, b = _two_mustered_same_side(st, "teutonic")
    st.lords[b].has_lower_lord = a
    st.lords[a].lieutenant_of = b
    _remove_lord_permanently(st, b, static[b])
    assert st.lords[b].state == "removed"
    assert st.lords[b].has_lower_lord is None
    assert st.lords[a].lieutenant_of is None


def test_disband_lieutenant_clears_marshal_pointer():
    """Disband-at-limit (3.3.2) of the Lower Lord dissolves the stack."""
    st = load_scenario("pleskau", seed=1)
    a, b = _two_mustered_same_side(st, "teutonic")
    st.lords[b].has_lower_lord = a
    st.lords[a].lieutenant_of = b
    _disband_at_limit(st, a, 4)
    assert st.lords[a].state == "disbanded"
    assert st.lords[a].lieutenant_of is None
    assert st.lords[b].has_lower_lord is None


def test_disband_marshal_clears_lieutenant_pointer():
    """Disband-at-limit of the Marshal dissolves the stack."""
    st = load_scenario("pleskau", seed=1)
    a, b = _two_mustered_same_side(st, "teutonic")
    st.lords[b].has_lower_lord = a
    st.lords[a].lieutenant_of = b
    _disband_at_limit(st, b, 4)
    assert st.lords[b].state == "disbanded"
    assert st.lords[b].has_lower_lord is None
    assert st.lords[a].lieutenant_of is None


def test_remove_no_stack_no_side_effects():
    """Removing an unstacked Lord touches neither field on others."""
    st = load_scenario("pleskau", seed=1)
    static = load_lords()
    a = _two_mustered_same_side(st, "teutonic")[0]
    # Save snapshot of partner fields
    others = {lid: (L.lieutenant_of, L.has_lower_lord)
              for lid, L in st.lords.items() if lid != a}
    _remove_lord_permanently(st, a, static[a])
    for lid, L in st.lords.items():
        if lid == a:
            continue
        assert L.lieutenant_of == others[lid][0]
        assert L.has_lower_lord == others[lid][1]


def test_remove_already_removed_idempotent():
    """Calling _remove_lord_permanently twice does not blow up the partner."""
    st = load_scenario("pleskau", seed=1)
    static = load_lords()
    a, b = _two_mustered_same_side(st, "teutonic")
    st.lords[b].has_lower_lord = a
    st.lords[a].lieutenant_of = b
    _remove_lord_permanently(st, a, static[a])
    # Second call — early-return path
    _remove_lord_permanently(st, a, static[a])
    # b's pointer remains cleared, not somehow restored
    assert st.lords[b].has_lower_lord is None


def test_remove_dangling_partner_id_safe():
    """If partner pointer points at a missing Lord, no AttributeError."""
    st = load_scenario("pleskau", seed=1)
    static = load_lords()
    a = _two_mustered_same_side(st, "teutonic")[0]
    # Inject a stale lieutenant_of pointing at a non-existent Lord
    st.lords[a].lieutenant_of = "nonexistent_lord"
    # Must not crash
    _remove_lord_permanently(st, a, static[a])
    assert st.lords[a].lieutenant_of is None


def test_remove_partner_mismatch_does_not_clobber():
    """If partner's back-pointer points elsewhere, don't blindly None it.

    Defensive: if Lord A's lieutenant_of == B but B's has_lower_lord ==
    C (some other lord), removing A should NOT clear B.has_lower_lord
    (which legitimately belongs to C).
    """
    st = load_scenario("pleskau", seed=1)
    static = load_lords()
    same = [lid for lid, L in st.lords.items() if L.side == "teutonic" and L.state == "mustered"]
    a, b, c = same[0], same[1], same[2]
    st.lords[a].lieutenant_of = b   # claimed stale ref
    st.lords[b].has_lower_lord = c  # actual stack is b<-c
    st.lords[c].lieutenant_of = b
    _remove_lord_permanently(st, a, static[a])
    # b should still believe c is its Lower Lord
    assert st.lords[b].has_lower_lord == c
    assert st.lords[c].lieutenant_of == b


# -----------------------------------------------------------------
# SMOKE-034: Lieutenant March must include Lower Lord (4.1.3)
# -----------------------------------------------------------------

from nevsky.actions import apply_action, IllegalAction
from nevsky.static_data import load_ways as _load_ways


def _setup_lt_march(seed=1):
    """Build a state with yaroslav (Lieutenant) + hermann (Lower Lord)
    at the same Locale, primed for cmd_march under campaign.command."""
    st = load_scenario("pleskau", seed=seed)
    y = st.lords["yaroslav"]
    h = st.lords["hermann"]
    h.location = y.location
    y.lieutenant_of = None
    y.has_lower_lord = "hermann"
    h.lieutenant_of = "yaroslav"
    h.has_lower_lord = None
    st.meta.phase = "campaign"
    st.meta.campaign_step = "command"
    st.campaign_turn.active_lord = "yaroslav"
    st.campaign_turn.active_card = "yaroslav"
    st.campaign_turn.actions_remaining = 5
    # Pick an adjacent locale
    for w in _load_ways():
        if w["a"] == y.location:
            return st, w["b"]
        if w["b"] == y.location:
            return st, w["a"]
    raise AssertionError("no adjacent")


def test_lt_march_without_lower_lord_rejected():
    """SMOKE-034: a Lieutenant marching without their Lower Lord is illegal."""
    st, dest = _setup_lt_march()
    with pytest.raises(IllegalAction) as exc:
        apply_action(st, {"type": "cmd_march", "side": "teutonic",
                          "args": {"lord_id": "yaroslav", "to": dest,
                                   "group": ["yaroslav"]}})
    assert exc.value.code == "lower_lord_required"
    # Neither Lord should have moved
    assert st.lords["hermann"].location == st.lords["yaroslav"].location  # both still at src


def test_lt_march_with_lower_lord_allowed():
    """Lieutenant march with Lower Lord in the group is fine."""
    st, dest = _setup_lt_march()
    src = st.lords["yaroslav"].location
    result = apply_action(st, {"type": "cmd_march", "side": "teutonic",
                              "args": {"lord_id": "yaroslav", "to": dest,
                                       "group": ["yaroslav", "hermann"]}})
    assert result["to"] == dest
    assert st.lords["yaroslav"].location == dest
    assert st.lords["hermann"].location == dest


def test_marshal_with_lower_lord_must_include_lower_lord():
    """A non-Lieutenant active Lord with has_lower_lord set must also bring
    them (the rule is symmetric — has_lower_lord means there IS a Lower
    Lord on this Lord, and they move together)."""
    st, dest = _setup_lt_march()
    # Same setup: yaroslav has_lower_lord = hermann. Try marching without.
    with pytest.raises(IllegalAction) as exc:
        apply_action(st, {"type": "cmd_march", "side": "teutonic",
                          "args": {"lord_id": "yaroslav", "to": dest, "group": ["yaroslav"]}})
    assert exc.value.code == "lower_lord_required"


def test_unstacked_lord_march_no_constraint():
    """A Lord with no Lower Lord stacked may march alone."""
    st, dest = _setup_lt_march()
    # Unstack
    st.lords["yaroslav"].has_lower_lord = None
    st.lords["hermann"].lieutenant_of = None
    # Now march yaroslav alone
    result = apply_action(st, {"type": "cmd_march", "side": "teutonic",
                              "args": {"lord_id": "yaroslav", "to": dest, "group": ["yaroslav"]}})
    assert result["to"] == dest
    assert st.lords["yaroslav"].location == dest
    # hermann stays
    assert st.lords["hermann"].location != dest
