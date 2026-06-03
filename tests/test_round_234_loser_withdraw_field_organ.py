"""Rules-accuracy fixes from the full audit (batch 5).

- 4.4.3: a losing DEFENDER may Withdraw into that side's Stronghold at
  the Battle Locale (if it has one) instead of Retreating, keeping all
  Assets and becoming Besieged. The owning player selects via
  args.withdraw_losers.
- T10 Field Organ is playable in Battle OR Storm; Round 1 the named
  Lord's Knights AND Sergeants Melee Strike +1 (it was Storm-silent).
"""
from __future__ import annotations

import pytest

import nevsky.actions  # noqa: F401
from nevsky.actions import IllegalAction, apply_action
from nevsky.battle import BattleDecisionContext, resolve_storm
from nevsky.scenarios import load_scenario
from nevsky.state import CombatPending


def _battle_at_pskov(def_forces, atk_forces):
    s = load_scenario("peipus", seed=1)
    s.meta.phase = "campaign"; s.meta.campaign_step = "done"
    s.meta.active_player = "teutonic"
    s.locales["pskov"].teutonic_conquered = 0
    s.locales["pskov"].russian_conquered = 0
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic")
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian")
    for lid, f in ((rus, def_forces), (teu, atk_forces)):
        s.lords[lid].state = "mustered"; s.lords[lid].location = "pskov"
        s.lords[lid].in_stronghold = False; s.lords[lid].forces = dict(f)
    s.lords[rus].assets = {"loot": 2, "coin": 1}
    s.combat_pending = CombatPending(
        attacker_side="teutonic", attacker_group=[teu],
        from_locale="dorpat", to_locale="pskov", way_type="trackway",
        defender_side="russian", defender_lords=[rus],
        pending_response_by="russian", laden=False)
    return s, teu, rus


def test_losing_defender_withdraws_into_stronghold():
    s, teu, rus = _battle_at_pskov({"knights": 4, "men_at_arms": 4}, {"knights": 4})
    before = dict(s.lords[rus].assets)
    res = apply_action(s, {"type": "stand_battle", "side": "russian",
                           "args": {"concede": "defender", "withdraw_losers": True}})
    assert res["battle"].get("conceded") == "defender"
    assert rus in (res.get("withdrew") or [])
    assert s.lords[rus].in_stronghold is True
    assert s.lords[rus].location == "pskov"
    assert dict(s.lords[rus].assets) == before          # Withdrew -> keep all Assets
    assert s.locales["pskov"].siege_markers >= 1         # now Besieged


def test_withdraw_losers_requires_a_friendly_stronghold():
    # Make Pskov enemy-Conquered -> not Friendly -> a named withdraw is rejected.
    s, teu, rus = _battle_at_pskov({"knights": 4, "men_at_arms": 4}, {"knights": 4})
    s.locales["pskov"].teutonic_conquered = 1
    with pytest.raises(IllegalAction) as e:
        apply_action(s, {"type": "stand_battle", "side": "russian",
                         "args": {"concede": "defender", "withdraw_losers": [rus]}})
    assert e.value.code == "no_withdraw_stronghold"


def _storm_melee_r1(field_organ):
    s = load_scenario("pleskau", seed=3)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].forces = {"knights": 1, "sergeants": 1}  # base melee = 2
    holds = {"field_organ_lord": teu} if field_organ else None
    res = resolve_storm(
        s, attacker_side="teutonic", attacker_lords=[teu], defender_lords=[],
        locale_id="pskov", walls_max=0, siege_markers=1,
        garrison={"men_at_arms": 1}, decision_ctx=BattleDecisionContext(), holds=holds)
    return next(st["hits_after_walls"] for st in res["log"][0]["steps"]
               if st["step"] == "melee_attacker")


def test_field_organ_adds_one_per_knight_and_sergeant_in_storm_round1():
    assert _storm_melee_r1(field_organ=False) == 2          # 1 Knight + 1 Sergeant
    assert _storm_melee_r1(field_organ=True) == 4           # +1 each in Round 1


def test_field_organ_storm_command_consumes_hold():
    s = load_scenario("pleskau", seed=3)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].location = "pskov"; s.lords[teu].in_stronghold = False
    s.lords[teu].forces = {"knights": 2, "sergeants": 2}
    s.locales["pskov"].siege_markers = 2
    s.decks.teutonic.holds.append("T10")
    s.meta.phase = "campaign"; s.meta.campaign_step = "command"
    s.meta.active_player = "teutonic"; s.campaign_turn.next_to_reveal = "teutonic"
    s.campaign_turn.active_card = teu; s.campaign_turn.active_lord = teu
    from nevsky.static_data import load_lords
    s.campaign_turn.actions_remaining = int(load_lords()[teu]["ratings"]["command"])
    s.campaign_turn.in_feed_pay_disband = False; s.lords[teu].moved_fought = False
    apply_action(s, {"type": "cmd_storm", "side": "teutonic",
                     "args": {"lord_id": teu, "field_organ_lord": teu}})
    assert "T10" not in s.decks.teutonic.holds
    assert "T10" in s.decks.teutonic.discard
