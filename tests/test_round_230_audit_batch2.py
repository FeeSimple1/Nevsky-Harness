"""Rules-accuracy fixes from the full audit (batch 2).

- Storm: the attacker may Concede (4.5.2) -- ends the Storm as loser, no
  Pursuit, Siege continues.
- Trebuchets (T14): a Sallying side with an Unrouted Trebuchets Lord
  reduces the besiegers' Siegeworks-as-Walls by 1 in a Sally (4.5.3),
  matching its Storm behavior.
"""
from __future__ import annotations

from nevsky.actions import apply_action
from nevsky.battle import BattleDecisionContext, resolve_battle, resolve_storm
from nevsky.scenarios import load_scenario
from nevsky.static_data import load_lords


def test_storm_attacker_concede_resolve_level():
    s = load_scenario("pleskau", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].forces = {"knights": 8}
    res = resolve_storm(
        s, attacker_side="teutonic", attacker_lords=[teu], defender_lords=[],
        locale_id="pskov", walls_max=4, siege_markers=4,
        garrison={"men_at_arms": 3}, decision_ctx=BattleDecisionContext(),
        attacker_concede_round=1,
    )
    assert res.get("conceded") == "attacker"
    assert res["winner"] == "defender" and res["loser"] == "attacker"
    assert res["rounds"] == 1


def test_storm_attacker_concede_via_command_keeps_siege():
    s = load_scenario("pleskau", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].location = "pskov"
    s.lords[teu].in_stronghold = False
    s.lords[teu].forces = {"knights": 6}
    s.locales["pskov"].siege_markers = 3
    # Make pskov a Teuton-besieged Russian stronghold (it is Russian by default).
    s.meta.phase = "campaign"; s.meta.campaign_step = "command"
    s.meta.active_player = "teutonic"; s.campaign_turn.next_to_reveal = "teutonic"
    s.campaign_turn.active_card = teu; s.campaign_turn.active_lord = teu
    s.campaign_turn.actions_remaining = int(load_lords()[teu]["ratings"]["command"])
    s.campaign_turn.in_feed_pay_disband = False
    s.lords[teu].moved_fought = False
    res = apply_action(s, {"type": "cmd_storm", "side": "teutonic",
                           "args": {"lord_id": teu, "concede": "attacker"}})
    assert res["battle"].get("conceded") == "attacker"
    assert res["battle"]["winner"] == "defender"
    assert s.locales["pskov"].siege_markers == 3  # Siege continues (no Sack)


def _sally(treb: bool, sw: int):
    s = load_scenario("pleskau", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic")
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian")
    s.lords[teu].state = "mustered"; s.lords[teu].location = "pskov"
    s.lords[teu].forces = {"knights": 6, "sergeants": 4}
    s.lords[rus].state = "mustered"; s.lords[rus].location = "pskov"
    s.lords[rus].forces = {"men_at_arms": 3}
    if treb:
        s.lords[teu].this_lord_capabilities.append("T14")  # Trebuchets
    res = resolve_battle(
        s, attacker_side="teutonic", attacker_lords=[teu], defender_lords=[rus],
        max_rounds=3, siegeworks_for_sally=sw, simple_sally=True,
        decision_ctx=BattleDecisionContext(),
    )
    return sum(1 for rd in res["log"] for st in rd.get("steps", [])
               for d in st.get("distribution", []) if d.get("target") == "siegeworks_vs_sally")


def test_trebuchets_nullifies_one_siegework_in_sally():
    # siegeworks=1 reduced to 0 by Trebuchets -> NO Siegeworks-as-Walls
    # absorption can occur (deterministic).
    assert _sally(treb=True, sw=1) == 0
    # Control: without Trebuchets, siegeworks=6 absorbs every Sally Hit.
    assert _sally(treb=False, sw=6) > 0
