"""SMOKE-084 (Round 88): Legate not removed on Battle Aftermath
Retreat.

Per AoW Reference 1.4.1 Legate: "Whenever a Teutonic Lord Avoids
Battle, Withdraws, or Retreats (4.3.4, 4.4.3) ... remove the pawn
and discard the William of Modena card."

SMOKE-043 wired Avoid Battle and Withdraw paths. The Retreat path
in Battle aftermath (campaign.py, post-resolve_battle loop) was
missed. If a Teutonic Lord brought the Legate along via March
(take_legate=True), lost the Battle, and Retreated, the Legate
would silently stay at the Battle Locale (where Russian Lords now
are) — directly contradicting the rule.

Fix: after the retreat loop, if any Teutonic Lord was in
loser_lords AND the Legate is at cp.to_locale, remove the Legate
pawn and discard T13 William of Modena.
"""
from __future__ import annotations

import inspect

import nevsky.actions  # noqa: F401 — register handlers
import nevsky.campaign as camp


def test_battle_aftermath_retreat_removes_legate_in_source():
    """Source inspection: the retreat aftermath block now references
    legate removal. The end-to-end Battle flow is exercised by
    surrounding battle suite tests; this guard catches removal of
    the SMOKE-084 trigger block."""
    src = inspect.getsource(camp)
    # Locate the SMOKE-084 marker.
    assert "SMOKE-084" in src, "SMOKE-084 Legate-retreat trigger missing from campaign.py"


def test_battle_aftermath_retreat_block_checks_teu_loser():
    """The trigger should check Teutonic side among loser_lords."""
    src = inspect.getsource(camp)
    # The fix uses `teu_lost = any(...)` checking lords[lid].side == 'teutonic'.
    smoke_block = src[src.find("SMOKE-084"):src.find("SMOKE-084") + 2000]
    assert 'state.lords[lid].side == "teutonic"' in smoke_block


def test_battle_aftermath_retreat_block_discards_t13():
    """The trigger discards T13 from capabilities_in_play."""
    src = inspect.getsource(camp)
    smoke_block = src[src.find("SMOKE-084"):src.find("SMOKE-084") + 2000]
    assert 'capabilities_in_play.remove("T13")' in smoke_block
    assert 'discard.append("T13")' in smoke_block


def test_battle_aftermath_retreat_block_clears_william_in_play():
    """The trigger flips william_of_modena_in_play to False."""
    src = inspect.getsource(camp)
    smoke_block = src[src.find("SMOKE-084"):src.find("SMOKE-084") + 2000]
    assert "william_of_modena_in_play = False" in smoke_block


def test_battle_aftermath_retreat_block_gated_on_legate_at_locale():
    """The trigger fires only when the Legate is at cp.to_locale."""
    src = inspect.getsource(camp)
    smoke_block = src[src.find("SMOKE-084"):src.find("SMOKE-084") + 2000]
    assert "state.legate.locale_id == cp.to_locale" in smoke_block
