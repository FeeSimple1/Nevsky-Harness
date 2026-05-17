"""SMOKE-082 (Round 86): T4/R1 Bridge target validation.

Per AoW Reference card texts:
  T4 Bridge: "May play on front center Russian Lord..."
  R1 Bridge: "May play on front center Teutonic Lord..."

`_consume_battle_holds` accepted the card without any target
validation. An agent could pass `holds={"bridge": "T4",
"bridge_target_lord": "hermann"}` and the card would discard;
because Hermann is Teutonic (own side, not "front center Russian"),
the actual Bridge cap effect would silently apply to a Teutonic
Lord instead of a Russian one — a self-handicap matching the
Marsh / Hill pattern.

Fix: T4 must target a Russian Lord in current combat; R1 must
target a Teutonic Lord in current combat. Missing or unknown
target raises `missing_target` / `bad_target`.
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
        attacker_side=attacker,
        attacker_group=["hermann"],
        defender_lords=["aleksandr"],
        from_locale="dorpat", to_locale="ostrov", way_type="trackway",
        defender_side=defender, pending_response_by=defender, laden=False,
    )


def test_bridge_t4_rejects_missing_target():
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.box = 1
    s.decks.teutonic.holds.append("T4")
    with pytest.raises(IllegalAction) as e:
        _consume_battle_holds(s, _mk_cp(), {"bridge": "T4"})
    assert e.value.code == "missing_target"


def test_bridge_t4_rejects_own_side_target():
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.box = 1
    s.decks.teutonic.holds.append("T4")
    with pytest.raises(IllegalAction) as e:
        _consume_battle_holds(
            s, _mk_cp(),
            {"bridge": "T4", "bridge_target_lord": "hermann"},
        )
    assert e.value.code == "bad_target"


def test_bridge_t4_rejects_unknown_lord():
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.box = 1
    s.decks.teutonic.holds.append("T4")
    with pytest.raises(IllegalAction) as e:
        _consume_battle_holds(
            s, _mk_cp(),
            {"bridge": "T4", "bridge_target_lord": "not_a_lord"},
        )
    assert e.value.code == "bad_target"


def test_bridge_t4_rejects_target_not_in_combat():
    """A Russian Lord not in cp.defender_lords or cp.attacker_group."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.box = 1
    s.decks.teutonic.holds.append("T4")
    # andrey is Russian but not in cp.defender_lords (only aleksandr).
    with pytest.raises(IllegalAction) as e:
        _consume_battle_holds(
            s, _mk_cp(),
            {"bridge": "T4", "bridge_target_lord": "andrey"},
        )
    assert e.value.code == "bad_target"


def test_bridge_t4_accepts_russian_defender_in_combat():
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.box = 1
    s.decks.teutonic.holds.append("T4")
    consumed = _consume_battle_holds(
        s, _mk_cp(),
        {"bridge": "T4", "bridge_target_lord": "aleksandr"},
    )
    assert consumed == [{"card": "T4", "key": "bridge"}]


def test_bridge_r1_rejects_russian_target():
    """R1 must target Teutonic; passing a Russian Lord is rejected."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.box = 1
    s.decks.russian.holds.append("R1")
    cp = _mk_cp(attacker="russian", defender="teutonic")
    cp.attacker_group = ["aleksandr"]
    cp.defender_lords = ["hermann"]
    with pytest.raises(IllegalAction) as e:
        _consume_battle_holds(
            s, cp,
            {"bridge": "R1", "bridge_target_lord": "aleksandr"},
        )
    assert e.value.code == "bad_target"


def test_bridge_r1_accepts_teutonic_defender_in_combat():
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.box = 1
    s.decks.russian.holds.append("R1")
    cp = _mk_cp(attacker="russian", defender="teutonic")
    cp.attacker_group = ["aleksandr"]
    cp.defender_lords = ["hermann"]
    consumed = _consume_battle_holds(
        s, cp,
        {"bridge": "R1", "bridge_target_lord": "hermann"},
    )
    assert consumed == [{"card": "R1", "key": "bridge"}]
