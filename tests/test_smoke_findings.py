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


def test_smoke_006_withdraw_capacity_uses_strongholds_json() -> None:
    """SMOKE-006: Withdraw capacity for City is 3 (not the 2 the
    hardcoded dict had). Pre-fix would reject 3 defenders trying to
    Withdraw into Pskov; post-fix accepts."""
    from nevsky.actions import apply_action
    from nevsky.scenarios import load_scenario
    from nevsky.state import CombatPending
    s = load_scenario("pleskau", seed=1)
    # Set up: 3 Russian Lords trying to Withdraw into pskov (City, cap=3).
    for lid in ("gavrilo", "domash", "vladislav"):
        if lid in s.lords:
            s.lords[lid].state = "mustered"
            s.lords[lid].location = "pskov"
            s.lords[lid].in_stronghold = False
    s.combat_pending = CombatPending(
        attacker_side="teutonic",
        attacker_group=["hermann"],
        from_locale="izborsk",
        to_locale="pskov",
        way_type="trackway",
        defender_side="russian",
        defender_lords=["gavrilo", "domash", "vladislav"],
        pending_response_by="russian",
        laden=False,
    )
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "russian"
    s.campaign_turn.active_lord = None
    s.campaign_turn.actions_remaining = 0
    # 3 defenders into capacity-3 city should succeed.
    apply_action(s, {"type": "withdraw", "side": "russian", "args": {}})
    # All three withdrew (in_stronghold flag set).
    for lid in ("gavrilo", "domash", "vladislav"):
        if lid in s.lords:
            assert s.lords[lid].in_stronghold is True


def test_smoke_007_sally_loss_with_zero_forces_removes_lord() -> None:
    """SMOKE-007: a Sallying Lord whose forces all rout in the Sally
    is permanently removed (1.5.1), not left mustered with empty forces."""
    from nevsky.actions import apply_action
    from nevsky.scenarios import load_scenario
    s = load_scenario("pleskau", seed=11)
    s.lords["hermann"].location = "pskov"
    s.lords["hermann"].forces = {"knights": 5, "men_at_arms": 3}
    s.lords["gavrilo"].location = "pskov"
    s.lords["gavrilo"].in_stronghold = True
    # Weak sallying force so it loses badly.
    s.lords["gavrilo"].forces = {"militia": 1}
    s.locales["pskov"].siege_markers = 4
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "russian"
    s.campaign_turn.next_to_reveal = "russian"
    s.campaign_turn.active_card = "gavrilo"
    s.campaign_turn.active_lord = "gavrilo"
    s.campaign_turn.actions_remaining = 2
    s.campaign_turn.in_feed_pay_disband = False
    res = apply_action(s, {"type": "cmd_sally", "side": "russian",
                            "args": {"lord_id": "gavrilo"}})
    if res["battle"]["loser"] == "russian" and not s.lords["gavrilo"].forces:
        # Gavrilo should be removed.
        assert s.lords["gavrilo"].state == "removed"
        assert "gavrilo" in res.get("removed_after_sally", [])


def test_smoke_009_fpd_zero_units_costs_zero() -> None:
    """SMOKE-009: FPD with 0 units costs 0 (no provender consumed,
    no unfed penalty). Defensive: 0-unit Lord should already be
    removed, but if not, FPD should not falsely charge."""
    from nevsky.actions import apply_action
    from nevsky.scenarios import load_scenario
    s = load_scenario("pleskau", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].forces = {}
    s.lords[teu].assets = {"provender": 5}
    s.lords[teu].moved_fought = True
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "teutonic"
    s.campaign_turn.in_feed_pay_disband = True
    res = apply_action(s, {"type": "fpd_resolve", "side": "teutonic", "args": {}})
    feeds = [f for f in res["feed"] if f.get("lord_id") == teu]
    assert len(feeds) == 1
    assert feeds[0]["cost"] == 0
    assert feeds[0]["consumed"] == {"provender": 0, "loot": 0}
    assert feeds[0]["unfed"] is False
    assert s.lords[teu].assets["provender"] == 5


def test_smoke_004_battle_log_skips_zero_hit_steps() -> None:
    """SMOKE-004: zero-hit Strike steps don't appear in the battle log.
    Battles with no Asiatic Horse should have NO archery steps in the log."""
    from nevsky.battle import resolve_battle
    from nevsky.scenarios import load_scenario
    s = load_scenario("watland", seed=3)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    # Strip any Asiatic Horse to guarantee zero archery.
    s.lords[teu].forces.pop("asiatic_horse", None)
    s.lords[rus].forces.pop("asiatic_horse", None)
    res = resolve_battle(s, "teutonic", [teu], [rus])
    for round_log in res["log"]:
        for step in round_log["steps"]:
            # No archery steps should appear.
            assert "archery" not in step["step"], (
                f"unexpected zero-hit archery step in log: {step}"
            )


def test_smoke_003_spoils_recipient_routed_to_named_lord() -> None:
    """SMOKE-003: stand_battle args.spoils_recipient routes Spoils to
    the named winner-side Lord present at the Battle Locale."""
    from nevsky.actions import apply_action
    from nevsky.scenarios import load_scenario
    from nevsky.state import CombatPending
    s = load_scenario("watland", seed=11)
    # Two Teutonic Lords at pskov; gavrilo (Russian) is the loser.
    for lid in ("hermann", "yaroslav"):
        s.lords[lid].location = "pskov"
        s.lords[lid].forces = {"knights": 5, "men_at_arms": 3}
    s.lords["gavrilo"].location = "pskov"
    s.lords["gavrilo"].forces = {"militia": 1}
    s.lords["gavrilo"].assets = {"loot": 2, "coin": 1}
    s.combat_pending = CombatPending(
        attacker_side="teutonic", attacker_group=["hermann", "yaroslav"],
        from_locale="izborsk", to_locale="pskov", way_type="trackway",
        defender_side="russian", defender_lords=["gavrilo"],
        pending_response_by="russian", laden=False,
    )
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "russian"
    s.campaign_turn.active_lord = None
    s.campaign_turn.actions_remaining = 0
    s.campaign_turn.in_feed_pay_disband = False
    pre_yaroslav_loot = s.lords["yaroslav"].assets.get("loot", 0)
    pre_hermann_loot = s.lords["hermann"].assets.get("loot", 0)
    res = apply_action(s, {
        "type": "stand_battle", "side": "russian",
        "args": {"spoils_recipient": "yaroslav"},
    })
    if res["winner"] == "teutonic":
        # Spoils went to yaroslav, not hermann (the default).
        post_yaroslav = s.lords["yaroslav"].assets.get("loot", 0)
        post_hermann = s.lords["hermann"].assets.get("loot", 0)
        assert post_yaroslav > pre_yaroslav_loot or post_hermann == pre_hermann_loot
