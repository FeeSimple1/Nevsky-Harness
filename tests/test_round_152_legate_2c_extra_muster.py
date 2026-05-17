"""SMOKE-106 (Round 152): Legate Use sub-option 2c "extra Muster" set
lordship_used=0 but Muster handlers required levy_step=='muster', so
the granted Muster could not actually be performed during
call_to_arms.

Per Call to Arms reference, sub-option 2c:
    "That Lord (must be Mustered and at this Friendly Locale)
     performs an immediate EXTRA Muster using his FULL Lordship
     Rating. All Muster options (3.4.1-3.4.4) are available to him —
     Levy other Lords, Levy Vassals, Levy Transport, Levy
     Capabilities — at this moment, in addition to whatever he did
     during the regular Muster segment."

Pre-fix the harness set lordship_used=0 + just_arrived_this_levy=
False on the target, but each Muster handler hard-required
levy_step=='muster'. The agent literally could not invoke any Muster
action during the granted CtA segment.

Fix:
  - Add `Legate.extra_muster_target_lord: str | None`.
  - _h_legate_use 2c records the target Lord id there.
  - All four Muster handlers (_h_muster_lord, _h_muster_vassal,
    _h_levy_transport, _h_levy_capability) gate via
    _require_muster_or_legate_2c_extra(state, by_lord_id) which
    accepts levy_step=='muster' (normal path) OR call_to_arms when
    the target matches.
  - advance_step clears the flag on CtA->done transition.
"""
from __future__ import annotations

import inspect

import nevsky.actions as actions
import nevsky.state as state_mod
import pytest


def test_smoke_106_marker_in_legate_use():
    src = inspect.getsource(actions._h_legate_use)
    assert "SMOKE-106" in src
    assert "extra_muster_target_lord" in src


def test_smoke_106_marker_in_state_legate():
    src = inspect.getsource(state_mod.Legate)
    assert "SMOKE-106" in src
    assert "extra_muster_target_lord" in src


def test_smoke_106_helper_function_present():
    assert hasattr(actions, "_require_muster_or_legate_2c_extra")
    src = inspect.getsource(actions._require_muster_or_legate_2c_extra)
    assert "SMOKE-106" in src
    assert "extra_muster_target_lord" in src


def test_smoke_106_muster_lord_uses_helper():
    src = inspect.getsource(actions._h_muster_lord)
    assert "_require_muster_or_legate_2c_extra" in src


def test_smoke_106_muster_vassal_uses_helper():
    src = inspect.getsource(actions._h_muster_vassal)
    assert "_require_muster_or_legate_2c_extra" in src


def test_smoke_106_levy_transport_uses_helper():
    src = inspect.getsource(actions._h_levy_transport)
    assert "_require_muster_or_legate_2c_extra" in src


def test_smoke_106_levy_capability_uses_helper():
    src = inspect.getsource(actions._h_levy_capability)
    assert "_require_muster_or_legate_2c_extra" in src


def test_smoke_106_advance_step_clears_flag():
    """When CtA -> done, the Legate-2c extra-muster target flag clears."""
    src = inspect.getsource(actions._h_advance_step)
    # Find the SMOKE-106 reset
    idx = src.find("SMOKE-106")
    assert idx > 0
    nearby = src[idx:idx + 400]
    assert "extra_muster_target_lord = None" in nearby


def test_smoke_106_helper_rejects_other_lord_in_cta():
    """Helper rejects a different by_lord_id during call_to_arms."""
    from nevsky.scenarios import load_scenario
    s = load_scenario("watland", seed=1)
    s.meta.phase = "levy"
    s.meta.levy_step = "call_to_arms"
    s.legate.extra_muster_target_lord = "andreas"
    # Different Lord -> rejected
    with pytest.raises(actions.IllegalAction):
        actions._require_muster_or_legate_2c_extra(s, "rudolf")


def test_smoke_106_helper_accepts_matching_lord_in_cta():
    """Helper accepts by_lord_id matching the legate target during CtA."""
    from nevsky.scenarios import load_scenario
    s = load_scenario("watland", seed=1)
    s.meta.phase = "levy"
    s.meta.levy_step = "call_to_arms"
    s.legate.extra_muster_target_lord = "andreas"
    # Matching Lord -> no exception
    actions._require_muster_or_legate_2c_extra(s, "andreas")


def test_smoke_106_helper_accepts_any_lord_in_muster_step():
    """In muster step, helper accepts any by_lord regardless of flag."""
    from nevsky.scenarios import load_scenario
    s = load_scenario("watland", seed=1)
    s.meta.phase = "levy"
    s.meta.levy_step = "muster"
    s.legate.extra_muster_target_lord = None
    actions._require_muster_or_legate_2c_extra(s, "andreas")
    actions._require_muster_or_legate_2c_extra(s, "rudolf")
