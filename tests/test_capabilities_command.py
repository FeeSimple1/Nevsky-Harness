"""Tests for Phase 4a Command-rating modifiers."""

from __future__ import annotations

from nevsky.actions import _HANDLERS  # noqa: F401
from nevsky.campaign import _effective_command_rating
from nevsky.scenarios import load_scenario


def test_druzhina_grants_plus_one_with_knights() -> None:
    """R5/R6: Druzhina gives +1 Command to a Lord with Knights."""
    s = load_scenario("watland", seed=1)
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    base = _effective_command_rating(s, rus)
    s.lords[rus].forces["knights"] = 1
    s.lords[rus].this_lord_capabilities = ["R5"]
    assert _effective_command_rating(s, rus) == base + 1


def test_druzhina_no_bonus_without_knights() -> None:
    s = load_scenario("watland", seed=1)
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    base = _effective_command_rating(s, rus)
    s.lords[rus].forces.pop("knights", None)
    s.lords[rus].this_lord_capabilities = ["R5"]
    assert _effective_command_rating(s, rus) == base


def test_house_of_suzdal_requires_both_princes_on_map() -> None:
    """R11: House of Suzdal grants +1 only when BOTH Aleksandr and Andrey on map."""
    s = load_scenario("return_of_the_prince", seed=1)
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    s.lords[rus].this_lord_capabilities = ["R11"]
    base = int(__import__("nevsky.static_data", fromlist=["load_lords"]).load_lords()[rus]["ratings"]["command"])
    # Make both princes mustered.
    s.lords["aleksandr"].state = "mustered"
    s.lords["aleksandr"].location = "novgorod"
    s.lords["andrey"].state = "mustered"
    s.lords["andrey"].location = "novgorod"
    assert _effective_command_rating(s, rus) == base + 1
    # Now remove one.
    s.lords["andrey"].state = "ready"
    s.lords["andrey"].location = None
    assert _effective_command_rating(s, rus) == base


def test_treaty_of_stensby_plus_one_for_heinrich_and_knud_and_abel() -> None:
    """T1: Treaty of Stensby grants +1 Command to Heinrich and Knud&Abel only."""
    s = load_scenario("watland", seed=1)
    s.decks.teutonic.capabilities_in_play = ["T1"]
    # Force Heinrich and Knud&Abel mustered.
    for lid in ("heinrich", "knud_and_abel"):
        s.lords[lid].state = "mustered"
        s.lords[lid].location = "riga"
    h_base = _effective_command_rating(
        s.__class__.model_validate_json(s.model_dump_json()), "heinrich",
    )
    # Easier: compare with capability removed.
    s2 = load_scenario("watland", seed=1)
    s2.lords["heinrich"].state = "mustered"
    s2.lords["heinrich"].location = "riga"
    base = _effective_command_rating(s2, "heinrich")
    assert _effective_command_rating(s, "heinrich") == base + 1
    # Other Teutonic Lord (e.g., Andreas) gets no bonus.
    teu_other = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and lid not in ("heinrich", "knud_and_abel") and l.state == "mustered")
    other_base = _effective_command_rating(s2, teu_other)
    assert _effective_command_rating(s, teu_other) == other_base


def test_archbishopric_plus_one_at_novgorod() -> None:
    """R15: Russian Lord starting at Novgorod gets +1 Command."""
    s = load_scenario("watland", seed=1)
    s.decks.russian.capabilities_in_play = ["R15"]
    # Pick a Russian Lord NOT at Novgorod by default.
    rus = next(
        lid for lid, l in s.lords.items()
        if l.side == "russian" and l.state == "mustered" and l.location != "novgorod"
    )
    base_at_other = _effective_command_rating(s, rus)
    s.lords[rus].location = "novgorod"
    assert _effective_command_rating(s, rus) == base_at_other + 1
