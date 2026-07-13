"""Playbook golden test: the full Battle example (Background Book pp.
11-14, "Battle" -- Andreas & Heinrich vs Domash at Zheltsy).

Replays the designer's worked two-Round Battle with every printed die
roll scripted, and asserts the printed outcome at each step:

  Round 1 (Field Organ played on Andreas, Hill + Luchniki for Domash):
    - Defending Archery: SIX Hits (Luchniki 1/2-Hit Militia/Light Horse
      x6 units, un-halved by Hill Rounds 1-2). Heinrich absorbs
      (flank-absorb choice, PLAY-28): Knights absorb 2 then Rout;
      second unit absorbs 2 then Routs.
    - Defending Horse Melee: TWO Hits (Sergeants 1 + Light Horse 1/2,
      round up). Heinrich's last unit Routs -> HEINRICH ROUTS MID-STEP
      and the leftover Hit follows the new Flanking situation to
      Andreas (PLAY-27), who absorbs.
    - Attacking Horse Melee: SEVEN Hits -- Knights 2 + Sergeants 1+1,
      plus Field Organ +1 per Knights AND Sergeants unit (+3)
      (PLAY-41). Militia absorb one and Rout five; a Sergeants Routs.
    - Defending Foot: 2 Hits; Andreas's Knights absorb one, Rout on the
      second. Attacking Foot: 1 Hit absorbed.
  Round 2 (Russians CONCEDE -> Pursuit halves their Hits):
    - Archery and Horse: 1 Hit each, both absorbed.
    - Attacking Horse (2 Hits): Light Horse and a Men-at-Arms Rout.
    - Defending Foot Routs a Teutonic unit; Attacking Foot Routs
      Domash's last unit.
  Ending:
    - Domash Retreats to Sablia; Service roll '3' shifts his marker
      HALF THE ROLL ROUNDED UP = 2 boxes left, box 7 -> 5 (4.4.3).
    - Losses: Domash Conceded, so Routed units roll STANDARD
      Protection: keeps 2 Militia and both Men-at-Arms; Andreas
      recovers everything; Heinrich loses all three units and is
      PERMANENTLY REMOVED (4.4.4).
    - Spoils: Conceded+Retreated = all Loot + Provender beyond Unladen:
      4 Provender vs 3 Sleds -> 1 Provender to Andreas.
    - Feed: Andreas eats the Provender he just took; Domash (4 units
      left) eats 1 of his 3.

Where a static absorption policy assigns a same-outcome Hit to a
different (equal-fate) unit than the narration, the difference is noted
inline; every Hit COUNT, Rout, and end-state number is the printed one.
"""
from __future__ import annotations

import sys
from pathlib import Path

import nevsky.actions  # noqa: F401
from nevsky.actions import apply_action
from nevsky.scenarios import load_scenario
from nevsky.state import CombatPending, GameState

sys.path.insert(0, str(Path(__file__).parent))
from _playbook_rolls import script_rolls  # noqa: E402


PRINTED_ROLLS = (
    # -- Round 1 --
    [2, 3, 5,        # Archery on Heinrich: Knights absorb, absorb, Rout
     3, 1, 6,        # ...second unit absorbs twice, Routs on the '6'
     4,              # Def Horse: Heinrich's last unit Routs -> Lord Routs
     1,              # PLAY-27 spillover Hit to Andreas: absorbed
     2, 3, 4, 5, 1,  # Att Horse on Militia: four Rout, one stands on '1'
     4,              # ...the standing Militia Routs
     5,              # ...seventh Hit Routs a Sergeants
     4, 5,           # Def Foot on Andreas's Knights: absorb, Rout
     1]              # Att Foot: absorbed
    # -- Round 2 (Pursuit) --
    + [2,            # Archery 1 Hit: absorbed ("avoid Routing on a 2")
       3,            # Def Horse 1 Hit: absorbed ("roll of 3")
       2, 4,         # Att Horse: Light Horse Routs, Men-at-Arms Routs
       5,            # Def Foot: Teutonic unit Routs
       5]            # Att Foot: Domash's last unit Routs
    # -- Ending --
    + [3,            # 4.4.3 Service roll: shift ceil(3/2)=2 boxes left
       1, 1, 3, 4, 5,  # Losses, Domash Militia x5: two '1's stand
       4,            # Sergeants: lost
       2,            # Light Horse: lost
       2, 3,         # Men-at-Arms x2: both stand
       3, 2,         # Andreas Knights + Sergeants: both recovered
       5, 6, 4]      # Heinrich's three units: ALL lost -> Lord removed
)


def _zheltsy_battle(seed=1) -> GameState:
    s = load_scenario("watland", seed=seed)
    for lid in ("andreas", "heinrich"):
        s.lords[lid].state = "mustered"
        s.lords[lid].location = "zheltsy"
        s.lords[lid].moved_fought = True
    s.lords["heinrich"].forces = {"knights": 1, "sergeants": 1,
                                  "men_at_arms": 1}
    s.lords["heinrich"].assets = {"sled": 2, "provender": 1}
    s.lords["andreas"].assets = {"sled": 2}          # eats the Spoils later
    d = s.lords["domash"]
    d.location = "zheltsy"
    d.moved_fought = True
    # 5 starting units + 4 Mustered Novgorod Militia = 9 (pp. 9).
    d.forces = {"sergeants": 1, "men_at_arms": 2, "light_horse": 1,
                "militia": 5}
    d.assets = {"sled": 3, "provender": 4}
    d.this_lord_capabilities = ["R1"]                # Luchniki
    s.decks.teutonic.holds = ["T10"]                 # Field Organ
    s.decks.russian.holds = ["R5"]                   # Hill
    s.combat_pending = CombatPending(
        attacker_side="teutonic", attacker_group=["andreas", "heinrich"],
        from_locale="plyussa_river", to_locale="zheltsy",
        way_type="trackway",
        defender_side="russian", defender_lords=["domash"],
        pending_response_by="russian", laden=False,
        # The example shields Andreas's Horse: strongest-sacrifice list.
        attacker_absorption_policy=["knights", "sergeants", "men_at_arms"],
    )
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.campaign_turn.active_card = "andreas"
    s.campaign_turn.active_lord = "andreas"
    s.campaign_turn.actions_remaining = 0
    s.meta.active_player = "russian"
    return s


def test_playbook_battle_of_zheltsy_replays_exactly(monkeypatch):
    s = _zheltsy_battle()
    rolls = script_rolls(monkeypatch, PRINTED_ROLLS)
    r = apply_action(s, {"type": "stand_battle", "side": "russian", "args": {
        "holds": {"field_organ": "T10", "field_organ_lord": "andreas",
                  "hill": "R5"},
        # "put Domash's Militia out front ... save his Men-at-Arms":
        "absorption_policy": ["militia", "sergeants", "light_horse",
                              "men_at_arms"],
        "concede": "defender", "concede_round": 2,
        "retreat_to": {"domash": "sablia"},
        "scripted_decisions": [
            # Heinrich takes a flank; left/right "will not matter".
            {"type": "initial_placement_attacker", "chosen": "left"},
            # PLAY-28: Teutons choose Heinrich to absorb Domash's
            # Archery, then his Horse Melee.
            {"type": "flank_absorb", "chosen": "heinrich"},
            {"type": "flank_absorb", "chosen": "heinrich"},
        ],
    }})
    assert rolls.rolls == [], "every printed roll consumed, none extra"
    b = r["battle"]
    assert b["winner"] == "teutonic" and b["rounds"] == 2
    assert b["conceded"]

    # ---- printed Hit totals per strike step ----
    def _hits(round_i, step):
        rd = b["log"][round_i]
        out = []
        for st in rd["steps"]:
            if st["step"] == step:
                for dist in st.get("distribution", []):
                    out.append((dist["lord"], dist["hits"]))
        return out

    assert _hits(0, "archery_defender") == [("heinrich", 6)]   # Hill x1
    # PLAY-27: two Hits; Heinrich Routs mid-step, spill to Andreas.
    assert _hits(0, "melee_horse_defender") == [("heinrich", 2),
                                                ("andreas", 1)]
    assert _hits(0, "melee_horse_attacker") == [("domash", 7)]  # PLAY-41
    assert _hits(0, "melee_foot_defender") == [("andreas", 2)]
    assert _hits(0, "melee_foot_attacker") == [("domash", 1)]
    # Round 2, all Russian strikes Pursuit-halved to single Hits.
    assert _hits(1, "archery_defender") == [("andreas", 1)]
    assert _hits(1, "melee_horse_defender") == [("andreas", 1)]
    assert _hits(1, "melee_horse_attacker") == [("domash", 2)]
    assert _hits(1, "melee_foot_defender") == [("andreas", 1)]
    assert _hits(1, "melee_foot_attacker") == [("domash", 1)]

    # Both Held Events consumed.
    consumed = {h["card"] for h in b["holds_consumed"]}
    assert consumed == {"T10", "R5"}

    # ---- printed ending ----
    # Retreat + 4.4.3 Service: roll '3' -> 2 boxes left (7 -> 5).
    assert r["retreats"] == [{"lord": "domash", "to": "sablia",
                              "service_shift": 2}]
    assert s.lords["domash"].location == "sablia"
    assert "domash" in s.calendar.boxes[5 - 1].service_markers
    # Losses: Domash keeps 2 Militia + both Men-at-Arms (Conceded ->
    # standard Protection); Horse both lost.
    assert dict(s.lords["domash"].forces) == {"militia": 2,
                                              "men_at_arms": 2}
    # Andreas recovers all four units.
    assert dict(s.lords["andreas"].forces) == {"knights": 1,
                                               "sergeants": 2,
                                               "men_at_arms": 1}
    # "Heinrich falls in Battle and is permanently removed."
    assert s.lords["heinrich"].state == "removed"
    assert not any("heinrich" in cb.service_markers or
                   "heinrich" in cb.cylinders for cb in s.calendar.boxes)
    # Spoils: 1 excess Provender (4 vs 3 Sleds) to Andreas.
    assert s.lords["domash"].assets.get("provender") == 3
    assert s.lords["andreas"].assets.get("provender") == 1
    sp = [x for x in r["spoils"] if x["from"] == "domash"]
    assert sp and sp[0]["mode"] == "loot_and_excess"
    assert sp[0]["transferred"] == {"provender": 1}

    # ---- Feed (pp. 14 Aftermath): 1 Provender each ----
    apply_action(s, {"type": "fpd_resolve", "side": "teutonic",
                     "args": {"decline_pay": True}})
    apply_action(s, {"type": "fpd_resolve", "side": "russian",
                     "args": {"decline_pay": True}})
    # "Andreas the 'Prov' marker that he just claimed from Domash!"
    assert s.lords["andreas"].assets.get("provender", 0) == 0
    assert s.lords["domash"].assets.get("provender", 0) == 2
    # Neither goes Unfed.
    assert "domash" in s.calendar.boxes[5 - 1].service_markers
    assert "andreas" in s.calendar.boxes[7 - 1].service_markers
