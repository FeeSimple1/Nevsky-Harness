"""SMOKE-074 (Round 77): storm_preview missed Castle-on-Town overlays.

`storm_preview` used `load_strongholds().get(static_loc["type"])` to
fetch Stronghold metadata, keying off the locale's base type. A Town
locale with a Castle marker overlay (T17 Stonemasons) returned None,
so storm_preview reported "not a stormable Stronghold" — even though
a Castle is stormable.

Fix: use `_effective_stronghold` (campaign helper that accounts for
Castle overlays) so the preview correctly fetches Castle stats for
the overlay case.
"""
from __future__ import annotations

import pytest

import nevsky.actions  # noqa: F401 — register handlers first to avoid circular import
from nevsky.previews import storm_preview
from nevsky.scenarios import load_scenario


def _setup_castle_on_town(s, locale="ostrov", castle_side="teutonic_castle"):
    """Place a Castle marker on a Town locale, no Conquered."""
    setattr(s.locales[locale], castle_side, True)
    s.locales[locale].russian_conquered = 0
    s.locales[locale].teutonic_conquered = 0


def test_storm_preview_recognizes_teutonic_castle_on_town():
    """Castle-on-Town (Teutonic) should be stormable per Storm preview."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    _setup_castle_on_town(s, "ostrov", "teutonic_castle")
    # Put a Teutonic defender inside the Castle.
    hermann = s.lords["hermann"]
    hermann.state = "mustered"
    hermann.location = "ostrov"
    hermann.in_stronghold = True
    # Russian attacker outside, with forces.
    aleksandr = s.lords["aleksandr"]
    aleksandr.state = "mustered"
    aleksandr.location = "ostrov"
    aleksandr.in_stronghold = False
    s.locales["ostrov"].siege_markers = 1
    r = storm_preview(s, attacker_side="russian", attacker_lords=["aleksandr"], locale_id="ostrov", trials=2)
    assert "error" not in r, f"storm_preview rejected Castle-on-Town: {r.get('error')}"
    assert r["trials"] == 2
    assert r["walls_max"] >= 1


def test_storm_preview_recognizes_russian_castle_on_town():
    """Castle-on-Town (Russian) should be stormable from Teutonic side."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    _setup_castle_on_town(s, "ostrov", "russian_castle")
    # Russian defender inside, Teutonic attacker outside.
    aleksandr = s.lords["aleksandr"]
    aleksandr.state = "mustered"
    aleksandr.location = "ostrov"
    aleksandr.in_stronghold = True
    hermann = s.lords["hermann"]
    hermann.state = "mustered"
    hermann.location = "ostrov"
    hermann.in_stronghold = False
    s.locales["ostrov"].siege_markers = 1
    r = storm_preview(s, attacker_side="teutonic", attacker_lords=["hermann"], locale_id="ostrov", trials=2)
    assert "error" not in r, f"storm_preview rejected Castle-on-Town: {r.get('error')}"
    assert r["trials"] == 2
    assert r["walls_max"] >= 1


def test_storm_preview_still_rejects_plain_town_without_castle():
    """A plain Town with no Castle marker is NOT stormable."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    # ostrov has no Castle marker by default in the scenario.
    s.locales["ostrov"].teutonic_castle = False
    s.locales["ostrov"].russian_castle = False
    s.locales["ostrov"].siege_markers = 1
    r = storm_preview(s, attacker_side="teutonic", attacker_lords=["hermann"], locale_id="ostrov", trials=1)
    assert r.get("trials") == 0
    assert "error" in r


def test_storm_preview_still_rejects_trade_route():
    """trade_route returns no_storm per stronghold spec."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    # luga is a Russian trade_route
    s.locales["luga"].siege_markers = 1
    r = storm_preview(s, attacker_side="teutonic", attacker_lords=["hermann"], locale_id="luga", trials=1)
    assert r.get("trials") == 0
    assert "error" in r
    assert "Stormed" in r["error"] or "stormable" in r["error"]
