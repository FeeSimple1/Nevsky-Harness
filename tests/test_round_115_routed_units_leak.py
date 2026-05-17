"""SMOKE-095 (Round 115): Lord removed/disbanded with routed_units
still set — pile leaks across the Lord lifecycle.

When a Lord is permanently removed (_remove_lord_permanently) or
disbanded at the End-Levy 3.3.2 limit (_disband_at_limit), the
harness cleared `forces` and `assets` but never cleared
`routed_units`. Stale routed units would:
  - persist on a removed Lord (state-consistency issue),
  - and worse, persist on a disbanded Lord — which per SMOKE-044
    can re-Muster — causing the re-Mustered Lord to carry ghost
    routed units from a previous incarnation.

The fix calls battle.clear_routed_pile(state, lord_id) in both
paths. clear_routed_pile was previously dead code (defined but
no callers); SMOKE-095 gives it its intended use site.
"""
from __future__ import annotations

import nevsky.actions  # noqa: F401
from nevsky.actions import (
    _disband_at_limit,
    _remove_lord_permanently,
    apply_action,
)
from nevsky.scenarios import load_scenario


def _setup_state():
    s = load_scenario("watland", seed=11)
    apply_action(s, {"type": "confirm_all_setup_transports",
                     "side": "teutonic", "args": {}})
    return s


def test_permanent_removal_clears_routed_units():
    s = _setup_state()
    teu = next(lid for lid, l in s.lords.items()
               if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].routed_units = {"asgard": 2, "serjeant": 1}
    _remove_lord_permanently(s, teu, {})
    assert s.lords[teu].state == "removed"
    assert s.lords[teu].routed_units == {}


def test_disband_at_limit_clears_routed_units():
    s = _setup_state()
    teu = next(lid for lid, l in s.lords.items()
               if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].routed_units = {"knights": 1, "men_at_arms": 2}
    _disband_at_limit(s, teu, 17)
    assert s.lords[teu].state == "disbanded"
    assert s.lords[teu].routed_units == {}


def test_clear_routed_pile_now_has_callers():
    """clear_routed_pile was previously dead code; SMOKE-095 gives
    it real callers. Verify via source inspection."""
    import inspect
    import nevsky.actions as actions_mod
    src = inspect.getsource(actions_mod)
    assert "clear_routed_pile" in src
    assert src.count("clear_routed_pile") >= 3  # 2 imports + 2 calls
