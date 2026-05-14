"""SMOKE-060 (Round 68): T11 Crusade auto-fires free Muster of Summer
Crusaders on entry to Muster step in a Summer Levy.

Per AoW Reference T11 Tip:
- "automatically Musters all Summer Crusader Knights to Andreas and
  Rudolf at no cost in Lordship actions, even in enemy territory,
  provided that the Lord is himself Mustered and is Unbesieged."
- "If already Mustered and any Knights have been lost from the Lord's
  Forces, restore Knight units up those shown on the Vassal marker."
"""
from __future__ import annotations

import pytest

from nevsky.actions import apply_action, _t11_summer_auto_muster, _season_of_box
from nevsky.scenarios import load_scenario


def _setup_summer_levy_at_muster_entry():
    """Crusade on Novgorod starts Summer Levy at box 1.

    Advance 3 levy steps (arts_of_war -> pay -> disband -> muster) so we
    trigger the auto-fire on muster-step entry. Returns the state after
    the auto-fire.
    """
    s = load_scenario("crusade_on_novgorod", seed=1)
    assert _season_of_box(s.meta.box) == "summer"
    s.decks.teutonic.capabilities_in_play.append("T11")
    # Force Andreas mustered (default he's on Calendar)
    andreas = s.lords["andreas"]
    andreas.state = "mustered"
    andreas.location = "fellin"
    andreas.forces = {"knights": 4, "sergeants": 3, "men_at_arms": 4, "light_horse": 1, "militia": 1}
    andreas.vassals["andreas_summer_crusaders_1"].ready = True
    return s, andreas


def test_t11_auto_musters_summer_crusaders_at_summer_muster_entry():
    """Andreas Mustered Unbesieged, T11 in play, Summer Levy →
    Summer Crusaders auto-muster at no Lordship cost."""
    s, andreas = _setup_summer_levy_at_muster_entry()
    assert not andreas.vassals["andreas_summer_crusaders_1"].mustered
    knights_before = andreas.forces.get("knights", 0)

    # Advance 3 levy steps to enter muster
    for _ in range(3):
        apply_action(s, {"type": "advance_step", "side": "teutonic"})
        apply_action(s, {"type": "advance_step", "side": "russian"})

    assert s.meta.levy_step == "muster"
    assert andreas.vassals["andreas_summer_crusaders_1"].mustered is True
    # Summer Crusaders vassal has 3 knights
    assert andreas.forces["knights"] == knights_before + 3
    assert andreas.lordship_used == 0, "auto-muster must not consume Lordship"


def test_t11_restores_lost_knights_when_sc_already_mustered():
    """Rudolf already Mustered with SC, lost knights → next Summer Levy
    restores knights up to SC Vassal marker count."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    assert _season_of_box(s.meta.box) == "summer"
    s.decks.teutonic.capabilities_in_play.append("T11")
    rudolf = s.lords["rudolf"]
    rudolf.state = "mustered"
    rudolf.location = "wenden"
    rudolf.vassals["rudolf_summer_crusaders"].ready = True
    rudolf.vassals["rudolf_summer_crusaders"].mustered = True
    # Rudolf base = 1 knight; SC = 2 knights. Expected = 3. Set to 0 (lost 3).
    rudolf.forces = {"knights": 0, "sergeants": 2, "men_at_arms": 2}

    for _ in range(3):
        apply_action(s, {"type": "advance_step", "side": "teutonic"})
        apply_action(s, {"type": "advance_step", "side": "russian"})

    # Restored 2 knights (capped by SC marker)
    assert rudolf.forces["knights"] == 2


def test_t11_skips_besieged_lord():
    """Lord Besieged → no auto-muster (must be Unbesieged)."""
    s, andreas = _setup_summer_levy_at_muster_entry()
    # Put andreas in a Stronghold under siege
    andreas.in_stronghold = True
    s.locales[andreas.location].siege_markers = 1

    for _ in range(3):
        apply_action(s, {"type": "advance_step", "side": "teutonic"})
        apply_action(s, {"type": "advance_step", "side": "russian"})

    assert andreas.vassals["andreas_summer_crusaders_1"].mustered is False, \
        "Besieged Lord must not auto-muster Summer Crusaders"


def test_t11_skips_unmustered_lord():
    """Lord not Mustered → no auto-muster."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.decks.teutonic.capabilities_in_play.append("T11")
    # Andreas is Ready by default (on calendar), not Mustered
    andreas = s.lords["andreas"]
    assert andreas.state != "mustered"
    andreas.vassals["andreas_summer_crusaders_1"].ready = True

    for _ in range(3):
        apply_action(s, {"type": "advance_step", "side": "teutonic"})
        apply_action(s, {"type": "advance_step", "side": "russian"})

    assert andreas.vassals["andreas_summer_crusaders_1"].mustered is False, \
        "Unmustered Lord cannot have SC auto-mustered"


def test_t11_does_not_fire_in_non_summer_levy():
    """Non-Summer Levy → no T11 auto-fire even with T11 in play."""
    s = load_scenario("watland", seed=1)  # box 4 = early_winter
    assert _season_of_box(s.meta.box) != "summer"
    s.decks.teutonic.capabilities_in_play.append("T11")
    andreas = s.lords["andreas"]
    andreas.state = "mustered"
    andreas.location = "fellin"
    andreas.vassals["andreas_summer_crusaders_1"].ready = True

    for _ in range(3):
        apply_action(s, {"type": "advance_step", "side": "teutonic"})
        apply_action(s, {"type": "advance_step", "side": "russian"})

    assert andreas.vassals["andreas_summer_crusaders_1"].mustered is False, \
        "Non-Summer Levy must not trigger T11 auto-muster"


def test_t11_no_fire_when_t11_not_in_play():
    """Summer Levy without T11 in play → no auto-fire."""
    s, andreas = _setup_summer_levy_at_muster_entry()
    # Remove T11 from play
    s.decks.teutonic.capabilities_in_play.remove("T11")

    for _ in range(3):
        apply_action(s, {"type": "advance_step", "side": "teutonic"})
        apply_action(s, {"type": "advance_step", "side": "russian"})

    assert andreas.vassals["andreas_summer_crusaders_1"].mustered is False
