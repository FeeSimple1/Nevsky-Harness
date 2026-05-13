"""Round 52 — SMOKE-040 regression tests.

T17 Stonemasons Tips: "Castles are permanent. They flip when
Conquered." Castle markers (russian_castle / teutonic_castle bools
on Locale) must flip color on Conquest (Storm Sack or Siege
Surrender). VP swings by 2 per flip (-1 old color, +1 new color),
since each Castle marker is worth 1 VP.
"""

import nevsky.actions  # ensure handlers registered (avoid circular import)
from nevsky.scenarios import load_scenario
from nevsky.campaign import _apply_conquest_or_liberation


def test_russian_castle_flips_to_teutonic_on_conquest():
    st = load_scenario("pleskau", seed=1)
    loc = st.locales["izborsk"]
    loc.russian_castle = True
    teu_vp_before = st.calendar.teutonic_vp
    rus_vp_before = st.calendar.russian_vp
    change = _apply_conquest_or_liberation(st, "izborsk", "teutonic", 1)
    assert loc.russian_castle is False
    assert loc.teutonic_castle is True
    # +1 sh_vp + 1 castle flip = +2 to teutonic; -1 castle flip from russian
    assert st.calendar.teutonic_vp == teu_vp_before + 2.0
    assert st.calendar.russian_vp == rus_vp_before - 1.0
    assert change["castle_flip"] == {"from": "russian", "to": "teutonic"}


def test_teutonic_castle_flips_to_russian_on_liberation():
    st = load_scenario("pleskau", seed=1)
    # Set up: a Russian-territory locale with teutonic_castle and
    # teutonic_conquered. Russian liberates -> castle flips russian.
    loc = st.locales["izborsk"]
    loc.teutonic_castle = True
    loc.teutonic_conquered = 1
    st.calendar.teutonic_vp += 2.0  # 1 conquered + 1 castle
    teu_vp_before = st.calendar.teutonic_vp
    rus_vp_before = st.calendar.russian_vp
    change = _apply_conquest_or_liberation(st, "izborsk", "russian", 1)
    assert loc.teutonic_castle is False
    assert loc.russian_castle is True
    # Liberation clears teutonic_conquered (1 VP back to teutonic = -1)
    # Castle flip: -1 from teu, +1 to rus
    assert st.calendar.teutonic_vp == teu_vp_before - 2.0  # -1 conquered, -1 castle
    assert st.calendar.russian_vp == rus_vp_before + 1.0
    assert change["castle_flip"] == {"from": "teutonic", "to": "russian"}


def test_no_castle_marker_no_flip():
    """If the locale has no Castle marker, no flip happens."""
    st = load_scenario("pleskau", seed=1)
    loc = st.locales["izborsk"]
    loc.russian_castle = False
    loc.teutonic_castle = False
    change = _apply_conquest_or_liberation(st, "izborsk", "teutonic", 1)
    assert loc.russian_castle is False
    assert loc.teutonic_castle is False
    assert "castle_flip" not in change


def test_same_color_castle_no_flip_on_re_conquest():
    """If a teutonic_castle is hit by a teutonic conqueror (e.g., re-
    Storm of own conquered castle for some reason), no flip."""
    st = load_scenario("pleskau", seed=1)
    loc = st.locales["izborsk"]
    loc.teutonic_castle = True
    change = _apply_conquest_or_liberation(st, "izborsk", "teutonic", 1)
    assert loc.teutonic_castle is True
    assert loc.russian_castle is False
    assert "castle_flip" not in change
