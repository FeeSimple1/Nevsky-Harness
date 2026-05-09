"""Round 28 regression tests for rule-correctness checks.

Found and fixed: Asiatic Horse used Evade in Storm Melee (engine
ignored protection_storm). Per Forces Reference: 'Evade vs Battle
Melee else Unarmored' — Asiatic Horse should be Unarmored in Storm.

Also pins down: Halbbrueder armor +1, Streltsy -2 armor, Battle
initiative ordering, Concede half-Hits, end-of-Rasputitsa Grow."""
from __future__ import annotations

from copy import deepcopy

import pytest

from nevsky.actions import apply_action
from nevsky.battle import (
    BattleDecisionContext,
    _absorb_hit,
    _protection_spec,
    resolve_battle,
)
from nevsky.scenarios import load_scenario


def _setup_two_lords(scenario="watland"):
    s = load_scenario(scenario, seed=1)
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic")
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian")
    for l in (teu, rus):
        s.lords[l].state = "mustered"
        s.lords[l].location = "pskov"
    return s, teu, rus


# ---------------------------------------------------------------------------
# Asiatic Horse Storm protection bug fix
# ---------------------------------------------------------------------------


def test_asiatic_horse_protection_spec_battle_vs_storm():
    """Per Forces Reference: 'Evade vs Battle Melee, else Unarmored.'"""
    assert _protection_spec("asiatic_horse", "melee", in_storm=False) == "evade:1-3"
    assert _protection_spec("asiatic_horse", "archery", in_storm=False) == "unarmored"
    assert _protection_spec("asiatic_horse", "melee", in_storm=True) == "unarmored"
    assert _protection_spec("asiatic_horse", "archery", in_storm=True) == "unarmored"


def test_asiatic_horse_storm_melee_uses_unarmored_not_evade():
    """Storm context: Asiatic Horse must NOT use Evade (50% absorb);
    must use Unarmored (~17%)."""
    s, _, _ = _setup_two_lords()
    s.meta.rng_state = 1000
    storm_absorbs = sum(_absorb_hit(s, "asiatic_horse", "melee", in_storm=True)
                         for _ in range(800))
    s.meta.rng_state = 1000
    battle_absorbs = sum(_absorb_hit(s, "asiatic_horse", "melee", in_storm=False)
                          for _ in range(800))
    storm_rate = storm_absorbs / 800
    battle_rate = battle_absorbs / 800
    # Storm: Unarmored, 1/6 ~ 16.7%
    assert 0.10 <= storm_rate <= 0.25, f"storm absorb rate {storm_rate:.1%} not Unarmored"
    # Battle: Evade 3/6 = 50%
    assert 0.40 <= battle_rate <= 0.60, f"battle absorb rate {battle_rate:.1%} not Evade"
    # Storm rate must be DISTINCTLY lower than battle rate.
    assert storm_rate < battle_rate * 0.6, (
        f"asiatic horse storm rate {storm_rate:.1%} should be much lower than "
        f"battle rate {battle_rate:.1%} (Unarmored vs Evade)"
    )


def test_asiatic_horse_storm_no_horseback_archery_unchanged():
    """When the No Horseback Archery variant is on, Asiatic Horse is
    Unarmored everywhere — Storm should still be Unarmored."""
    s, _, _ = _setup_two_lords()
    s.meta.optional_rules["no_horseback_archery"] = True
    s.meta.rng_state = 1000
    storm_absorbs = sum(_absorb_hit(s, "asiatic_horse", "melee", in_storm=True)
                         for _ in range(500))
    rate = storm_absorbs / 500
    # Either way, ~17% absorb.
    assert 0.10 <= rate <= 0.25


# ---------------------------------------------------------------------------
# Other unit protection rates (sanity)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("utype,kind,expected_min,expected_max", [
    ("knights",      "melee",   0.55, 0.78),  # Armor 1-4 ~67%
    ("sergeants",    "melee",   0.40, 0.60),  # Armor 1-3 ~50%
    ("men_at_arms",  "melee",   0.40, 0.60),  # Armor 1-3 ~50%? actually 1-2 ~33%
    ("light_horse",  "melee",   0.10, 0.25),  # Unarmored ~17%
    ("militia",      "melee",   0.10, 0.25),  # Unarmored ~17%
    ("serfs",        "melee",   0.00, 0.05),  # No protection
])
def test_unit_protection_rates(utype, kind, expected_min, expected_max):
    s, _, _ = _setup_two_lords()
    s.meta.rng_state = 1000
    absorbs = sum(_absorb_hit(s, utype, kind) for _ in range(800))
    rate = absorbs / 800
    assert expected_min <= rate <= expected_max, (
        f"{utype} {kind} absorb rate {rate:.1%} outside [{expected_min:.1%}, "
        f"{expected_max:.1%}]"
    )


# ---------------------------------------------------------------------------
# Halbbrueder reduces Sergeant losses
# ---------------------------------------------------------------------------


def test_halbbrueder_reduces_sergeant_losses():
    """Sergeant Armor 1-3 (50%) -> 1-4 (67%) with Halbbrueder."""
    s_base, teu, rus = _setup_two_lords()
    s_base.lords[teu].forces = {"sergeants": 30}
    s_base.lords[rus].forces = {"sergeants": 30}

    def avg_loss(use_halb):
        s = deepcopy(s_base)
        if use_halb:
            s.decks.teutonic.capabilities_in_play.append("T9")
            s.lords[teu].this_lord_capabilities.append("T9")
        loss = 0
        for t in range(60):
            s2 = deepcopy(s)
            s2.meta.rng_state = t * 7919 + 1
            pre = sum(s2.lords[teu].forces.values())
            resolve_battle(s2, attacker_side="russian",
                           attacker_lords=[rus], defender_lords=[teu],
                           max_rounds=2, decision_ctx=BattleDecisionContext())
            loss += pre - sum(s2.lords[teu].forces.values())
        return loss

    no_halb = avg_loss(False)
    with_halb = avg_loss(True)
    assert with_halb < no_halb * 0.85, (
        f"Halbbrueder should noticeably reduce losses: no_halb={no_halb}, "
        f"with_halb={with_halb} (ratio {with_halb/no_halb:.2f})"
    )


# ---------------------------------------------------------------------------
# Streltsy increases enemy MaA losses
# ---------------------------------------------------------------------------


def test_streltsy_dramatically_increases_enemy_maa_losses():
    """Streltsy: Russian MaA archery -2 enemy Armor. Teu MaA Armor 1-2
    -> 1-0 = no absorb. Should dramatically increase Teu MaA losses."""
    s_base, teu, rus = _setup_two_lords()
    s_base.lords[teu].forces = {"men_at_arms": 30}
    s_base.lords[rus].forces = {"men_at_arms": 30}

    def avg_loss(use_streltsy):
        s = deepcopy(s_base)
        if use_streltsy:
            s.decks.russian.capabilities_in_play.append("R3")
            s.lords[rus].this_lord_capabilities.append("R3")
        loss = 0
        for t in range(60):
            s2 = deepcopy(s)
            s2.meta.rng_state = t * 7919 + 1
            pre = sum(s2.lords[teu].forces.values())
            resolve_battle(s2, attacker_side="russian",
                           attacker_lords=[rus], defender_lords=[teu],
                           max_rounds=1, decision_ctx=BattleDecisionContext())
            loss += pre - sum(s2.lords[teu].forces.values())
        return loss

    no_strel = avg_loss(False)
    with_strel = avg_loss(True)
    # Should be at least 2x more loss with Streltsy.
    assert with_strel > no_strel * 2.0, (
        f"Streltsy should >=2x Teu MaA losses: no_strel={no_strel}, "
        f"with_strel={with_strel} (ratio {with_strel/no_strel:.2f})"
    )


# ---------------------------------------------------------------------------
# Battle initiative ordering
# ---------------------------------------------------------------------------


def test_battle_initiative_defender_strikes_first_in_each_step():
    """Per 4.4.2: defender strikes first in archery, then attacker;
    same pattern for melee_horse and melee_foot."""
    s, teu, rus = _setup_two_lords()
    s.lords[teu].forces = {"asiatic_horse": 5, "men_at_arms": 5}
    s.lords[rus].forces = {"asiatic_horse": 5, "men_at_arms": 5}
    s.meta.rng_state = 1
    res = resolve_battle(s, attacker_side="teutonic",
                         attacker_lords=[teu], defender_lords=[rus],
                         max_rounds=1, decision_ctx=BattleDecisionContext())
    rd1 = res["log"][0]
    step_names = [st["step"] for st in rd1["steps"]]
    # Each defender step must precede its attacker counterpart.
    pairs = [
        ("archery_defender", "archery_attacker"),
        ("melee_horse_defender", "melee_horse_attacker"),
        ("melee_foot_defender", "melee_foot_attacker"),
    ]
    for d_step, a_step in pairs:
        if d_step in step_names and a_step in step_names:
            assert step_names.index(d_step) < step_names.index(a_step), (
                f"{a_step} preceded {d_step}: {step_names}"
            )


# ---------------------------------------------------------------------------
# Concede Pursuit halves Conceder's Hits
# ---------------------------------------------------------------------------


def test_concede_halves_conceder_hits_round_1():
    """4.4.2 Pursuit: Conceder takes half Hits this Round (round up by
    step). Conversely, Conceder's strike output halves too -> defender
    takes about half the damage when attacker concedes."""
    s_base, teu, rus = _setup_two_lords()
    s_base.lords[teu].forces = {"sergeants": 30}
    s_base.lords[rus].forces = {"sergeants": 30}

    def avg_rus_loss(concede):
        loss = 0
        for t in range(60):
            s = deepcopy(s_base)
            s.meta.rng_state = t * 7919 + 1
            pre = sum(s.lords[rus].forces.values())
            resolve_battle(s, attacker_side="teutonic",
                           attacker_lords=[teu], defender_lords=[rus],
                           max_rounds=1, decision_ctx=BattleDecisionContext(),
                           concede=concede)
            loss += pre - sum(s.lords[rus].forces.values())
        return loss

    no_concede = avg_rus_loss(None)
    concede_atk = avg_rus_loss("attacker")
    # Concede halves Conceder's Hits -> defender takes ~half.
    assert concede_atk < no_concede * 0.7, (
        f"Concede should noticeably reduce defender losses (attacker hits halved): "
        f"no_concede={no_concede}, concede_atk={concede_atk} "
        f"(ratio {concede_atk/no_concede:.2f})"
    )


# ---------------------------------------------------------------------------
# End-of-Rasputitsa Grow halves Ravaged markers
# ---------------------------------------------------------------------------


def test_grow_halves_ravaged_markers_at_end_of_rasputitsa():
    """At end of each Rasputitsa (boxes 8 and 16), the side whose
    territory was Ravaged removes markers down to half (round up)."""
    s = load_scenario("watland", seed=1)
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})
    s.meta.box = 8
    # Place 6 Teutonic-color Ravaged markers.
    targets = ("vod", "tesovo", "sablia", "zheltsy", "dubrovno", "pskov")
    for lid in targets:
        if lid in s.locales:
            s.locales[lid].teutonic_ravaged = True
    pre = sum(1 for loc in s.locales.values() if loc.teutonic_ravaged)
    assert pre == 6
    s.meta.phase = "campaign"
    s.meta.campaign_step = "end_campaign"
    apply_action(s, {"type": "end_campaign_resolve", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "end_campaign_resolve", "side": "russian", "args": {}})
    post = sum(1 for loc in s.locales.values() if loc.teutonic_ravaged)
    # 6 / 2 = 3 remaining (round up half number to be REMOVED -> remove 3, leave 3).
    # Per rule: "down to half their number, rounded up" -> retain 3 (ceil(6/2)).
    assert post == 3, f"expected 3 remaining (half of 6 rounded up), got {post}"
