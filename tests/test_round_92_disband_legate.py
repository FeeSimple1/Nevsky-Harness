"""SMOKE-088 (Round 92): `_disband_at_limit` didn't trigger Legate
auto-removal per 1.4.1.

Per AoW Reference 1.4.1: "a Teutonic Lord ... is in a Locale with
any Russian Lord(s) and no Teutonic Lord, remove the pawn and
discard the William of Modena card."

R91 (SMOKE-087) wired the check into `_remove_lord_permanently`
(3.3.1 path). The analogous `_disband_at_limit` (3.3.2 at-limit
Disband) sets `lord.location = None` but didn't trigger the
"Russian-only-at-Legate-locale" check. A Teutonic Lord Disbanded
in Feed/Pay/Disband at the Legate's Locale with Russian present
would leave the pawn behind.

Fix mirrors SMOKE-087: capture pre-disband location at function
entry, check the Legate auto-removal condition at the end.
"""
from __future__ import annotations

import inspect

import nevsky.actions as actions  # noqa: F401


def test_disband_at_limit_captures_pre_disband_location():
    src = inspect.getsource(actions._disband_at_limit)
    assert "_smoke088_disband_location" in src
    assert "SMOKE-088" in src


def test_disband_at_limit_legate_trigger_checks_teu_side():
    src = inspect.getsource(actions._disband_at_limit)
    smoke_block = src[src.find("SMOKE-088 (Round 92): Legate"):]
    assert '_smoke088_disband_side == "teutonic"' in smoke_block


def test_disband_at_limit_legate_trigger_checks_russian_present():
    src = inspect.getsource(actions._disband_at_limit)
    smoke_block = src[src.find("SMOKE-088 (Round 92): Legate"):]
    assert "rus_present" in smoke_block
    assert 'L.side == "russian"' in smoke_block


def test_disband_at_limit_legate_trigger_checks_no_teu_left():
    src = inspect.getsource(actions._disband_at_limit)
    smoke_block = src[src.find("SMOKE-088 (Round 92): Legate"):]
    assert "teu_left" in smoke_block
    assert "not teu_left" in smoke_block


def test_disband_at_limit_legate_discards_t13():
    src = inspect.getsource(actions._disband_at_limit)
    smoke_block = src[src.find("SMOKE-088 (Round 92): Legate"):]
    assert 'capabilities_in_play.remove("T13")' in smoke_block
    assert "william_of_modena_in_play = False" in smoke_block


def test_disband_at_limit_gated_on_legate_locale():
    src = inspect.getsource(actions._disband_at_limit)
    smoke_block = src[src.find("SMOKE-088 (Round 92): Legate"):]
    assert "state.legate.locale_id ==" in smoke_block
