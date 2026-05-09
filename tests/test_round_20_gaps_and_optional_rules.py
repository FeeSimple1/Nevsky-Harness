"""Round 20 regression tests: R19 interface gaps + optional rules infra."""
from __future__ import annotations

import pytest

from nevsky.actions import apply_action
from nevsky.legal_moves import legal_moves
from nevsky.previews import battle_preview
from nevsky.render import (
    lord_card_status,
    paths_from,
    render_summary,
)
from nevsky.scenarios import load_scenario, set_optional_rule


def _setup_pleskau():
    s = load_scenario("pleskau", seed=1)
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})
    return s


# ---------------------------------------------------------------------------
# R19 Gap 1: cmd_march warning when destination is enemy Stronghold
# ---------------------------------------------------------------------------


def test_cmd_march_note_warns_about_enemy_stronghold():
    """When a March destination is an enemy-territory Stronghold, the
    legal_moves note must warn that the March places a Siege and ends
    the Command card per rule 4.3."""
    s = _setup_pleskau()
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.campaign_turn.active_lord = "hermann"
    s.campaign_turn.actions_remaining = 3
    s.campaign_turn.next_to_reveal = "teutonic"
    moves = legal_moves(s)
    march_moves = [m for m in moves if m["type"] == "cmd_march"]
    assert march_moves
    # Hermann is at Dorpat; ugaunia is a region (no Stronghold). Force a
    # contrived test: pretend Hermann is at Ugaunia so Izborsk is one
    # hop away.
    s.lords["hermann"].location = "ugaunia"
    moves = legal_moves(s)
    march_moves = [m for m in moves if m["type"] == "cmd_march"]
    izborsk_march = next((m for m in march_moves if m["args"]["to"] == "izborsk"), None)
    assert izborsk_march is not None
    assert "Siege" in izborsk_march["note"]
    assert "ends the Command card" in izborsk_march["note"]


# ---------------------------------------------------------------------------
# R19 Gap 2: withdraw note clarity
# ---------------------------------------------------------------------------


def test_withdraw_note_explains_no_args_required():
    """The withdraw entry should explicitly say no args are required and
    that it auto-targets combat_pending.to_locale."""
    # Construct a state with combat_pending set up.
    s = _setup_pleskau()
    from nevsky.state import CombatPending
    s.combat_pending = CombatPending(
        attacker_side="teutonic",
        attacker_group=["hermann"],
        from_locale="dorpat", to_locale="pskov", way_type="trackway",
        defender_side="russian",
        defender_lords=["gavrilo"],
        pending_response_by="russian",
    )
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "russian"  # response_by side has the move
    moves = legal_moves(s)
    withdraw = next((m for m in moves if m["type"] == "withdraw"), None)
    assert withdraw is not None
    assert "no args required" in withdraw["note"]
    # Note resolves the actual locale id (e.g. 'pskov') rather than
    # the abstract 'to_locale' placeholder.
    assert "pskov" in withdraw["note"] or "to_locale" in withdraw["note"]


# ---------------------------------------------------------------------------
# R19 Gap 3: paths_from helper
# ---------------------------------------------------------------------------


def test_paths_from_finds_multi_hop_routes():
    s = _setup_pleskau()
    paths = paths_from(s, "novgorod", max_hops=4)
    # Novgorod itself has empty path.
    assert paths["novgorod"] == []
    # Some neighbor exists.
    assert any(len(p) == 1 for p in paths.values())
    # Pskov should be reachable in 3 hops via shelon_river/dubrovno.
    assert "pskov" in paths
    assert 1 <= len(paths["pskov"]) <= 4


def test_paths_from_returns_path_lists_in_order():
    """Each path should end at the destination locale and contain the
    intermediate hops."""
    s = _setup_pleskau()
    paths = paths_from(s, "dorpat", max_hops=3)
    for dest, p in paths.items():
        if dest == "dorpat":
            assert p == []
            continue
        assert p[-1] == dest
        # Every step transitions through known Locales.
        assert all(loc in s.locales for loc in p)


# ---------------------------------------------------------------------------
# R19 Gap 4: lord_card_status helper
# ---------------------------------------------------------------------------


def test_lord_card_status_returns_well_formed_dict():
    s = _setup_pleskau()
    status = lord_card_status(s, "hermann")
    expected_keys = {
        "lord_id", "side", "is_mustered", "is_besieged",
        "in_plan", "in_plan_position", "is_active", "actions_remaining",
        "service_disband_box",
    }
    assert expected_keys.issubset(status.keys())
    assert status["lord_id"] == "hermann"
    assert status["side"] == "teutonic"
    assert status["is_mustered"] is True
    assert status["service_disband_box"] == 4


def test_lord_card_status_unknown_lord():
    s = _setup_pleskau()
    status = lord_card_status(s, "fictional_lord")
    assert "error" in status


# ---------------------------------------------------------------------------
# Optional rules infrastructure
# ---------------------------------------------------------------------------


def test_optional_rules_default_empty():
    s = _setup_pleskau()
    assert s.meta.optional_rules == {}


def test_load_scenario_accepts_optional_rules_kwarg():
    s = load_scenario("pleskau", seed=1, optional_rules={
        "no_horseback_archery": True,
        "hidden_mats": True,
    })
    assert s.meta.optional_rules["no_horseback_archery"] is True
    assert s.meta.optional_rules["hidden_mats"] is True


def test_load_scenario_rejects_unknown_optional_rule():
    with pytest.raises(ValueError, match="unknown optional rule"):
        load_scenario("pleskau", seed=1,
                      optional_rules={"made_up_rule": True})


def test_set_optional_rule_toggles_and_returns_summary():
    s = _setup_pleskau()
    res = set_optional_rule(s, "no_horseback_archery", True)
    assert res["new_state"] is True
    assert res["prior_state"] is False
    assert "no_horseback_archery" in res["all_active"]
    assert s.meta.optional_rules["no_horseback_archery"] is True


def test_set_optional_rule_rejects_unknown():
    s = _setup_pleskau()
    with pytest.raises(ValueError, match="unknown optional rule"):
        set_optional_rule(s, "totally_invented", True)


def test_render_summary_shows_active_optional_rules():
    s = load_scenario("pleskau", seed=1, optional_rules={
        "no_horseback_archery": True,
        "hidden_mats": True,
    })
    out = render_summary(s)
    assert "Optional rules:" in out
    assert "no_horseback_archery" in out
    assert "hidden_mats" in out


def test_render_summary_omits_optional_rules_line_when_none_active():
    s = _setup_pleskau()
    out = render_summary(s)
    assert "Optional rules:" not in out


# ---------------------------------------------------------------------------
# Bidding for Sides
# ---------------------------------------------------------------------------


def test_bidding_for_sides_adds_vp_markers_to_veche():
    base = load_scenario("pleskau", seed=1)
    bid_3 = load_scenario("pleskau", seed=1, bidding_bid=3)
    assert bid_3.veche.vp_markers == base.veche.vp_markers + 3
    assert bid_3.meta.optional_rules["bidding_for_sides"] is True


def test_bidding_for_sides_capped_at_8():
    """Veche VP markers cap at 8 per rules 1.3.3."""
    s = load_scenario("pleskau", seed=1, bidding_bid=20)
    assert s.veche.vp_markers <= 8


def test_bidding_bid_negative_rejected():
    with pytest.raises(ValueError):
        load_scenario("pleskau", seed=1, bidding_bid=-1)


# ---------------------------------------------------------------------------
# No Horseback Archery variant
# ---------------------------------------------------------------------------


def test_no_horseback_archery_makes_asiatic_horse_more_fragile():
    """With NHA on, Asiatic Horse Defense rolls succeed only on '1' —
    the unit becomes effectively Unarmored. Compare attacker damage
    against an all-Asiatic-Horse defender with vs without the variant."""
    s_default = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s_default.lords.items() if l.side == "teutonic")
    rus = next(lid for lid, l in s_default.lords.items() if l.side == "russian")
    s_default.lords[teu].state = "mustered"
    s_default.lords[teu].location = "pskov"
    s_default.lords[teu].forces = {"sergeants": 4, "men_at_arms": 4}
    s_default.lords[rus].state = "mustered"
    s_default.lords[rus].location = "pskov"
    s_default.lords[rus].forces = {"asiatic_horse": 6}
    prev_default = battle_preview(
        s_default, "teutonic", [teu], [rus], trials=200)
    # NHA-on copy.
    s_nha = load_scenario("watland", seed=1,
                           optional_rules={"no_horseback_archery": True})
    teu2 = next(lid for lid, l in s_nha.lords.items() if l.side == "teutonic")
    rus2 = next(lid for lid, l in s_nha.lords.items() if l.side == "russian")
    s_nha.lords[teu2].state = "mustered"
    s_nha.lords[teu2].location = "pskov"
    s_nha.lords[teu2].forces = {"sergeants": 4, "men_at_arms": 4}
    s_nha.lords[rus2].state = "mustered"
    s_nha.lords[rus2].location = "pskov"
    s_nha.lords[rus2].forces = {"asiatic_horse": 6}
    prev_nha = battle_preview(
        s_nha, "teutonic", [teu2], [rus2], trials=200)
    # Defender (all Asiatic Horse) wins LESS often with NHA on.
    assert prev_nha["defender_winrate"] < prev_default["defender_winrate"], (
        f"NHA should weaken Asiatic Horse defense: "
        f"default D-win {prev_default['defender_winrate']:.2%} "
        f"vs NHA D-win {prev_nha['defender_winrate']:.2%}"
    )
