"""SMOKE-077 (Round 78): R18 Stone Kremlin allows Walls +1 on a locale
that already has a Castle marker overlay.

Per AoW Reference R18 card text: "Walls +1 at Russian Fort, City, or
Novgorod." T17 Stonemasons Tip: "The Castle marker REPLACES the Fort
or Town at its Locale and removes any 'Walls +1' marker there (see
Russian Capability R18 Stone Kremlin)." — Castle and Walls +1 are
mutually exclusive; once a Castle marker is on a locale, the base
Fort/City has been replaced and Walls +1 is no longer applicable.

The previous code keyed off `static_loc["type"]` only and missed the
Castle-overlay short-circuit. A Russian Fort overlaid with a
russian_castle marker (e.g. from initial scenario setup or via
post-flip-on-Conquest dance) would still accept Stone Kremlin
Walls +1, resulting in a Castle marker AND a Walls +1 marker
co-existing — directly contradicting T17 Tip.
"""
from __future__ import annotations

import pytest

import nevsky.actions  # noqa: F401 — register handlers
from nevsky.actions import IllegalAction
from nevsky.campaign import _h_cmd_stone_kremlin
from nevsky.scenarios import load_scenario


def _setup_aleksandr_at_locale(s, locale_id):
    """Place Aleksandr at a Russian Stronghold with R18 tucked and full Command card."""
    aleksandr = s.lords["aleksandr"]
    aleksandr.location = locale_id
    aleksandr.state = "mustered"
    aleksandr.in_stronghold = False
    aleksandr.moved_fought = False
    aleksandr.this_lord_capabilities = ["R18"]
    s.campaign_turn.active_lord = "aleksandr"
    s.campaign_turn.actions_remaining = 5
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.campaign_turn.in_feed_pay_disband = False


def test_stone_kremlin_rejects_locale_with_russian_castle_overlay():
    s = load_scenario("crusade_on_novgorod", seed=1)
    _setup_aleksandr_at_locale(s, "velikiye_luki")
    s.locales["velikiye_luki"].russian_castle = True
    s.locales["velikiye_luki"].walls_plus_one = False
    with pytest.raises(IllegalAction) as e:
        _h_cmd_stone_kremlin(s, "russian", {"lord_id": "aleksandr"})
    assert e.value.code == "castle_overlay"
    assert s.locales["velikiye_luki"].walls_plus_one is False


def test_stone_kremlin_rejects_locale_with_teutonic_castle_overlay():
    """Even a Teutonic Castle on a former Russian Fort blocks R18 Walls +1
    (the base Stronghold has been replaced)."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    _setup_aleksandr_at_locale(s, "velikiye_luki")
    s.locales["velikiye_luki"].teutonic_castle = True
    s.locales["velikiye_luki"].walls_plus_one = False
    with pytest.raises(IllegalAction) as e:
        _h_cmd_stone_kremlin(s, "russian", {"lord_id": "aleksandr"})
    assert e.value.code == "castle_overlay"


def test_stone_kremlin_succeeds_at_plain_fort():
    """Regression: Stone Kremlin still works on a plain Russian Fort
    with no Castle marker."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    _setup_aleksandr_at_locale(s, "velikiye_luki")
    s.locales["velikiye_luki"].russian_castle = False
    s.locales["velikiye_luki"].teutonic_castle = False
    s.locales["velikiye_luki"].walls_plus_one = False
    result, _ = _h_cmd_stone_kremlin(s, "russian", {"lord_id": "aleksandr"})
    assert result["walls_plus_one"] is True
    assert s.locales["velikiye_luki"].walls_plus_one is True


def test_stone_kremlin_succeeds_at_city():
    """Regression: Stone Kremlin works on a Russian City."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    _setup_aleksandr_at_locale(s, "pskov")
    s.locales["pskov"].russian_castle = False
    s.locales["pskov"].teutonic_castle = False
    s.locales["pskov"].walls_plus_one = False
    result, _ = _h_cmd_stone_kremlin(s, "russian", {"lord_id": "aleksandr"})
    assert result["walls_plus_one"] is True
