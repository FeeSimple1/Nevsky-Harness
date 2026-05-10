"""Round 35 — SMOKE-021: Storm/Siege Surrender victory must distinguish
conquest from liberation when placing Conquered markers and VP.

Pre-fix, Storm and Siege-Surrender unconditionally incremented the
attacker's `conquered` marker and VP — even when the attacker was
LIBERATING their own native territory from an enemy Conquered marker.
The result: the enemy marker stayed on the map, the enemy kept their
VP, AND the liberating side gained a fresh marker + VP. A net swing
of +2 VP relative to the rules-correct outcome.

Rules-correct behavior:
  Conquest: attacker takes an enemy-native locale -> attacker's marker
            increments; attacker's VP increments.
  Liberation: attacker reclaims their own native locale from an enemy
              marker -> enemy marker cleared, enemy VP decremented.
              Attacker gains NO marker (you can't conquer your own
              territory) and NO VP (the swing comes from the enemy
              losing theirs).
"""
from __future__ import annotations

from nevsky.actions import apply_action
from nevsky.scenarios import load_scenario


def _setup_campaign():
    s = load_scenario("crusade_on_novgorod", seed=1)
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.box = 1
    return s


def test_storm_liberation_clears_enemy_marker_and_subtracts_enemy_vp():
    """R Storms a Teu-conquered Russian Fort: teu_conq -> 0, T VP -1,
    russ_conq stays 0, R VP unchanged."""
    s = _setup_campaign()
    s.meta.active_player = "russian"
    fort = "kaibolovo"
    s.locales[fort].teutonic_conquered = 1
    s.calendar.teutonic_vp = 1.0
    pre_r_vp = s.calendar.russian_vp

    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    s.lords[rus].location = fort
    s.lords[rus].in_stronghold = False
    s.lords[rus].forces = {"knights": 4, "men_at_arms": 4}
    s.locales[fort].siege_markers = 1
    s.campaign_turn.active_lord = rus
    s.campaign_turn.actions_remaining = 3
    s.campaign_turn.in_feed_pay_disband = False

    res = apply_action(s, {"type": "cmd_storm", "side": "russian", "args": {"lord_id": rus}})
    assert res.get("battle", {}).get("winner") == "attacker", "R should win the storm"
    assert s.locales[fort].teutonic_conquered == 0, "T marker not cleared"
    assert s.locales[fort].russian_conquered == 0, "R should not gain marker on own territory"
    assert s.calendar.teutonic_vp == 0.0, f"T VP not decremented (got {s.calendar.teutonic_vp})"
    assert s.calendar.russian_vp == pre_r_vp, f"R VP should be unchanged (got {s.calendar.russian_vp})"
    assert res.get("conquest_change", {}).get("type") == "liberation"


def test_storm_conquest_adds_attacker_marker_and_vp():
    """T Storms a Russian Fort (not yet conquered): teu_conq -> vp,
    T VP += vp, russ_conq unchanged."""
    s = _setup_campaign()
    s.meta.active_player = "teutonic"
    fort = "kaibolovo"
    pre_t_vp = s.calendar.teutonic_vp
    pre_r_vp = s.calendar.russian_vp

    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].location = fort
    s.lords[teu].in_stronghold = False
    s.lords[teu].forces = {"knights": 4, "men_at_arms": 4}
    s.locales[fort].siege_markers = 1
    s.campaign_turn.active_lord = teu
    s.campaign_turn.actions_remaining = 3
    s.campaign_turn.in_feed_pay_disband = False

    res = apply_action(s, {"type": "cmd_storm", "side": "teutonic", "args": {"lord_id": teu}})
    assert res.get("battle", {}).get("winner") == "attacker"
    # Fort vp = 1 per Strongholds reference.
    assert s.locales[fort].teutonic_conquered == 1
    assert s.locales[fort].russian_conquered == 0
    assert s.calendar.teutonic_vp == pre_t_vp + 1.0
    assert s.calendar.russian_vp == pre_r_vp
    assert res.get("conquest_change", {}).get("type") == "conquest"


def test_siege_surrender_liberation_clears_enemy_marker():
    """R Sieges a Teu-conquered Russian Fort with no T defender inside:
    Surrender roll may succeed; if so, marker clears, T loses VP, R
    gains NO marker."""
    s = _setup_campaign()
    s.meta.active_player = "russian"
    fort = "kaibolovo"
    s.locales[fort].teutonic_conquered = 1
    s.calendar.teutonic_vp = 1.0
    pre_r_vp = s.calendar.russian_vp

    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    s.lords[rus].location = fort
    s.lords[rus].in_stronghold = False
    s.lords[rus].forces = {"knights": 4, "men_at_arms": 4}
    # 4 siege markers maxes out the Surrender roll (auto-success).
    s.locales[fort].siege_markers = 4
    s.campaign_turn.active_lord = rus
    s.campaign_turn.actions_remaining = 3
    s.campaign_turn.in_feed_pay_disband = False

    res = apply_action(s, {"type": "cmd_siege", "side": "russian", "args": {"lord_id": rus}})
    # Surrender at roll <= 4 is high-probability; if conquered, verify.
    surrender = res.get("surrender_result", {})
    if surrender.get("conquered"):
        assert s.locales[fort].teutonic_conquered == 0
        assert s.locales[fort].russian_conquered == 0
        assert s.calendar.teutonic_vp == 0.0
        assert s.calendar.russian_vp == pre_r_vp
        assert surrender.get("change", {}).get("type") == "liberation"
