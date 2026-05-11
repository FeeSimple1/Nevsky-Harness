"""Round 36 — VP-credit pathways must reach calendar.teutonic_vp /
russian_vp, the floats that determine_scenario_winner reads.

Bugs found:

  SMOKE-022 — VP track markers set once at scenario load; never
  refreshed during play. After conquest/liberation/ravage/etc., the
  calendar box markers diverged from the source-of-truth floats.

  SMOKE-023 — Stonemasons (T17) placed teutonic_castle marker but did
  not increment calendar.teutonic_vp. Castle marker contributes +1 VP
  per Strongholds reference, but determine_scenario_winner missed it.

  SMOKE-024 — Pleskau Lord-removed bonus incremented
  calendar.pleskau_lords_removed_* counters but not the side's
  calendar.*_vp float. The +1 VP per enemy Lord removed (Pleskau
  scenario only) never reached determine_scenario_winner. With a
  pre-fix Pleskau game where T removed 2 R lords, T's VP showed 0;
  R won the scenario despite the rules giving T a 2-VP swing.
"""
from __future__ import annotations

from nevsky.actions import apply_action, _remove_lord_permanently
from nevsky.scenarios import (
    load_scenario, determine_scenario_winner, refresh_victory_markers,
)
from nevsky.static_data import load_lords


def _setup_campaign():
    s = load_scenario("crusade_on_novgorod", seed=1)
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.box = 1
    return s


def _vp_marker_box(s, side):
    attr = f"{side}_victory_marker"
    for i, cb in enumerate(s.calendar.boxes):
        if getattr(cb, attr):
            return i + 1
    return None


# ---------- SMOKE-022: VP markers refresh ----------

def test_vp_marker_refreshes_after_storm_conquest():
    s = _setup_campaign()
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].location = "kaibolovo"
    s.lords[teu].in_stronghold = False
    s.lords[teu].forces = {"knights": 5, "men_at_arms": 5}
    s.locales["kaibolovo"].siege_markers = 1
    s.meta.active_player = "teutonic"
    s.campaign_turn.active_lord = teu
    s.campaign_turn.actions_remaining = 3
    s.campaign_turn.in_feed_pay_disband = False

    res = apply_action(s, {"type": "cmd_storm", "side": "teutonic", "args": {"lord_id": teu}})
    # T gained 1 VP from Fort conquest; marker must be at box 1.
    assert s.calendar.teutonic_vp == 1.0
    assert _vp_marker_box(s, "teutonic") == 1


def test_vp_marker_refreshes_after_ravage():
    s = _setup_campaign()
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].location = "gdov"
    s.lords[teu].in_stronghold = False
    s.lords[teu].forces = {"knights": 3}
    s.meta.active_player = "teutonic"
    s.campaign_turn.active_lord = teu
    s.campaign_turn.actions_remaining = 3
    s.campaign_turn.in_feed_pay_disband = False
    pre_marker = _vp_marker_box(s, "teutonic")
    res = apply_action(s, {"type": "cmd_ravage", "side": "teutonic", "args": {"lord_id": teu}})
    # +0.5 VP for Ravage marker.
    assert s.calendar.teutonic_vp == 0.5
    # 0.5 is below the integer threshold; marker stays None.
    assert _vp_marker_box(s, "teutonic") is None


def test_refresh_victory_markers_is_idempotent():
    """Calling refresh multiple times must not produce duplicate markers."""
    s = _setup_campaign()
    s.calendar.teutonic_vp = 3.0
    refresh_victory_markers(s)
    refresh_victory_markers(s)
    refresh_victory_markers(s)
    count = sum(1 for b in s.calendar.boxes if b.teutonic_victory_marker)
    assert count == 1, f"got {count} markers, expected 1"


# ---------- SMOKE-023: Stonemasons VP ----------

def test_stonemasons_grants_castle_vp_to_calendar_float():
    s = _setup_campaign()
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].this_lord_capabilities = ["T17"]
    s.lords[teu].location = "kaibolovo"  # Russian Fort
    s.lords[teu].assets["provender"] = 6
    s.meta.active_player = "teutonic"
    s.campaign_turn.active_lord = teu
    from nevsky.campaign import _effective_command_rating
    s.campaign_turn.actions_remaining = _effective_command_rating(s, teu)
    s.campaign_turn.in_feed_pay_disband = False
    pre_vp = s.calendar.teutonic_vp

    res = apply_action(s, {"type": "cmd_stonemasons", "side": "teutonic", "args": {"lord_id": teu}})
    assert s.locales["kaibolovo"].teutonic_castle is True
    # Castle marker contributes +1 VP per Strongholds reference.
    assert s.calendar.teutonic_vp == pre_vp + 1.0, (
        f"Stonemasons should grant +1 VP; T_vp pre={pre_vp}, post={s.calendar.teutonic_vp}"
    )


# ---------- SMOKE-024: Pleskau Lord-removed bonus ----------

def test_pleskau_lord_removed_reaches_winner_determination():
    """In Pleskau, removing an enemy Lord grants +1 VP. Pre-fix this
    only reached _compute_vp (re-derived from markers) but NOT
    calendar.teutonic_vp (the float winner determination reads)."""
    s = load_scenario("pleskau", seed=1)
    assert s.meta.special_rules.get("victory_lord_removed_bonus"), (
        "Pleskau should have victory_lord_removed_bonus set"
    )
    russ_lords = [lid for lid, l in s.lords.items()
                  if l.side == "russian" and l.state == "mustered"]
    pre_t_vp = s.calendar.teutonic_vp
    # Remove 2 R Lords.
    for lid in russ_lords[:2]:
        _remove_lord_permanently(s, lid, load_lords()[lid])
    # T gains +2 VP per Pleskau bonus.
    assert s.calendar.teutonic_vp == pre_t_vp + 2.0, (
        f"T VP should be {pre_t_vp + 2.0}, got {s.calendar.teutonic_vp}"
    )
    # Verify scenario winner correctly sees T's lead.
    winner = determine_scenario_winner(s)
    assert winner["t_vp"] == pre_t_vp + 2.0


def test_pleskau_lord_removed_only_fires_when_special_rule_set():
    """In non-Pleskau scenarios, victory_lord_removed_bonus is False
    and Lord removal should NOT add VP."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    assert not s.meta.special_rules.get("victory_lord_removed_bonus", False)
    pre_t_vp = s.calendar.teutonic_vp
    russ_lords = [lid for lid, l in s.lords.items()
                  if l.side == "russian" and l.state == "mustered"]
    _remove_lord_permanently(s, russ_lords[0], load_lords()[russ_lords[0]])
    assert s.calendar.teutonic_vp == pre_t_vp, (
        f"Non-Pleskau Lord removal should not change VP; pre={pre_t_vp}, "
        f"post={s.calendar.teutonic_vp}"
    )
