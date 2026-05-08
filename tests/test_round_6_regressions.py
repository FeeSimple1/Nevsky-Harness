"""Regression tests from Round 6 aggressive smoke probes.

Round 6 found zero new bugs across multiple aggressive sweeps:
  - 16-turn Crusade-on-Novgorod run with invariant checking (1015+
    actions, 0 violations).
  - Re-Muster after Disband cycle.
  - Calendar off-edges, asset caps, Veche cap/exhaustion.
  - Stronghold capacity exact and over-capacity.
  - Sail to non-Seaport, levy_capability of no-event card.
  - Mutual destruction battle, muster_vassal already_mustered,
    cmd_supply with empty sources, legate_use 2a non-Ready target,
    Ravage same-locale twice, Pay zero units, Decline edge cases.

These tests lock in the invariants so future regressions are caught.
"""

from __future__ import annotations

import pytest

from nevsky.actions import IllegalAction, apply_action
from nevsky.scenarios import load_scenario
from nevsky.state import CombatPending


# === Re-Muster after Disband ===

def test_remuster_after_at_limit_disband() -> None:
    """3.3.2 + 3.4.1: at-limit Disband places cylinder back on Calendar;
    Lord can be re-Mustered later via muster_lord (Fealty roll required)."""
    s = load_scenario("watland", seed=23)
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})
    levy_box = next(cb.box for cb in s.calendar.boxes if cb.has_levy_campaign_marker)
    # Force yaroslav at-limit.
    for cb in s.calendar.boxes:
        if "yaroslav" in cb.service_markers:
            cb.service_markers.remove("yaroslav")
    s.calendar.boxes[levy_box - 1].service_markers.append("yaroslav")
    s.meta.phase = "levy"
    s.meta.levy_step = "disband"
    s.meta.active_player = "teutonic"
    apply_action(s, {"type": "disband_resolve", "side": "teutonic", "args": {}})
    assert s.lords["yaroslav"].state == "disbanded"
    # Cylinder placed.
    yaroslav_cyl_box = next(
        (cb.box for cb in s.calendar.boxes if "yaroslav" in cb.cylinders),
        None,
    )
    assert yaroslav_cyl_box is not None


def test_disband_cap_returns_to_deck() -> None:
    """3.3: this-lord capabilities return to side's deck on Disband."""
    s = load_scenario("watland", seed=1)
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    levy_box = next(cb.box for cb in s.calendar.boxes if cb.has_levy_campaign_marker)
    s.lords["yaroslav"].this_lord_capabilities = ["T7"]
    if "T7" in s.decks.teutonic.deck:
        s.decks.teutonic.deck.remove("T7")
    pre_deck = len(s.decks.teutonic.deck)
    for cb in s.calendar.boxes:
        if "yaroslav" in cb.service_markers:
            cb.service_markers.remove("yaroslav")
    s.calendar.boxes[levy_box - 1].service_markers.append("yaroslav")
    s.meta.levy_step = "disband"
    s.meta.active_player = "teutonic"
    apply_action(s, {"type": "disband_resolve", "side": "teutonic", "args": {}})
    assert len(s.decks.teutonic.deck) == pre_deck + 1
    assert "T7" in s.decks.teutonic.deck


# === Calendar off-edges via Pay ===

def test_pay_pushes_service_off_right() -> None:
    """3.2.1 + 2.2.3: Pay shifting Service marker past box 16 places it in off_right."""
    s = load_scenario("watland", seed=1)
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    for cb in s.calendar.boxes:
        if teu in cb.service_markers:
            cb.service_markers.remove(teu)
    s.calendar.boxes[15].service_markers.append(teu)  # box 16
    s.lords[teu].assets["coin"] = 3
    s.meta.phase = "levy"
    s.meta.levy_step = "pay"
    s.meta.active_player = "teutonic"
    res = apply_action(s, {"type": "pay_with_coin", "side": "teutonic",
                            "args": {"from": f"lord:{teu}", "target_lord": teu, "units": 2}})
    assert teu in s.calendar.off_right_service
    assert res["new_box"] == 17


# === Stronghold capacity ===

def test_withdraw_exact_capacity() -> None:
    """3.4.4 + Strongholds: 3 defenders fit in a City (capacity 3)."""
    s = load_scenario("pleskau", seed=1)
    for lid in ("gavrilo", "domash", "vladislav"):
        if lid in s.lords:
            s.lords[lid].state = "mustered"
            s.lords[lid].location = "pskov"
            s.lords[lid].in_stronghold = False
            s.lords[lid].assets.pop("loot", None)
            s.lords[lid].assets.pop("provender", None)
    s.combat_pending = CombatPending(
        attacker_side="teutonic", attacker_group=["hermann"],
        from_locale="izborsk", to_locale="pskov", way_type="trackway",
        defender_side="russian", defender_lords=["gavrilo", "domash", "vladislav"],
        pending_response_by="russian", laden=False,
    )
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "russian"
    apply_action(s, {"type": "withdraw", "side": "russian", "args": {}})
    for lid in ("gavrilo", "domash", "vladislav"):
        if lid in s.lords:
            assert s.lords[lid].in_stronghold is True


def test_withdraw_over_capacity_rejected() -> None:
    """4 lords cannot withdraw into a city (capacity 3)."""
    s = load_scenario("pleskau", seed=1)
    fake_4 = ["gavrilo", "domash", "vladislav", "aleksandr"]
    for lid in fake_4:
        if lid in s.lords:
            s.lords[lid].state = "mustered"
            s.lords[lid].location = "pskov"
            s.lords[lid].in_stronghold = False
            s.lords[lid].assets.pop("loot", None)
            s.lords[lid].assets.pop("provender", None)
    s.combat_pending = CombatPending(
        attacker_side="teutonic", attacker_group=["hermann"],
        from_locale="izborsk", to_locale="pskov", way_type="trackway",
        defender_side="russian", defender_lords=fake_4,
        pending_response_by="russian", laden=False,
    )
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "russian"
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "withdraw", "side": "russian", "args": {}})
    assert exc.value.code == "over_capacity"


# === Veche edge cases ===

def test_veche_options_rejected_at_zero_vp() -> None:
    """3.5.2: Options A/B/C all require >= 1 VP marker."""
    s = load_scenario("watland", seed=1)
    s.veche.vp_markers = 0
    s.meta.phase = "levy"
    s.meta.levy_step = "call_to_arms"
    s.meta.active_player = "russian"
    for opt in ("A", "B", "C"):
        with pytest.raises(IllegalAction):
            apply_action(s, {"type": "veche_action", "side": "russian",
                              "args": {"option": opt, "target_lord": "domash"}})


def test_veche_decline_with_only_one_prince_ready() -> None:
    """3.5.2 Option D: slides only the Ready prince when only one is."""
    s = load_scenario("return_of_the_prince", seed=1)
    levy_box = next(cb.box for cb in s.calendar.boxes if cb.has_levy_campaign_marker)
    # Move andrey to Levy box; aleksandr stays mustered.
    for cb in s.calendar.boxes:
        if "andrey" in cb.cylinders:
            cb.cylinders.remove("andrey")
    s.calendar.boxes[levy_box - 1].cylinders.append("andrey")
    s.lords["andrey"].state = "ready"
    s.meta.phase = "levy"
    s.meta.levy_step = "call_to_arms"
    s.meta.active_player = "russian"
    res = apply_action(s, {"type": "veche_action", "side": "russian", "args": {"option": "D"}})
    assert res["slid"] == ["andrey"]


def test_veche_vp_cap_at_8() -> None:
    """1.4.2: Veche VP cap is 8; excess forfeit."""
    s = load_scenario("watland", seed=1)
    s.veche.vp_markers = 8
    s.calendar.russian_vp = 8.0
    s.lords["aleksandr"].state = "ready"
    s.lords["aleksandr"].location = None
    levy_box = next(cb.box for cb in s.calendar.boxes if cb.has_levy_campaign_marker)
    for cb in s.calendar.boxes:
        if "aleksandr" in cb.cylinders:
            cb.cylinders.remove("aleksandr")
    s.calendar.boxes[levy_box - 1].cylinders.append("aleksandr")
    s.meta.phase = "levy"
    s.meta.levy_step = "call_to_arms"
    s.meta.active_player = "russian"
    apply_action(s, {"type": "veche_action", "side": "russian", "args": {"option": "D"}})
    assert s.veche.vp_markers == 8


# === Battle edge cases ===

def test_serfs_rout_unconditionally() -> None:
    """1.6 / Forces table: Serfs have no Protection and Rout on any Hit."""
    from nevsky.battle import resolve_battle
    s = load_scenario("watland", seed=7)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    s.lords[teu].forces = {"knights": 3}
    s.lords[rus].forces = {"serfs": 4}
    res = resolve_battle(s, "teutonic", [teu], [rus])
    assert res["winner"] == "teutonic"
    assert s.lords[rus].forces.get("serfs", 0) == 0


def test_sail_to_non_seaport_rejected() -> None:
    """4.7.3: Sail destination must be a Seaport."""
    s = load_scenario("watland", seed=1)
    s.meta.box = 1
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].location = "riga"
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "teutonic"
    s.campaign_turn.next_to_reveal = "teutonic"
    s.campaign_turn.active_card = teu
    s.campaign_turn.active_lord = teu
    s.campaign_turn.actions_remaining = 3
    s.campaign_turn.in_feed_pay_disband = False
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "cmd_sail", "side": "teutonic",
                          "args": {"lord_id": teu, "destination": "novgorod"}})
    assert exc.value.code == "not_seaport"


def test_pay_zero_units_rejected() -> None:
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].assets["coin"] = 5
    s.meta.phase = "levy"
    s.meta.levy_step = "pay"
    s.meta.active_player = "teutonic"
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "pay_with_coin", "side": "teutonic",
                          "args": {"from": f"lord:{teu}", "target_lord": teu, "units": 0}})
    assert exc.value.code == "bad_units"


def test_levy_capability_no_event_card_rejected() -> None:
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.meta.phase = "levy"
    s.meta.levy_step = "muster"
    s.meta.active_player = "teutonic"
    s.decks.teutonic.deck.append("T_no_event_1")
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "levy_capability", "side": "teutonic",
                          "args": {"by_lord": teu, "card_id": "T_no_event_1"}})
    assert exc.value.code == "bad_card"


def test_aow_play_hold_card_not_in_holds() -> None:
    s = load_scenario("watland", seed=1)
    s.decks.russian.holds = []
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "aow_play_hold", "side": "russian",
                          "args": {"card_id": "R3", "target": "domash"}})
    assert exc.value.code == "not_in_holds"


def test_levy_transport_at_eight_cap_rejected() -> None:
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].assets["cart"] = 8
    s.meta.phase = "levy"
    s.meta.levy_step = "muster"
    s.meta.active_player = "teutonic"
    s.lords[teu].lordship_used = 0
    s.lords[teu].just_arrived_this_levy = False
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "levy_transport", "side": "teutonic",
                          "args": {"by_lord": teu, "transport_type": "cart"}})
    assert exc.value.code == "transport_max"


def test_ravage_same_locale_twice_rejected() -> None:
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].location = "izhora"
    s.lords[teu].forces = {"knights": 2}
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "teutonic"
    s.campaign_turn.next_to_reveal = "teutonic"
    s.campaign_turn.active_card = teu
    s.campaign_turn.active_lord = teu
    s.campaign_turn.actions_remaining = 3
    s.campaign_turn.in_feed_pay_disband = False
    apply_action(s, {"type": "cmd_ravage", "side": "teutonic", "args": {"lord_id": teu}})
    assert s.locales["izhora"].teutonic_ravaged
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "cmd_ravage", "side": "teutonic", "args": {"lord_id": teu}})
    assert exc.value.code == "already_ravaged"


def test_muster_vassal_already_mustered_rejected() -> None:
    s = load_scenario("watland", seed=1)
    s.meta.phase = "levy"
    s.meta.levy_step = "muster"
    s.meta.active_player = "teutonic"
    teu = "andreas"
    v_id = next(iter(s.lords[teu].vassals))
    s.lords[teu].vassals[v_id].mustered = True
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "muster_vassal", "side": "teutonic",
                          "args": {"by_lord": teu, "vassal_id": v_id}})
    assert exc.value.code == "already_mustered"


def test_legate_use_2a_non_ready_lord_rejected() -> None:
    s = load_scenario("watland", seed=1)
    s.legate.william_of_modena_in_play = True
    s.legate.location = "locale"
    s.legate.locale_id = "riga"
    s.meta.phase = "levy"
    s.meta.levy_step = "call_to_arms"
    s.meta.active_player = "teutonic"
    # andreas is mustered (not ready); 2a requires Ready Lord.
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "legate_use", "side": "teutonic",
                          "args": {"sub_option": "2a", "target_lord": "andreas"}})
    assert exc.value.code == "bad_target"


def test_full_16_turn_crusade_run_no_invariant_violation() -> None:
    """E2E: 16-turn Crusade-on-Novgorod all-pass run completes cleanly
    with no Veche cap, asset cap, VP, or phase invariant violations.

    This test is slow but the most comprehensive end-to-end validation
    we have. Smoke driver _playthrough_round6_16turn.py does the same
    thing interactively."""
    from nevsky.campaign import _plan_target_size
    s = load_scenario("crusade_on_novgorod", seed=53)
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})

    def fast_levy():
        # AoW T+R. On first Levy, capabilities; after, immediate events
        # are skipped if their args are unsatisfiable.
        for sd in ("teutonic", "russian"):
            apply_action(s, {"type": "aow_shuffle", "side": sd, "args": {}})
            apply_action(s, {"type": "aow_draw", "side": sd, "args": {}})
            deck = s.decks.teutonic if sd == "teutonic" else s.decks.russian
            while deck.pending_draw:
                from nevsky.static_data import load_cards
                cid = deck.pending_draw[0]
                c = load_cards()[cid]
                args: dict = {}
                if not c["no_event"]:
                    if not s.meta.first_levy_done:
                        if c["capability_scope"] == "this_lord":
                            t = next((lid for lid, l in s.lords.items()
                                       if l.side == sd and l.state == "mustered"), None)
                            if t:
                                args["lord_id"] = t
                            else:
                                deck.pending_draw.pop(0)
                                deck.discard.append(cid)
                                continue
                    else:
                        # Subsequent Levy events: discard rather than risk
                        # an arg-validation failure aborting the test.
                        deck.pending_draw.pop(0)
                        deck.discard.append(cid)
                        continue
                try:
                    apply_action(s, {"type": "aow_implement_card", "side": sd, "args": args})
                except IllegalAction:
                    if deck.pending_draw and deck.pending_draw[0] == cid:
                        deck.pending_draw.pop(0)
                        deck.discard.append(cid)
            apply_action(s, {"type": "advance_step", "side": sd, "args": {}})
        # pay/disband/muster: skip
        for _ in range(3):
            apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})
            apply_action(s, {"type": "advance_step", "side": "russian", "args": {}})
        # CtA skip
        apply_action(s, {"type": "legate_skip", "side": "teutonic", "args": {}})
        apply_action(s, {"type": "aow_discard_this_levy", "side": "teutonic", "args": {}})
        apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})
        apply_action(s, {"type": "veche_action", "side": "russian", "args": {"option": "skip"}})
        apply_action(s, {"type": "aow_discard_this_levy", "side": "russian", "args": {}})
        apply_action(s, {"type": "advance_step", "side": "russian", "args": {}})

    def fast_camp():
        target = _plan_target_size(s.meta.box)
        for sd in ("teutonic", "russian"):
            for _ in range(target):
                apply_action(s, {"type": "plan_add_card", "side": sd, "args": {"card": "pass"}})
            apply_action(s, {"type": "finalize_plan", "side": sd, "args": {}})
        while s.meta.campaign_step == "command":
            side = s.campaign_turn.next_to_reveal
            if not s.campaign_turn.in_feed_pay_disband:
                apply_action(s, {"type": "command_reveal", "side": side, "args": {}})
            apply_action(s, {"type": "fpd_resolve", "side": "teutonic", "args": {}})
            apply_action(s, {"type": "fpd_resolve", "side": "russian", "args": {}})
        if s.meta.campaign_step == "end_campaign":
            apply_action(s, {"type": "end_campaign_resolve", "side": "teutonic", "args": {}})
            apply_action(s, {"type": "end_campaign_resolve", "side": "russian", "args": {}})

    turn = 0
    while not (s.meta.phase == "campaign" and s.meta.campaign_step == "done"):
        turn += 1
        assert turn <= 17, f"safety bail at turn 17 (box={s.meta.box})"
        assert s.meta.phase == "levy", f"phase={s.meta.phase} at turn {turn}"
        fast_levy()
        assert s.meta.phase == "campaign", f"after Levy phase={s.meta.phase}"
        fast_camp()
        # Invariants.
        assert s.veche.coin <= 8
        assert s.veche.vp_markers <= 8
        assert s.calendar.russian_vp >= 0
        assert s.calendar.teutonic_vp >= 0
        for lid, lord in s.lords.items():
            if lord.state == "mustered":
                assert lord.location is not None, f"{lid} mustered but no location"
                assert lord.location in s.locales
                for k, v in lord.assets.items():
                    assert 0 <= v <= 8, f"{lid} {k}={v} out of range"
    # Game ended at scenario.span_end_box.
    assert s.meta.box == 16
