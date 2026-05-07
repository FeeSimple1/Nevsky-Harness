"""Tests for legal_moves enumeration."""

from __future__ import annotations

from nevsky.legal_moves import legal_moves
from nevsky.scenarios import load_scenario


def test_legal_moves_advance_step_always_present() -> None:
    s = load_scenario("watland", seed=42)
    moves = legal_moves(s)
    assert any(m["type"] == "advance_step" and m["side"] == "teutonic" for m in moves)


def test_legal_moves_aow_step_offers_shuffle_or_draw() -> None:
    s = load_scenario("watland", seed=42)
    types = {m["type"] for m in legal_moves(s)}
    assert "aow_shuffle" in types or "aow_draw" in types


def test_legal_moves_pay_step_offers_pay_options_when_assets_present() -> None:
    s = load_scenario("watland", seed=42)
    s.meta.levy_step = "pay"
    s.meta.active_player = "teutonic"
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].assets["coin"] = 2
    types = {m["type"] for m in legal_moves(s)}
    assert "pay_with_coin" in types


def test_legal_moves_call_to_arms_t_offers_legate_options_when_william_in_play() -> None:
    s = load_scenario("watland", seed=42)
    s.meta.levy_step = "call_to_arms"
    s.meta.active_player = "teutonic"
    s.legate.william_of_modena_in_play = True
    s.legate.location = "card"
    types = {m["type"] for m in legal_moves(s)}
    assert "legate_arrives" in types


def test_legal_moves_call_to_arms_r_offers_veche_actions_when_vp_in_box() -> None:
    s = load_scenario("watland", seed=42)
    s.meta.levy_step = "call_to_arms"
    s.meta.active_player = "russian"
    s.meta.levy_step_completed_t = True
    s.veche.vp_markers = 1
    moves = legal_moves(s)
    veche_options = {
        m["args"].get("option") if "args" in m else m.get("args_template", {}).get("option")
        for m in moves if m["type"] == "veche_action"
    }
    # At least D ('decline') is offered; A/B/C only when targets exist.
    assert veche_options  # non-empty


def test_legal_moves_empty_when_not_levy_phase() -> None:
    s = load_scenario("watland", seed=42)
    s.meta.phase = "campaign"
    assert legal_moves(s) == []
