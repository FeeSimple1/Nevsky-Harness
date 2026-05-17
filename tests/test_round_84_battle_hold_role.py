"""SMOKE-080 (Round 84): Tier 2 Battle Holds with "if Defending" role
restriction were consumed without role gating.

Per AoW Reference card texts:
  T5 Marsh:  "May play if Defending in non-Winter Battle..."
  R2 Marsh:  "May play if Defending in non-Winter Battle..."
  T9 Hill:   "May play if Defending in Battle—Round 1 and 2 Teutonic Archery is x1..."
  R5 Hill:   "May play if Defending in Battle—Round 1 and 2 Russian Archery is x1..."

_consume_battle_holds enforced neither the role of the playing side
nor a side-vs-defender match. An attacker could pass holds={"marsh":
"T5"} and the function would happily move T5 to discard, applying
its effect (block attacker Horse R1-2) and effectively penalising
the attacker's own Horse units.

Fix: a Defending-only restriction is enforced — for each restricted
card, the card's side must equal cp.defender_side; otherwise
`role_blocked` is raised.
"""
from __future__ import annotations

import pytest

import nevsky.actions  # noqa: F401 — register handlers
from nevsky.actions import IllegalAction
from nevsky.events import _consume_battle_holds
from nevsky.scenarios import load_scenario
from nevsky.state import CombatPending


def _mk_cp(attacker="teutonic", defender="russian"):
    return CombatPending(
        attacker_side=attacker, attacker_group=[], defender_lords=[],
        from_locale="dorpat", to_locale="odenpah", way_type="trackway",
        defender_side=defender, pending_response_by=defender, laden=False,
    )


def test_marsh_t5_rejected_when_teutonic_attacker():
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.box = 1  # Summer (passes season check)
    s.decks.teutonic.holds.append("T5")
    # Teu attacker, Rus defender — T5 should be Defending-only on Teu side.
    with pytest.raises(IllegalAction) as e:
        _consume_battle_holds(s, _mk_cp(), {"marsh": "T5"})
    assert e.value.code == "role_blocked"
    assert "T5" in s.decks.teutonic.holds


def test_marsh_r2_rejected_when_russian_attacker():
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.box = 1
    s.decks.russian.holds.append("R2")
    cp = _mk_cp(attacker="russian", defender="teutonic")
    with pytest.raises(IllegalAction) as e:
        _consume_battle_holds(s, cp, {"marsh": "R2"})
    assert e.value.code == "role_blocked"


def test_hill_t9_rejected_when_teutonic_attacker():
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.decks.teutonic.holds.append("T9")
    with pytest.raises(IllegalAction) as e:
        _consume_battle_holds(s, _mk_cp(), {"hill": "T9"})
    assert e.value.code == "role_blocked"


def test_hill_r5_rejected_when_russian_attacker():
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.decks.russian.holds.append("R5")
    cp = _mk_cp(attacker="russian", defender="teutonic")
    with pytest.raises(IllegalAction) as e:
        _consume_battle_holds(s, cp, {"hill": "R5"})
    assert e.value.code == "role_blocked"


def test_marsh_t5_accepted_when_teutonic_defender():
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.box = 1
    s.decks.teutonic.holds.append("T5")
    cp = _mk_cp(attacker="russian", defender="teutonic")
    consumed = _consume_battle_holds(s, cp, {"marsh": "T5"})
    assert consumed == [{"card": "T5", "key": "marsh"}]


def test_hill_r5_accepted_when_russian_defender():
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.decks.russian.holds.append("R5")
    consumed = _consume_battle_holds(s, _mk_cp(), {"hill": "R5"})
    assert consumed == [{"card": "R5", "key": "hill"}]


def test_unrestricted_holds_still_role_agnostic():
    """Bridge (T4/R1), Ambush (T6/R6), Field Organ (T10), Raven's Rock (R4)
    don't have 'if Defending' restriction in their text — they remain
    role-agnostic in the harness."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.box = 1  # Summer (avoids R4 season-block)
    s.decks.teutonic.holds.extend(["T4", "T6", "T10"])
    s.decks.russian.holds.append("R4")
    # T4 Bridge played by Teu attacker on Rus defender's center.
    # SMOKE-082: T4 Bridge requires a Russian target in current combat.
    cp_with_br = _mk_cp()
    cp_with_br.defender_lords = ["aleksandr"]
    consumed = _consume_battle_holds(s, cp_with_br, {"bridge": "T4", "bridge_target_lord": "aleksandr"})
    assert consumed == [{"card": "T4", "key": "bridge"}]
    # T6 Ambush.
    consumed = _consume_battle_holds(s, _mk_cp(), {"ambush": "T6"})
    assert consumed == [{"card": "T6", "key": "ambush"}]
    # T10 Field Organ.
    cp_with_fo = _mk_cp()
    cp_with_fo.attacker_group = ["hermann"]
    consumed = _consume_battle_holds(s, cp_with_fo, {"field_organ": "T10", "field_organ_lord": "hermann"})
    assert consumed == [{"card": "T10", "key": "field_organ"}]
