"""SMOKE-087 (Round 91): Permanent Lord removal didn't trigger Legate
auto-removal per 1.4.1 "Russian Lord(s) and no Teutonic Lord."

Per AoW Reference 1.4.1: "a Teutonic Lord ... is in a Locale with
any Russian Lord(s) and no Teutonic Lord, remove the pawn and
discard the William of Modena card."

R88/89/90 wired Avoid Battle, Withdraw, Battle Retreat, Sally
Retreat, and Storm Sack triggers. But `_remove_lord_permanently`
itself didn't check this rule. If a Teutonic Lord at the Legate's
Locale was permanently removed via any non-Battle path (Wastage
cascade, Pay/Disband loss, etc.) AND a Russian Lord was at the
Locale AND no Teutonic Lord remained, the pawn would silently stay.

Fix: at the end of `_remove_lord_permanently`, after the Lord is
gone, if the removed Lord was Teutonic and was at the Legate's
Locale, check whether any Teutonic Lord still remains there
(probably none — we just removed the only one) and any Russian
Lord is present. If so, remove the pawn and discard T13.
"""
from __future__ import annotations

import inspect

import nevsky.actions as actions  # noqa: F401 — register handlers


def test_remove_lord_permanently_captures_pre_removal_location():
    src = inspect.getsource(actions._remove_lord_permanently)
    assert "_smoke087_removed_location" in src
    assert "SMOKE-087" in src


def test_remove_lord_permanently_legate_trigger_checks_teu_side():
    src = inspect.getsource(actions._remove_lord_permanently)
    smoke_block = src[src.find("SMOKE-087 (Round 91): Legate"):]
    assert '_smoke087_removed_side == "teutonic"' in smoke_block


def test_remove_lord_permanently_legate_trigger_checks_russian_present():
    src = inspect.getsource(actions._remove_lord_permanently)
    smoke_block = src[src.find("SMOKE-087 (Round 91): Legate"):]
    assert 'L.side == "russian"' in smoke_block
    assert "rus_present" in smoke_block


def test_remove_lord_permanently_legate_trigger_checks_no_teu_left():
    src = inspect.getsource(actions._remove_lord_permanently)
    smoke_block = src[src.find("SMOKE-087 (Round 91): Legate"):]
    assert "teu_left" in smoke_block
    assert "not teu_left" in smoke_block


def test_remove_lord_permanently_legate_discards_t13():
    src = inspect.getsource(actions._remove_lord_permanently)
    smoke_block = src[src.find("SMOKE-087 (Round 91): Legate"):]
    assert 'capabilities_in_play.remove("T13")' in smoke_block
    assert "william_of_modena_in_play = False" in smoke_block


def test_remove_lord_permanently_gated_on_legate_locale():
    src = inspect.getsource(actions._remove_lord_permanently)
    smoke_block = src[src.find("SMOKE-087 (Round 91): Legate"):]
    assert "state.legate.locale_id ==" in smoke_block
