"""SMOKE-079 (Round 83): Tier 2 Battle Holds with explicit season
restrictions on the card text were consumed without season gating.

Per AoW Reference card texts:
  T5 Marsh: "Hold: May play if Defending in non-Winter Battle..."
  R2 Marsh: "Hold: May play if Defending in non-Winter Battle..."
  R4 Raven's Rock: "Hold: May play in non-Summer Battle..."

The Bridge (T4/R1) season check was wired in battle.py via
`bridge_target_lord = None` when Winter is detected, but Marsh and
Raven's Rock had no season gate at the consumption stage —
_consume_battle_holds silently moved the card to discard AND let its
effect apply in the wrong season.

Fix: add a season-restriction table in _consume_battle_holds and
raise `season_blocked` when the season violates the card text.
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


def test_marsh_t5_rejected_in_winter():
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.box = 3  # Early Winter
    s.decks.teutonic.holds.append("T5")
    with pytest.raises(IllegalAction) as e:
        _consume_battle_holds(s, _mk_cp(), {"marsh": "T5"})
    assert e.value.code == "season_blocked"
    # Card not consumed.
    assert "T5" in s.decks.teutonic.holds


def test_marsh_r2_rejected_in_late_winter():
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.box = 5  # Late Winter
    s.decks.russian.holds.append("R2")
    with pytest.raises(IllegalAction) as e:
        _consume_battle_holds(s, _mk_cp(attacker="russian", defender="teutonic"), {"marsh": "R2"})
    assert e.value.code == "season_blocked"


def test_marsh_t5_accepted_in_summer():
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.box = 1  # Summer
    s.decks.teutonic.holds.append("T5")
    consumed = _consume_battle_holds(s, _mk_cp(), {"marsh": "T5"})
    assert consumed == [{"card": "T5", "key": "marsh"}]
    assert "T5" in s.decks.teutonic.discard


def test_marsh_t5_accepted_in_rasputitsa():
    """Marsh: non-Winter includes Rasputitsa (mud)."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.box = 7  # Rasputitsa
    s.decks.teutonic.holds.append("T5")
    consumed = _consume_battle_holds(s, _mk_cp(), {"marsh": "T5"})
    assert consumed == [{"card": "T5", "key": "marsh"}]


def test_ravens_rock_r4_rejected_in_summer():
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.box = 1  # Summer
    s.decks.russian.holds.append("R4")
    with pytest.raises(IllegalAction) as e:
        _consume_battle_holds(s, _mk_cp(), {"raven_rock": "R4"})
    assert e.value.code == "season_blocked"


def test_ravens_rock_r4_accepted_in_winter():
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.box = 3  # Early Winter
    s.decks.russian.holds.append("R4")
    consumed = _consume_battle_holds(s, _mk_cp(), {"raven_rock": "R4"})
    assert consumed == [{"card": "R4", "key": "raven_rock"}]


def test_ravens_rock_r4_accepted_in_rasputitsa():
    """Raven's Rock: non-Summer includes Rasputitsa."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.box = 7  # Rasputitsa
    s.decks.russian.holds.append("R4")
    consumed = _consume_battle_holds(s, _mk_cp(), {"raven_rock": "R4"})
    assert consumed == [{"card": "R4", "key": "raven_rock"}]


def test_unrestricted_holds_unaffected_by_season():
    """T9/R5 Hill, T6/R6 Ambush, T10 Field Organ have no season restriction."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.box = 3  # Winter - should not affect Hill / Ambush / Field Organ
    s.decks.teutonic.holds.extend(["T9", "T6", "T10"])
    consumed = _consume_battle_holds(s, _mk_cp(), {"hill": "T9"})
    assert consumed == [{"card": "T9", "key": "hill"}]
    consumed = _consume_battle_holds(s, _mk_cp(), {"ambush": "T6"})
    assert consumed == [{"card": "T6", "key": "ambush"}]
    consumed = _consume_battle_holds(s, _mk_cp(), {"field_organ": "T10"})
    assert consumed == [{"card": "T10", "key": "field_organ"}]
