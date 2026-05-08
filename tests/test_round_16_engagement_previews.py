"""Round 16 regression tests for engagement previews + VP forecast."""
from __future__ import annotations

from nevsky.actions import apply_action
from nevsky.legal_moves import legal_moves
from nevsky.previews import battle_preview, storm_preview, vp_forecast
from nevsky.scenarios import load_scenario


def _setup():
    s = load_scenario("pleskau", seed=1)
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})
    return s


def test_battle_preview_balanced_1v1_defender_favored():
    """1v1 balanced parity should favor defender per Round 13 finding."""
    s = _setup()
    prev = battle_preview(s, "teutonic", ["hermann"], ["gavrilo"], trials=200)
    assert prev["trials"] == 200
    assert prev["defender_winrate"] > 0.55, (
        f"defender winrate {prev['defender_winrate']:.2%} weaker than expected"
    )
    assert 0 < prev["avg_rounds"] < 10
    # Sanity: per-side losses non-negative.
    assert prev["avg_attacker_units_lost"] >= 0
    assert prev["avg_defender_units_lost"] >= 0


def test_battle_preview_does_not_mutate_state():
    """The caller's state must be unchanged after a preview run."""
    s = _setup()
    pre_t = s.calendar.teutonic_vp
    pre_h_forces = dict(s.lords["hermann"].forces)
    pre_g_forces = dict(s.lords["gavrilo"].forces)
    battle_preview(s, "teutonic", ["hermann"], ["gavrilo"], trials=20)
    assert s.calendar.teutonic_vp == pre_t
    assert dict(s.lords["hermann"].forces) == pre_h_forces
    assert dict(s.lords["gavrilo"].forces) == pre_g_forces


def test_storm_preview_fort_one_attacker_one_marker():
    """Hermann (4 units) Storming Izborsk (Fort, walls 3, 1 garrison MaA)
    with 1 siege marker should win comfortably per smoke."""
    s = _setup()
    s.lords["hermann"].location = "izborsk"
    s.locales["izborsk"].siege_markers = 1
    prev = storm_preview(s, "teutonic", ["hermann"], "izborsk", trials=200)
    assert prev["trials"] == 200
    assert prev["attacker_winrate"] >= 0.6
    assert prev["stronghold_type"] == "fort"
    assert prev["walls_max"] == 3
    assert prev["siege_markers"] == 1
    assert prev["stronghold_vp"] == 1


def test_storm_preview_does_not_mutate_state():
    s = _setup()
    s.lords["hermann"].location = "izborsk"
    s.locales["izborsk"].siege_markers = 1
    pre_loc = s.lords["hermann"].location
    pre_sm = s.locales["izborsk"].siege_markers
    pre_forces = dict(s.lords["hermann"].forces)
    storm_preview(s, "teutonic", ["hermann"], "izborsk", trials=20)
    assert s.lords["hermann"].location == pre_loc
    assert s.locales["izborsk"].siege_markers == pre_sm
    assert dict(s.lords["hermann"].forces) == pre_forces


def test_vp_forecast_cmd_ravage_deterministic():
    s = _setup()
    fc = vp_forecast(s, {"type": "cmd_ravage", "side": "russian",
                          "args": {"locale_id": "vod"}})
    assert fc["kind"] == "deterministic"
    assert fc["attacker_vp_delta"] == 0.5
    assert "Ravage" in fc["note"]


def test_vp_forecast_cmd_storm_probabilistic():
    s = _setup()
    s.lords["hermann"].location = "izborsk"
    s.locales["izborsk"].siege_markers = 1
    fc = vp_forecast(s, {"type": "cmd_storm", "side": "teutonic",
                          "args": {"lord_id": "hermann"}}, preview_trials=30)
    assert fc["kind"] == "probabilistic"
    # Expected VP delta should be positive and < the stronghold VP (=1).
    assert 0 < fc["attacker_vp_delta"] <= 1.0
    assert fc["preview"] is not None
    assert "A_win" in fc["note"]


def test_vp_forecast_cmd_pass_noop():
    s = _setup()
    fc = vp_forecast(s, {"type": "cmd_pass", "side": "teutonic",
                          "args": {"lord_id": "hermann"}})
    assert fc["kind"] == "noop"
    assert fc["attacker_vp_delta"] == 0.0


def test_legal_moves_cmd_storm_note_includes_preview():
    """When Storm is a legal action, its note should embed the preview
    so the LLM consumer can read win-prob + VP + losses inline."""
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
    assert storm is not None, "no cmd_storm option emitted"
    note = storm.get("note", "")
    assert "A_win" in note
    assert "VP" in note
    assert "A_loss" in note
