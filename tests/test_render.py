"""Tests for state rendering modes."""

from __future__ import annotations

import pytest

from nevsky.render import render_focus, render_summary, render_verbose, season
from nevsky.scenarios import load_scenario


@pytest.fixture
def peipus_state():
    return load_scenario("peipus", seed=1)


def test_summary_includes_header_and_vp(peipus_state) -> None:
    """summary shows scenario name, box, season, phase, and VPs."""
    out = render_summary(peipus_state)
    assert "Peipus" in out
    assert "box 13" in out
    assert "Late Winter 1242" in out
    assert "VP: R=5" in out
    assert "T=6" in out


def test_summary_lists_mustered_lords_with_locations(peipus_state) -> None:
    """summary lists Mustered Lords by side with their locale id."""
    out = render_summary(peipus_state)
    assert "aleksandr@novgorod" in out
    assert "hermann@dorpat" in out


def test_summary_token_budget_under_500(peipus_state) -> None:
    """BRIEF: summary mode targets ~500 tokens. We approximate with
    char/4 == tokens (conservative estimate). Peipus is one of the
    larger scenarios in active state."""
    out = render_summary(peipus_state)
    approx_tokens = len(out) / 4
    assert approx_tokens < 700, f"summary too large: ~{approx_tokens:.0f} tokens"


def test_verbose_is_valid_json(peipus_state) -> None:
    """verbose round-trips through GameState parser."""
    import json
    from nevsky.state import GameState
    text = render_verbose(peipus_state)
    parsed = json.loads(text)
    GameState.model_validate(parsed)


def test_focus_lord_basic(peipus_state) -> None:
    """focus lord:<id> shows ratings, seats, forces, vassals."""
    out = render_focus(peipus_state, "lord:aleksandr")
    assert "Aleksandr" in out
    assert "Service=6" in out
    assert "Lordship=4" in out
    assert "Fealty=None" in out  # Aleksandr has no Fealty
    assert "novgorod" in out  # primary seat
    assert "knights" in out and "men_at_arms" in out


def test_focus_locale_basic(peipus_state) -> None:
    """focus locale:<id> shows type, territory, markers, neighbors."""
    out = render_focus(peipus_state, "locale:pskov")
    assert "Pskov" in out
    assert "city" in out
    assert "Tconq" in out  # Teutonic conquered markers
    assert "izborsk" in out  # neighbor


def test_focus_calendar_lists_all_16_boxes(peipus_state) -> None:
    """focus calendar shows boxes 1-16 inclusive."""
    out = render_focus(peipus_state, "calendar")
    for n in range(1, 17):
        assert f"box {n:2d}" in out


def test_focus_veche_shows_caps(peipus_state) -> None:
    """focus veche shows coin and vp_markers with /8 cap."""
    out = render_focus(peipus_state, "veche")
    assert "coin: 3/8" in out
    assert "vp_markers: 4/8" in out


def test_focus_deck_lists_all_piles(peipus_state) -> None:
    """focus deck:<side> lists draw / discard / removed / cap-in-play /
    holds / Plan."""
    out = render_focus(peipus_state, "deck:teutonic")
    for label in ("draw pile", "discard", "removed from play", "capabilities in play", "hold events", "current Plan"):
        assert label in out


def test_focus_invalid_format_errors(peipus_state) -> None:
    """unknown focus syntax raises ValueError."""
    with pytest.raises(ValueError):
        render_focus(peipus_state, "garbage")
    with pytest.raises(ValueError):
        render_focus(peipus_state, "deck:typo")


def test_season_labels_per_calendar_reference() -> None:
    """Calendar reference: 2 boxes per season, 8 seasons across 16
    boxes."""
    assert season(1) == "Summer 1240"
    assert season(2) == "Summer 1240"
    assert season(3) == "Early Winter 1240"
    assert season(7) == "Rasputitsa 1241"
    assert season(8) == "Rasputitsa 1241"
    assert season(9) == "Summer 1241"
    assert season(13) == "Late Winter 1242"
    assert season(16) == "Rasputitsa 1242"
