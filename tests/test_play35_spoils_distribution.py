"""PLAY-35 regression tests: Spoils distribute among ALL winner Lords.

4.4.3 SPOILS: "the winning player distributes these Assets among mats
of Lords at the Locale". 4.5.2 (Storm): "The Besiegers receive and
distribute as desired among their Lords' mats". 4.3.4 (Avoid discards):
the Approaching Lords "receive and divide among them".

Before PLAY-35 every Spoils path handed everything to a single
recipient (winner_lords[0] / attackers[0] / spoils_recipient) and any
amount over that one Lord's 1.7.3 cap of 8 vanished even while other
winner Lords had room. Now:
  - distribute_spoils() spreads Assets over the whole recipient list,
    spilling to the next Lord with room; lost_to_cap only when EVERY
    recipient is at cap;
  - args.spoils_recipient accepts a str (priority Lord, SMOKE-003
    semantics) or a list (full priority order);
  - args.spoils_allocation = {lord_id: {asset: count}} expresses an
    explicit split (validated fail-loud), remainder spill-fills.
"""
from __future__ import annotations

import pytest

import nevsky.actions  # noqa: F401
from nevsky.actions import IllegalAction, apply_action
from nevsky.battle import distribute_spoils, transfer_spoils
from nevsky.scenarios import load_scenario
from nevsky.state import CombatPending


# --------------------------- helper unit tests ---------------------------

def _two_teutons(s):
    lords = [lid for lid, l in s.lords.items()
             if l.side == "teutonic" and l.state == "mustered"]
    for lid in lords[:2]:
        s.lords[lid].location = "pskov"
    return lords[:2]


def test_distribute_spills_to_next_lord_with_room():
    s = load_scenario("watland", seed=1)
    a, b = _two_teutons(s)
    s.lords[a].assets = {"loot": 7}
    s.lords[b].assets = {}
    r = distribute_spoils(s, [a, b], {"loot": 5})
    assert s.lords[a].assets["loot"] == 8      # 7 + 1 (capped)
    assert s.lords[b].assets["loot"] == 4      # spill
    assert r["lost_to_cap"] == {}
    assert r["total_added"] == {"loot": 5}
    assert r["added"] == {a: {"loot": 1}, b: {"loot": 4}}


def test_distribute_loses_only_when_all_at_cap():
    s = load_scenario("watland", seed=1)
    a, b = _two_teutons(s)
    s.lords[a].assets = {"coin": 8}
    s.lords[b].assets = {"coin": 7}
    r = distribute_spoils(s, [a, b], {"coin": 3})
    assert s.lords[b].assets["coin"] == 8
    assert r["lost_to_cap"] == {"coin": 2}


def test_distribute_allocation_plan_and_remainder():
    s = load_scenario("watland", seed=1)
    a, b = _two_teutons(s)
    s.lords[a].assets = {}
    s.lords[b].assets = {}
    plan = {b: {"loot": 2}}
    r = distribute_spoils(s, [a, b], {"loot": 3, "coin": 1}, plan)
    assert s.lords[b].assets["loot"] == 2      # plan honored first
    assert s.lords[a].assets["loot"] == 1      # remainder to order head
    assert s.lords[a].assets["coin"] == 1
    assert r["added"][b] == {"loot": 2}


def test_transfer_spoils_spreads_over_winners():
    """The 4.4.3 path: loser assets no longer vanish at winner[0]'s cap
    while winner[1] has room."""
    s = load_scenario("watland", seed=1)
    a, b = _two_teutons(s)
    rus = next(lid for lid, l in s.lords.items()
               if l.side == "russian" and l.state == "mustered")
    s.lords[a].assets = {"loot": 8}
    s.lords[b].assets = {}
    s.lords[rus].assets = {"loot": 4}
    r = transfer_spoils(s, rus, [a, b], "all_except_ships")
    assert s.lords[b].assets["loot"] == 4
    assert r["lost_to_cap"] == {}
    assert r["distributed"] == {b: {"loot": 4}}


# --------------------------- action-level tests ---------------------------

def _pending_battle(s, winners, loser):
    for lid in winners:
        s.lords[lid].location = "pskov"
        s.lords[lid].forces = {"knights": 5, "men_at_arms": 3}
    s.lords[loser].location = "pskov"
    s.lords[loser].forces = {"militia": 1}
    s.combat_pending = CombatPending(
        attacker_side="teutonic", attacker_group=list(winners),
        from_locale="izborsk", to_locale="pskov", way_type="trackway",
        defender_side="russian", defender_lords=[loser],
        pending_response_by="russian", laden=False,
    )
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "russian"
    s.campaign_turn.active_lord = None
    s.campaign_turn.actions_remaining = 0
    s.campaign_turn.in_feed_pay_disband = False


def test_stand_battle_spoils_allocation_split():
    """Explicit split: 1 loot to hermann, 1 to yaroslav (the old code
    could only give both to one mat)."""
    s = load_scenario("watland", seed=11)
    _pending_battle(s, ["hermann", "yaroslav"], "gavrilo")
    s.lords["gavrilo"].assets = {"loot": 2}
    s.lords["hermann"].assets = {}
    s.lords["yaroslav"].assets = {}
    res = apply_action(s, {
        "type": "stand_battle", "side": "russian",
        "args": {"spoils_allocation": {"hermann": {"loot": 1},
                                        "yaroslav": {"loot": 1}}},
    })
    if res["winner"] == "teutonic" and s.lords["gavrilo"].state != "mustered":
        assert s.lords["hermann"].assets.get("loot", 0) == 1
        assert s.lords["yaroslav"].assets.get("loot", 0) == 1


def test_stand_battle_spoils_allocation_validated():
    s = load_scenario("watland", seed=11)
    _pending_battle(s, ["hermann", "yaroslav"], "gavrilo")
    for bad in (
        {"gavrilo": {"loot": 1}},          # loser, not a winner Lord
        {"hermann": {"loot": -1}},         # negative
        {"hermann": ["loot"]},             # wrong shape
        "hermann",                          # wrong shape
    ):
        s2 = load_scenario("watland", seed=11)
        _pending_battle(s2, ["hermann", "yaroslav"], "gavrilo")
        with pytest.raises(IllegalAction):
            apply_action(s2, {"type": "stand_battle", "side": "russian",
                              "args": {"spoils_allocation": bad}})


def test_stand_battle_spoils_recipient_list_order():
    """spoils_recipient as a LIST sets the fill priority order."""
    s = load_scenario("watland", seed=11)
    _pending_battle(s, ["hermann", "yaroslav"], "gavrilo")
    s.lords["gavrilo"].assets = {"coin": 3}
    s.lords["hermann"].assets = {}
    s.lords["yaroslav"].assets = {}
    res = apply_action(s, {
        "type": "stand_battle", "side": "russian",
        "args": {"spoils_recipient": ["yaroslav", "hermann"]},
    })
    if res["winner"] == "teutonic" and s.lords["gavrilo"].state != "mustered":
        assert s.lords["yaroslav"].assets.get("coin", 0) == 3
        assert s.lords["hermann"].assets.get("coin", 0) == 0


def test_avoid_discards_divide_among_attacker_group():
    """4.3.4: discarded Loot/Provender goes to the WHOLE Approaching
    group -- overflow at attacker[0] spills to attacker[1]."""
    s = load_scenario("crusade_on_novgorod", seed=42)
    for lid in ("heinrich", "hermann"):
        s.lords[lid].state = "mustered"
        s.lords[lid].location = "izborsk"
        s.lords[lid].forces = {"knights": 2}
    s.lords["heinrich"].assets = {"loot": 7}
    s.lords["hermann"].assets = {}
    gav = s.lords["gavrilo"]
    gav.state = "mustered"
    gav.location = "pskov"
    gav.forces = {"militia": 2}
    gav.assets = {"loot": 3}
    s.combat_pending = CombatPending(
        attacker_side="teutonic", attacker_group=["heinrich", "hermann"],
        from_locale="izborsk", to_locale="pskov", way_type="trackway",
        defender_side="russian", defender_lords=["gavrilo"],
        pending_response_by="russian", laden=False,
    )
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.campaign_turn.active_card = "heinrich"
    s.campaign_turn.active_lord = "heinrich"
    s.campaign_turn.actions_remaining = 2
    s.meta.active_player = "russian"
    r = apply_action(s, {"type": "avoid_battle", "side": "russian",
                         "args": {"to": "dubrovno"}})
    # 3 loot dropped: heinrich takes 1 (to cap), hermann takes 2.
    assert s.lords["heinrich"].assets.get("loot", 0) == 8
    assert s.lords["hermann"].assets.get("loot", 0) == 2
    assert r["spoils_lost_to_cap"] == {}
    assert r["spoils_distribution"] == {"heinrich": {"loot": 1},
                                        "hermann": {"loot": 2}}


def _storm_ready(seed=2):
    """pleskau seed-2 Storm that the attackers win (probed): hermann +
    yaroslav besiege gavrilo's militia inside pskov (Stronghold VP 2 ->
    spoils 2 loot / 2 provender / 2 coin)."""
    from nevsky.static_data import load_lords
    s = load_scenario("pleskau", seed=seed)
    teus = [lid for lid, l in s.lords.items()
            if l.side == "teutonic" and l.state == "mustered"]
    if len(teus) < 2:
        extra = next(lid for lid, l in s.lords.items()
                     if l.side == "teutonic" and lid not in teus)
        s.lords[extra].state = "mustered"
        teus.append(extra)
    a, b = teus[:2]
    rus = next(lid for lid, l in s.lords.items()
               if l.side == "russian" and l.state == "mustered")
    for lid in (a, b):
        s.lords[lid].location = "pskov"
        s.lords[lid].in_stronghold = False
        s.lords[lid].forces = {"knights": 6, "men_at_arms": 4}
        s.lords[lid].assets = {}
    s.lords[rus].location = "pskov"
    s.lords[rus].in_stronghold = True
    s.lords[rus].forces = {"militia": 1}
    s.lords[rus].assets = {}
    s.locales["pskov"].siege_markers = 2
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "teutonic"
    s.campaign_turn.active_card = a
    s.campaign_turn.active_lord = a
    s.campaign_turn.actions_remaining = int(
        load_lords()[a]["ratings"]["command"])
    s.campaign_turn.in_feed_pay_disband = False
    s.lords[a].moved_fought = False
    return s, a, b


def test_storm_stronghold_spoils_priority_list():
    """4.5.2: spoils_recipient list routes the whole award to the listed
    Lord first (old code: always attackers[0])."""
    s, a, b = _storm_ready()
    res = apply_action(s, {"type": "cmd_storm", "side": "teutonic",
                           "args": {"lord_id": a,
                                    "spoils_recipient": [b, a]}})
    assert res["battle"]["winner"] == "attacker"
    assert res["stronghold_spoils_distribution"] == {
        b: {"loot": 2, "provender": 2, "coin": 2}}
    assert s.lords[b].assets == {"loot": 2, "provender": 2, "coin": 2}
    assert res["spoils_recipient"] == b


def test_storm_stronghold_spoils_allocation_and_spill():
    """Explicit split of the Stronghold award; near-cap recipient spills
    to the other Besieger instead of vanishing."""
    s, a, b = _storm_ready()
    s.lords[a].assets = {"coin": 7}
    res = apply_action(s, {"type": "cmd_storm", "side": "teutonic",
                           "args": {"lord_id": a,
                                    "spoils_allocation": {
                                        a: {"coin": 2, "loot": 1},
                                        b: {"provender": 2}}}})
    assert res["battle"]["winner"] == "attacker"
    # a wanted 2 coin but had room for 1 (7 -> 8); the second coin
    # spill-fills to b rather than vanishing.
    assert s.lords[a].assets.get("coin") == 8
    assert s.lords[b].assets.get("coin") == 1
    # a's planned loot (1) plus the unallocated remainder loot (1),
    # which spill-fills in attacker order to a (he has room).
    assert s.lords[a].assets.get("loot") == 2
    assert s.lords[b].assets.get("loot", 0) == 0
    assert s.lords[b].assets.get("provender") == 2
    assert not any(e["from_lord"] == "stronghold"
                   for e in res.get("storm_spoils_lost_to_cap", []))
