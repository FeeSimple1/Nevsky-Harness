"""SMOKE-122 (Round 188): legal_moves cmd_ravage over-enumeration.

The legal_moves enumerator was offering cmd_ravage unconditionally
in the command-execution block, but _h_cmd_ravage (campaign.py
4.7.2) rejects it when any of these hold:

- Locale is own territory
- Locale is already Conquered (either color)
- Locale is Friendly to the active side
- Locale is already Ravaged (either color)

Surfaced during the Round 188 LLM-interface playthrough: the LLM
agent burned retry slots on "Cannot Ravage own territory (...)"
errors. Same family as SMOKE-118 (levy_capability filters) and
SMOKE-120 (R16 no-op).

Found via docs/llm_interface_playthrough.md (Pleskau scenario).
"""
from __future__ import annotations

import nevsky.actions  # noqa: F401
from nevsky.campaign import _is_friendly_locale
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import load_scenario
from nevsky.static_data import load_locales


def _setup_command_exec(s, side: str, active_lord: str) -> None:
    """Place state at command-execution step with an active Lord."""
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = side
    s.campaign_turn.active_lord = active_lord
    s.campaign_turn.actions_remaining = 2
    s.campaign_turn.in_feed_pay_disband = False


# ----- SMOKE-122 -----------------------------------------------------------


def test_smoke_122_no_ravage_at_own_seat():
    """A Teutonic Lord at his own teutonic-territory Seat (fellin)
    must NOT be offered cmd_ravage."""
    s = load_scenario("watland", seed=1)
    _setup_command_exec(s, "teutonic", "andreas")
    assert s.lords["andreas"].location == "fellin"
    moves = legal_moves(s, with_previews=False)
    ravage = [m for m in moves if m.get("type") == "cmd_ravage"]
    assert ravage == [], (
        f"legal_moves offers cmd_ravage at own territory (fellin); "
        f"_h_cmd_ravage would raise own_territory: {ravage}"
    )


def test_smoke_122_no_ravage_at_own_territory_russian():
    """A Russian Lord at a russian-territory Locale (novgorod) must
    NOT be offered cmd_ravage."""
    s = load_scenario("watland", seed=1)
    _setup_command_exec(s, "russian", "domash")
    assert s.lords["domash"].location == "novgorod"
    moves = legal_moves(s, with_previews=False)
    ravage = [m for m in moves if m.get("type") == "cmd_ravage"]
    assert ravage == [], (
        f"legal_moves offers cmd_ravage at own russian territory "
        f"(novgorod): {ravage}"
    )


def test_smoke_122_no_ravage_at_already_ravaged_locale():
    """Pskov starts watland already teu-conquered+ravaged. The
    Teutonic Lord (yaroslav) standing on it must NOT be offered
    cmd_ravage (would raise already_ravaged / conquered / friendly)."""
    s = load_scenario("watland", seed=1)
    _setup_command_exec(s, "teutonic", "yaroslav")
    assert s.lords["yaroslav"].location == "pskov"
    # Confirm fixture preconditions actually hold.
    assert s.locales["pskov"].teutonic_ravaged is True
    moves = legal_moves(s, with_previews=False)
    ravage = [m for m in moves if m.get("type") == "cmd_ravage"]
    assert ravage == [], (
        f"legal_moves offers cmd_ravage at already-ravaged pskov: "
        f"{ravage}"
    )


def test_smoke_122_offers_ravage_at_legitimate_enemy_locale():
    """Positive control: a Teutonic Lord moved onto an enemy
    russian-territory Locale that is neither conquered, ravaged,
    nor friendly SHOULD be offered cmd_ravage."""
    s = load_scenario("watland", seed=1)
    # Luga is russian territory, unconquered, unravaged, not friendly
    # to Teutonic in watland's starting state.
    s.lords["andreas"].location = "luga"
    _setup_command_exec(s, "teutonic", "andreas")
    # Belt-and-braces precondition check.
    locs = load_locales()
    assert locs["luga"]["territory"] == "russian"
    assert s.locales["luga"].russian_conquered == 0
    assert s.locales["luga"].teutonic_conquered == 0
    assert not s.locales["luga"].russian_ravaged
    assert not s.locales["luga"].teutonic_ravaged
    assert not _is_friendly_locale(s, "luga", "teutonic")
    moves = legal_moves(s, with_previews=False)
    ravage = [m for m in moves if m.get("type") == "cmd_ravage"]
    assert len(ravage) == 1, (
        f"legal_moves should offer cmd_ravage for andreas at luga "
        f"(enemy, not conq/rav/friendly); got {ravage}"
    )
    assert ravage[0]["args"]["lord_id"] == "andreas"
    assert ravage[0]["args"]["locale_id"] == "luga"


def test_smoke_122_marker_present_in_source():
    """Source-level regression: the SMOKE-122 marker must remain in
    legal_moves.py so a future refactor doesn't silently drop the
    filter."""
    import inspect
    import nevsky.legal_moves as lm
    src = inspect.getsource(lm)
    assert "SMOKE-122" in src, "SMOKE-122 marker missing from legal_moves.py"
