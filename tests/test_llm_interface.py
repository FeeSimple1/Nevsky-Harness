"""Tests for the nevsky.llm interface.

Covers:
  - view_for_side hides opponent holds/pending_draw/plan
  - briefing renders for both sides, stays under ~5 KB
  - legal_actions_for_side returns nothing when off-turn
  - LLMSession lifecycle (start, apply, save/load, terminal)
  - lookup tools (card / strategy / AoW reference)
  - preview_combat is gated by human_requested
  - safe fallback per phase
  - review artifact structure
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import nevsky.actions  # noqa: F401
import pytest
from nevsky.actions import IllegalAction
from nevsky.llm.briefing import briefing_for_side
from nevsky.llm.review import build_review_artifact, review_prompt_for_llm
from nevsky.llm.session import LLMSession
from nevsky.llm.tools import (legal_actions_for_side, lookup_aow_reference,
                              lookup_card, lookup_strategy, preview_combat,
                              safe_fallback_for_side)
from nevsky.llm.view import own_decks, view_for_side
from nevsky.scenarios import load_scenario


# ---------- view_for_side ---------------------------------------------------


def test_view_masks_opponent_holds():
    s = load_scenario("watland", seed=1)
    # Put a card in russian holds
    s.decks.russian.holds.append("R1")
    v = view_for_side(s, "teutonic")
    assert "<hidden>" in v["decks"]["russian"]["holds"]
    assert "R1" not in v["decks"]["russian"]["holds"]


def test_view_masks_opponent_pending_draw():
    s = load_scenario("watland", seed=1)
    s.decks.russian.pending_draw = ["R3", "R5"]
    v = view_for_side(s, "teutonic")
    assert v["decks"]["russian"]["pending_draw"] == ["<hidden>", "<hidden>"]
    assert "R3" not in v["decks"]["russian"]["pending_draw"]


def test_view_masks_opponent_plan():
    s = load_scenario("watland", seed=1)
    s.decks.russian.plan = ["domash", "andrey", "pass"]
    v = view_for_side(s, "teutonic")
    assert v["decks"]["russian"]["plan"] == ["<hidden>"] * 3


def test_view_preserves_own_holds():
    s = load_scenario("watland", seed=1)
    s.decks.teutonic.holds.append("T6")
    v = view_for_side(s, "teutonic")
    assert "T6" in v["decks"]["teutonic"]["holds"]


def test_view_preserves_public_state():
    """Capabilities in play, locale markers, lord positions are public."""
    s = load_scenario("watland", seed=1)
    s.decks.russian.capabilities_in_play = ["R8", "R10"]
    v = view_for_side(s, "teutonic")
    assert v["decks"]["russian"]["capabilities_in_play"] == ["R8", "R10"]
    # Locales are public
    assert "locales" in v
    # Lords are public (positions, forces, etc.)
    assert "lords" in v


def test_own_decks_returns_unfiltered_own_state():
    s = load_scenario("watland", seed=1)
    s.decks.teutonic.holds.append("T4")
    s.decks.teutonic.pending_draw.append("T1")
    d = own_decks(s, "teutonic")
    assert "T4" in d["holds"]
    assert "T1" in d["pending_draw"]


# ---------- briefing --------------------------------------------------------


def test_briefing_renders_for_teutonic():
    s = load_scenario("watland", seed=1)
    b = briefing_for_side(s, "teutonic")
    assert "you play TEUTONIC" in b
    assert "Phase" in b
    assert "Victory Points" in b
    assert "Your Lords (teutonic)" in b
    assert "Opponent Lords (russian)" in b


def test_briefing_renders_for_russian():
    s = load_scenario("crusade_on_novgorod", seed=1)
    b = briefing_for_side(s, "russian")
    assert "you play RUSSIAN" in b
    assert "Your Lords (russian)" in b
    assert "Opponent Lords (teutonic)" in b


def test_briefing_size_reasonable():
    """Briefing should stay under 5 KB for token-budget friendliness."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    b = briefing_for_side(s, "teutonic")
    assert len(b) < 5000, f"briefing is {len(b)} chars; expected < 5000"


def test_briefing_includes_combat_pending_when_set():
    """When combat_pending exists, briefing surfaces it."""
    s = load_scenario("watland", seed=1)
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "russian"
    from nevsky.state import CombatPending
    s.combat_pending = CombatPending(
        attacker_side="teutonic",
        attacker_group=["andreas"],
        from_locale="fellin",
        to_locale="pskov",
        way_type="trackway",
        defender_side="russian",
        defender_lords=["yaroslav"],
        pending_response_by="russian",
        laden=False,
    )
    b = briefing_for_side(s, "russian")
    assert "COMBAT PENDING" in b
    assert "pskov" in b


# ---------- legal_actions_for_side ----------------------------------------


def test_legal_actions_empty_when_off_turn():
    s = load_scenario("watland", seed=1)
    s.meta.active_player = "teutonic"
    moves = legal_actions_for_side(s, "russian")
    assert moves == []


def test_legal_actions_returns_when_on_turn():
    s = load_scenario("watland", seed=1)
    s.meta.active_player = "teutonic"
    moves = legal_actions_for_side(s, "teutonic")
    assert len(moves) > 0


# ---------- LLMSession lifecycle -------------------------------------------


def test_session_start_new_teutonic():
    s = LLMSession.start_new("watland", llm_side="teutonic", seed=1)
    assert s.llm_side == "teutonic"
    assert s.human_side == "russian"
    assert s.scenario_id == "watland"
    assert not s.is_terminal()
    assert s.whose_turn() in ("llm", "human")


def test_session_start_random_side():
    import random
    random.seed(42)
    s = LLMSession.start_new("pleskau", randomize_side=True, seed=1)
    assert s.llm_side in ("teutonic", "russian")


def test_session_rejects_unknown_scenario():
    with pytest.raises(ValueError):
        LLMSession.start_new("quickstart", llm_side="teutonic", seed=1)


def test_session_rejects_wrong_side_action():
    s = LLMSession.start_new("watland", llm_side="teutonic", seed=1)
    s.state.meta.active_player = "russian"  # russian's turn
    # LLM is teutonic; try to apply as llm anyway with their own side
    # The session enforces by setting action["side"] = llm_side by default
    # The harness will reject for wrong_actor based on active_player
    with pytest.raises(IllegalAction):
        s.apply({"type": "advance_step", "args": {}}, who="llm")


def test_session_apply_records_history():
    s = LLMSession.start_new("watland", llm_side="teutonic", seed=1)
    # Advance step (legal move for active player)
    s.apply({"type": "advance_step", "args": {}}, who="llm",
            reasoning="finishing AoW step")
    assert len(s.history) == 1
    assert s.history[0]["who"] == "llm"
    assert s.history[0]["reasoning"] == "finishing AoW step"


def test_session_save_and_load_round_trip():
    s = LLMSession.start_new("watland", llm_side="teutonic", seed=1)
    s.apply({"type": "advance_step", "args": {}}, who="llm")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    try:
        s.save(path)
        s2 = LLMSession.load(path)
        assert s2.llm_side == s.llm_side
        assert s2.scenario_id == s.scenario_id
        assert len(s2.history) == 1
        # State should round-trip
        assert s2.state.model_dump_json() == s.state.model_dump_json()
    finally:
        Path(path).unlink(missing_ok=True)


# ---------- lookup tools --------------------------------------------------


def test_lookup_card_returns_structured_data():
    c = lookup_card("T17")
    assert c["card_id"] == "T17"
    assert c["capability_name"] == "Stonemasons"


def test_lookup_card_unknown_returns_error():
    c = lookup_card("ZZZ")
    assert "error" in c


def test_lookup_strategy_finds_section():
    s = lookup_strategy("Pleskau")
    assert "Pleskau" in s
    assert len(s) > 100


def test_lookup_strategy_returns_headers_on_miss():
    s = lookup_strategy("nonexistent topic xyz")
    assert "No section" in s


def test_lookup_aow_reference_finds_card():
    s = lookup_aow_reference("T11")
    assert "T11" in s
    assert len(s) > 50


# ---------- preview_combat gating ------------------------------------------


def test_preview_combat_blocked_without_human_request():
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items()
               if l.side == "teutonic" and l.state == "mustered")
    rus = next(lid for lid, l in s.lords.items()
               if l.side == "russian" and l.state == "mustered")
    r = preview_combat(s, attacker_side="teutonic",
                        attacker_lords=[teu], defender_lords=[rus],
                        human_requested=False)
    assert r.get("preview_blocked") is True


def test_preview_combat_runs_with_human_request():
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items()
               if l.side == "teutonic" and l.state == "mustered")
    rus = next(lid for lid, l in s.lords.items()
               if l.side == "russian" and l.state == "mustered")
    r = preview_combat(s, attacker_side="teutonic",
                        attacker_lords=[teu], defender_lords=[rus],
                        human_requested=True)
    assert "samples" in r
    assert "attacker_win_pct" in r


# ---------- safe_fallback_for_side ----------------------------------------


def test_safe_fallback_levy_returns_advance_step():
    s = load_scenario("watland", seed=1)
    s.meta.phase = "levy"
    s.meta.levy_step = "arts_of_war"
    fb = safe_fallback_for_side(s, "teutonic")
    assert fb["type"] == "advance_step"


def test_safe_fallback_cta_teutonic_returns_legate_skip():
    s = load_scenario("watland", seed=1)
    s.meta.phase = "levy"
    s.meta.levy_step = "call_to_arms"
    fb = safe_fallback_for_side(s, "teutonic")
    assert fb["type"] == "legate_skip"


def test_safe_fallback_plan_returns_pass_card():
    s = load_scenario("watland", seed=1)
    s.meta.phase = "campaign"
    s.meta.campaign_step = "plan"
    fb = safe_fallback_for_side(s, "teutonic")
    assert fb["type"] == "plan_add_card"
    assert fb["args"]["card"] == "pass"


# ---------- review artifact -----------------------------------------------


def test_review_artifact_structure():
    s = LLMSession.start_new("watland", llm_side="teutonic", seed=1)
    s.apply({"type": "advance_step", "args": {}}, who="llm",
            reasoning="finishing AoW step")
    art = build_review_artifact(s)
    assert art["scenario"] == "watland"
    assert art["llm_side"] == "teutonic"
    assert art["total_actions"] == 1
    assert "advance_step" in art["action_counts"]
    assert len(art["llm_reasoning_log"]) == 1


def test_review_prompt_includes_reflection_questions():
    s = LLMSession.start_new("watland", llm_side="teutonic", seed=1)
    prompt = review_prompt_for_llm(s)
    assert "Reflection prompts" in prompt
    assert "strategic plan" in prompt
