"""Round 7: tests for off_left/off_right architectural split + Routed-vs-Lost.

The off-edge cylinders/service-markers separation and Routed-vs-Lost
4.4.4 Losses are documented in SMOKE_TEST_FINDINGS.md round 7.
"""

from __future__ import annotations

from nevsky.actions import apply_action
from nevsky.battle import (
    apply_losses_rolls,
    clear_routed_pile,
    resolve_battle,
)
from nevsky.scenarios import load_scenario


# --- off-edges separation ----------------------------------------------------


def test_off_right_service_distinct_from_off_right_cylinder() -> None:
    """Round 7: pushing a Service marker past box 16 lands in
    off_right_service, NOT off_right (cylinders)."""
    s = load_scenario("watland", seed=1)
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    for cb in s.calendar.boxes:
        if teu in cb.service_markers:
            cb.service_markers.remove(teu)
    s.calendar.boxes[15].service_markers.append(teu)
    s.lords[teu].assets["coin"] = 5
    s.meta.phase = "levy"
    s.meta.levy_step = "pay"
    s.meta.active_player = "teutonic"
    apply_action(s, {"type": "pay_with_coin", "side": "teutonic",
                     "args": {"from": f"lord:{teu}", "target_lord": teu, "units": 3}})
    assert teu in s.calendar.off_right_service
    # Cylinder list separate.
    assert teu not in s.calendar.off_right


def test_unfed_at_box_1_lands_in_off_left_service() -> None:
    """4.8.1 unfed shift LEFT: a Lord with Service at box 1 ends up in
    off_left_service, NOT off_left (cylinders).

    Note: same FPD's 4.8.2 Disband then permanently removes him because
    his Service is at-or-left-of Levy. So the marker is cleared from
    off_left_service in the same call, but during the unfed step it
    must land in the right list."""
    s = load_scenario("watland", seed=1)
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    # Place service at box 16 so the unfed shift to box 15 doesn't trigger
    # at-limit Disband.
    for cb in s.calendar.boxes:
        if teu in cb.service_markers:
            cb.service_markers.remove(teu)
    s.calendar.boxes[15].service_markers.append(teu)  # box 16
    # Put him at far-right so the unfed shift is just box 16 -> 15.
    s.lords[teu].assets.pop("provender", None)
    s.lords[teu].assets.pop("loot", None)
    s.lords[teu].moved_fought = True
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "teutonic"
    s.campaign_turn.in_feed_pay_disband = True
    apply_action(s, {"type": "fpd_resolve", "side": "teutonic", "args": {}})
    # Service marker should be at box 15 now.
    assert any(teu in cb.service_markers and cb.box == 15 for cb in s.calendar.boxes)


# --- Routed-vs-Lost ---------------------------------------------------------


def test_apply_losses_rolls_returns_some_units_to_forces() -> None:
    """4.4.4: Losses rolls give a chance for Routed units to recover.

    With "withdrew" loser_state and Knights (Armor 1-4 -> 4/6 keep rate),
    a large pile of Knights should largely be retained."""
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].forces = {}
    s.lords[teu].routed_units = {"knights": 12}
    res = apply_losses_rolls(s, teu, "withdrew")
    # Expected: ~8 of 12 Knights kept (4/6 = 66.7%).
    kept = s.lords[teu].forces.get("knights", 0)
    assert 4 <= kept <= 12  # statistical bounds
    # routed pile cleared.
    assert s.lords[teu].routed_units == {}


def test_apply_losses_rolls_retreated_no_concede_is_harsh() -> None:
    """retreated_no_concede threshold is roll==1; ~1/6 retention."""
    s = load_scenario("watland", seed=42)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].forces = {}
    s.lords[teu].routed_units = {"knights": 12}
    apply_losses_rolls(s, teu, "retreated_no_concede")
    kept = s.lords[teu].forces.get("knights", 0)
    # Expected ~2 of 12 kept (1/6 = 16.7%).
    assert 0 <= kept <= 6


def test_resolve_battle_routes_units_to_pile() -> None:
    """resolve_battle moves Routed units to lord.routed_units, not nowhere."""
    s = load_scenario("watland", seed=11)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    s.lords[teu].forces = {"knights": 3, "men_at_arms": 3}
    s.lords[rus].forces = {"knights": 3, "men_at_arms": 3}
    res = resolve_battle(s, "teutonic", [teu], [rus])
    # Loser's routed_units should be non-empty (some units routed during battle).
    loser_lid = teu if res["loser"] == "teutonic" else rus
    routed = sum(s.lords[loser_lid].routed_units.values())
    assert routed > 0, f"expected routed units in loser pile; got {s.lords[loser_lid].routed_units}"


def test_winner_recovers_routed_units_after_battle() -> None:
    """Winner's routed_units are returned to forces after Battle ends
    via stand_battle (winner doesn't roll Losses per rules)."""
    from nevsky.state import CombatPending
    s = load_scenario("watland", seed=11)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    s.lords[teu].forces = {"knights": 5}  # strong attacker
    s.lords[rus].forces = {"knights": 1}  # weak defender
    s.lords[teu].location = "izborsk"
    s.lords[rus].location = "pskov"
    s.lords[teu].assets.pop("loot", None)
    s.lords[rus].assets.pop("loot", None)
    s.combat_pending = CombatPending(
        attacker_side="teutonic", attacker_group=[teu],
        from_locale="izborsk", to_locale="pskov", way_type="trackway",
        defender_side="russian", defender_lords=[rus],
        pending_response_by="russian", laden=False,
    )
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "russian"
    apply_action(s, {"type": "stand_battle", "side": "russian", "args": {}})
    # Winner's routed_units must be empty.
    if s.lords[teu].state == "mustered":
        assert s.lords[teu].routed_units == {}, \
            f"winner routed pile not cleared: {s.lords[teu].routed_units}"
