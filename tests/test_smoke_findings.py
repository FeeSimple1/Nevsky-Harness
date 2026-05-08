"""Regression tests from the active-play smoke test.

Each test cites a specific bug found by playing the harness against a
real scenario. See SMOKE_TEST_FINDINGS.md for the full report.
"""

from __future__ import annotations

from nevsky.actions import apply_action
from nevsky.scenarios import load_scenario


def test_smoke_fpd_skips_removed_lord_with_stale_moved_fought() -> None:
    """SMOKE-001: 4.8 Feed previously processed Lords whose state had
    transitioned to 'removed' during Battle/Storm aftermath because
    moved_fought was set BEFORE the permanent removal. After fix, FPD
    skips non-mustered Lords and clears their stale moved_fought."""
    s = load_scenario("pleskau", seed=11)
    # Simulate post-Battle removal state.
    s.lords["hermann"].state = "removed"
    s.lords["hermann"].forces = {}
    s.lords["hermann"].location = None
    s.lords["hermann"].moved_fought = True
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "teutonic"
    s.campaign_turn.in_feed_pay_disband = True
    s.campaign_turn.fpd_completed_t = False
    s.campaign_turn.fpd_completed_r = False
    res = apply_action(s, {"type": "fpd_resolve", "side": "teutonic", "args": {}})
    # No feed entry for hermann (he was removed, not Mustered).
    feeds_for_hermann = [f for f in res["feed"] if f.get("lord_id") == "hermann"]
    assert feeds_for_hermann == []
    # moved_fought cleared.
    assert s.lords["hermann"].moved_fought is False
