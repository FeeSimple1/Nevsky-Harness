"""3.5.1: the Legate may arrive before the once-per-segment ACTIVE choice."""
from __future__ import annotations

import pytest

import nevsky.actions  # noqa: F401
from nevsky.actions import IllegalAction, _h_legate_arrives
from nevsky.scenarios import load_scenario


def test_arrives_leaves_the_active_choice_available():
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.decks.teutonic.capabilities_in_play.append("T13")
    s.legate.william_of_modena_in_play = True
    s.legate.location = "card"
    s.legate.locale_id = None
    s.legate.acted_this_call_to_arms = False
    s.meta.phase = "levy"
    s.meta.levy_step = "call_to_arms"
    s.meta.active_player = "teutonic"
    _h_legate_arrives(s, "teutonic", {"bishopric": "riga"})
    assert s.legate.acted_this_call_to_arms is False


def test_arrives_rejected_when_already_acted():
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.decks.teutonic.capabilities_in_play.append("T13")
    s.legate.william_of_modena_in_play = True
    s.legate.location = "card"
    s.legate.locale_id = None
    s.legate.acted_this_call_to_arms = True  # already acted
    s.meta.phase = "levy"
    s.meta.levy_step = "call_to_arms"
    s.meta.active_player = "teutonic"
    with pytest.raises(IllegalAction) as e:
        _h_legate_arrives(s, "teutonic", {"bishopric": "riga"})
    assert e.value.code == "already_acted"


def test_arrives_places_pawn():
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.decks.teutonic.capabilities_in_play.append("T13")
    s.legate.william_of_modena_in_play = True
    s.legate.location = "card"
    s.legate.locale_id = None
    s.legate.acted_this_call_to_arms = False
    s.meta.phase = "levy"
    s.meta.levy_step = "call_to_arms"
    s.meta.active_player = "teutonic"
    result, _ = _h_legate_arrives(s, "teutonic", {"bishopric": "dorpat"})
    assert result["placed_at"] == "dorpat"
    assert s.legate.location == "locale"
    assert s.legate.locale_id == "dorpat"
