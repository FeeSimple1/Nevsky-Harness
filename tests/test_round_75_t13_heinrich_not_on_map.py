"""T13's unused Capability and Held Event have different eligibility."""
from __future__ import annotations

import pytest

from nevsky.actions import IllegalAction, _place_lord_on_map, apply_action
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import load_scenario


@pytest.mark.parametrize("status", ["ready", "disbanded", "removed", "mustered"])
@pytest.mark.parametrize("source", ["deck", "discard"])
def test_unused_t13_can_be_levied_regardless_of_heinrich(status, source):
    s = load_scenario("pleskau" if status == "removed" else "watland", seed=1)
    s.meta.levy_step = "muster"
    s.meta.active_player = "teutonic"
    if status == "mustered":
        _place_lord_on_map(s, "heinrich", "leal", s.meta.box)
    elif status == "disbanded":
        s.lords["heinrich"].state = "disbanded"
        # The later return box keeps him Disbanded after the action.
        for box in s.calendar.boxes:
            if "heinrich" in box.cylinders:
                box.cylinders.remove("heinrich")
        s.calendar.boxes[s.meta.box + 1].cylinders.append("heinrich")
    assert s.lords["heinrich"].state == status
    assert (s.lords["heinrich"].location is not None) == (status == "mustered")
    deck = s.decks.teutonic
    if source == "discard":
        deck.deck.remove("T13")
        deck.discard.append("T13")
    by_lord = "hermann" if status == "removed" else "andreas"
    action = {"type": "levy_capability", "side": "teutonic",
              "args": {"by_lord": by_lord, "card_id": "T13"}}
    assert any(m["type"] == action["type"] and m.get("args") == action["args"]
               for m in legal_moves(s, with_previews=False))
    result = apply_action(s, action)
    assert result["from"] == source
    assert deck.capabilities_in_play.count("T13") == 1
    assert "T13" not in deck.deck + deck.discard
    assert s.legate.william_of_modena_in_play and s.legate.location == "card"
    assert s.legate.locale_id is None


@pytest.mark.parametrize("zone", ["holds", "pending_draw", "removed", "capabilities_in_play"])
def test_t13_levy_requires_the_card_in_an_unused_pile(zone):
    s = load_scenario("watland", seed=1)
    s.meta.levy_step = "muster"
    deck = s.decks.teutonic
    deck.deck.remove("T13")
    getattr(deck, zone).append("T13")
    before = s.model_dump_json()
    assert not any(m["type"] == "levy_capability" and m.get("args", {}).get("card_id") == "T13"
                   for m in legal_moves(s, with_previews=False))
    with pytest.raises(IllegalAction, match="card_unavailable"):
        apply_action(s, {"type": "levy_capability", "side": "teutonic",
                         "args": {"by_lord": "andreas", "card_id": "T13"}})
    assert s.model_dump_json() == before


def test_curia_event_requires_heinrich_on_map():
    s = load_scenario("watland", seed=1)
    deck = s.decks.teutonic
    deck.deck.remove("T13")
    deck.holds.append("T13")
    action = {"type": "aow_play_hold", "side": "teutonic",
              "args": {"card_id": "T13", "recipients": ["andreas", "knud_and_abel"]}}
    before = s.model_dump_json()
    with pytest.raises(IllegalAction, match="heinrich_off_map"):
        apply_action(s, action)
    assert s.model_dump_json() == before

    _place_lord_on_map(s, "heinrich", "leal", s.meta.box)
    apply_action(s, action)
    assert s.lords["heinrich"].state == "disbanded"
    assert "T13" in deck.discard and "T13" not in deck.holds
    assert not s.legate.william_of_modena_in_play
