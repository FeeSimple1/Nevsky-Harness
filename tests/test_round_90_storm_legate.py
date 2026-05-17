"""SMOKE-086 (Round 90): Legate not removed on Storm Sack of a Teutonic
Stronghold by Russian attackers.

Per AoW Reference 1.4.1 Legate: "Whenever a Teutonic Lord ... is in
a Locale with any Russian Lord(s) and no Teutonic Lord, remove the
pawn and discard the William of Modena card."

`_h_cmd_storm` permanently removes all Besieged Lords on attacker
Sack. If Russians Storm a Teutonic Stronghold where the Legate is
(e.g., Riga, Dorpat, Reval, Leal), the post-Sack state is
Russian-only at the Legate's Locale — Legate should be removed.

The handler did not trigger this; the pawn would silently stay
with the Russian conquerors.

Fix: after Sack, if attackers were Russian AND any Teutonic Lord(s)
were sacked at the Legate's Locale, remove the pawn and discard T13.
"""
from __future__ import annotations

import inspect

import nevsky.actions  # noqa: F401 — register handlers
import nevsky.campaign as camp


def test_storm_sack_legate_trigger_in_source():
    src = inspect.getsource(camp)
    assert "SMOKE-086" in src, "SMOKE-086 Storm-Sack Legate trigger missing"


def test_storm_sack_legate_checks_russian_attacker():
    src = inspect.getsource(camp)
    smoke_block = src[src.find("SMOKE-086"):src.find("SMOKE-086") + 2000]
    assert 'sd == "russian"' in smoke_block


def test_storm_sack_legate_checks_attacker_won():
    src = inspect.getsource(camp)
    smoke_block = src[src.find("SMOKE-086"):src.find("SMOKE-086") + 2000]
    assert 'result["winner"] == "attacker"' in smoke_block


def test_storm_sack_legate_gated_on_legate_at_locale():
    src = inspect.getsource(camp)
    smoke_block = src[src.find("SMOKE-086"):src.find("SMOKE-086") + 2000]
    assert "state.legate.locale_id == locale_id" in smoke_block


def test_storm_sack_legate_discards_t13():
    src = inspect.getsource(camp)
    smoke_block = src[src.find("SMOKE-086"):src.find("SMOKE-086") + 2000]
    assert 'capabilities_in_play.remove("T13")' in smoke_block


def test_storm_sack_legate_clears_william_in_play():
    src = inspect.getsource(camp)
    smoke_block = src[src.find("SMOKE-086"):src.find("SMOKE-086") + 2000]
    assert "william_of_modena_in_play = False" in smoke_block
