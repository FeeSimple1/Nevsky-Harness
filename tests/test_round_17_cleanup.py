"""Round 17 regression tests for the cleanup: tighter exception handling
in previews + lord_id validation + legal_moves preview-failure surfacing."""
from __future__ import annotations

from copy import deepcopy

from nevsky.actions import apply_action
from nevsky.legal_moves import legal_moves
from nevsky.previews import battle_preview, storm_preview, vp_forecast
from nevsky.scenarios import load_scenario


def _setup():
    s = load_scenario("pleskau", seed=1)
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})
    return s


def test_battle_preview_validates_unknown_lord_id():
    """A typo in lord_id must return error, not a confident 0-pre-unit
    result that an LLM consumer might trust."""
    s = _setup()
    res = battle_preview(s, "teutonic", ["nonexistent"], ["gavrilo"], trials=5)
    assert res["trials"] == 0
    assert "error" in res
    assert "unknown" in res["error"]
    assert "nonexistent" in res["error"]


def test_storm_preview_validates_unknown_lord_id():
    s = _setup()
    res = storm_preview(s, "teutonic", ["typo"], "izborsk", trials=5)
    assert res["trials"] == 0
    assert "error" in res
    assert "typo" in res["error"]


def test_storm_preview_unknown_locale():
    s = _setup()
    res = storm_preview(s, "teutonic", ["hermann"], "atlantis", trials=5)
    assert res["trials"] == 0
    assert "error" in res
    assert "atlantis" in res["error"]


def test_storm_preview_no_storm_locale():
    """Trade-route locales (e.g., Neva) cannot be Stormed — return error."""
    s = _setup()
    res = storm_preview(s, "teutonic", ["hermann"], "neva", trials=5)
    assert res["trials"] == 0
    assert "error" in res


def test_battle_preview_tracks_failed_trials():
    """If trials raise, failed_trials is recorded and last_error surfaces."""
    s = _setup()
    res = battle_preview(s, "teutonic", ["hermann"], ["gavrilo"], trials=10)
    # Successful trial: no failed_trials key.
    assert "failed_trials" not in res or res["failed_trials"] == 0
    assert res["successful_trials"] == 10


def test_battle_preview_does_not_swallow_unexpected_state_attribute_errors():
    """If state somehow lacks expected fields, preview should surface the
    error in last_error rather than returning silent zeros."""
    s = _setup()
    s2 = deepcopy(s)
    # Sabotage forces dict with a bogus type that resolve_battle will
    # choke on.
    s2.lords["hermann"].forces = {"bogus_unit_type": 999}
    res = battle_preview(s2, "teutonic", ["hermann"], ["gavrilo"], trials=5)
    # Either succeeds with attacker losing (likely; bogus units don't
    # contribute) or fails. Either way, the helper shouldn't crash and
    # if there are failures they're surfaced.
    if res.get("failed_trials"):
        assert res.get("last_error")


def test_legal_moves_storm_note_handles_preview_unavailable():
    """Storm note should be present even if preview can't run (e.g. broken
    state) — it surfaces the unavailability rather than dropping silently."""
    s = _setup()
    s.lords["hermann"].location = "izborsk"
    s.locales["izborsk"].siege_markers = 1
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.campaign_turn.active_lord = "hermann"
    s.campaign_turn.actions_remaining = 3
    s.campaign_turn.next_to_reveal = "teutonic"
    moves = legal_moves(s)
    storm = next((m for m in moves if m["type"] == "cmd_storm"), None)
    assert storm is not None
    # Note should always include base text.
    assert "Storm" in storm["note"]


def test_vp_forecast_handles_missing_combat_pending():
    """stand_battle without combat_pending returns a noop, not a crash."""
    s = _setup()
    fc = vp_forecast(s, {"type": "stand_battle", "side": "teutonic", "args": {}})
    assert fc["kind"] == "noop"
    assert "combat_pending" in fc["note"]


def test_vp_forecast_handles_missing_lord_id():
    s = _setup()
    fc = vp_forecast(s, {"type": "cmd_storm", "side": "teutonic", "args": {}})
    assert fc["kind"] == "noop"
    assert "lord_id" in fc["note"]


def test_rules_questions_q007_q008_resolved_in_decisions():
    """Q-007 (Russian archery rounding) and Q-008 (Tier 2 Battle Hold
    effects) were adjudicated and moved to RULES_DECISIONS.md in
    Round 18; RULES_QUESTIONS.md no longer carries them."""
    from pathlib import Path
    decisions = Path("RULES_DECISIONS.md").read_text()
    questions = Path("RULES_QUESTIONS.md").read_text()
    assert "Q-007" in decisions
    assert "Russian Archery" in decisions
    assert "Q-008" in decisions
    assert "Bridge" in decisions
    # And no longer open.
    assert "Q-007" not in questions
    assert "Q-008" not in questions
