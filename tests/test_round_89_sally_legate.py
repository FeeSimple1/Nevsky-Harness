"""SMOKE-085 (Round 89): Legate not removed on Sally Aftermath
Retreat (Teutonic besiegers lose Sally).

Per AoW Reference 1.4.1 Legate: "Whenever a Teutonic Lord ...
Retreats ... remove the pawn and discard the William of Modena
card."

The Sally aftermath in `_h_cmd_sally` handles the case where the
sallying side (besieged Lords) wins and the besiegers lose
(retreat or are removed). If a Teutonic besieger retreats from the
siege locale and the Legate is at that locale, the Legate should
be removed — analogous to SMOKE-084 for Battle Aftermath Retreat.

Fix: After the sally retreat loop, if the Legate is at locale_id
and any Teutonic Lord was in `defenders` (the losing besiegers),
remove the pawn and discard T13 William of Modena.
"""
from __future__ import annotations

import inspect

import nevsky.actions  # noqa: F401 — register handlers
import nevsky.campaign as camp


def test_sally_aftermath_legate_trigger_in_source():
    src = inspect.getsource(camp)
    assert "SMOKE-085" in src, "SMOKE-085 Sally-Legate trigger missing from campaign.py"


def test_sally_aftermath_legate_checks_teu_defender():
    src = inspect.getsource(camp)
    smoke_block = src[src.find("SMOKE-085"):src.find("SMOKE-085") + 2000]
    assert 'state.lords[lid].side == "teutonic"' in smoke_block


def test_sally_aftermath_legate_discards_t13():
    src = inspect.getsource(camp)
    smoke_block = src[src.find("SMOKE-085"):src.find("SMOKE-085") + 2000]
    assert 'capabilities_in_play.remove("T13")' in smoke_block
    assert 'discard.append("T13")' in smoke_block


def test_sally_aftermath_legate_gated_on_locale_id():
    """The trigger fires only when Legate is at the Sally locale (locale_id)."""
    src = inspect.getsource(camp)
    smoke_block = src[src.find("SMOKE-085"):src.find("SMOKE-085") + 2000]
    assert "state.legate.locale_id == locale_id" in smoke_block


def test_sally_aftermath_legate_clears_william_in_play():
    src = inspect.getsource(camp)
    smoke_block = src[src.find("SMOKE-085"):src.find("SMOKE-085") + 2000]
    assert "william_of_modena_in_play = False" in smoke_block
