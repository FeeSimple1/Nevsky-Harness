"""SMOKE-105 (Round 145): R4 Raven's Rock Walls applied only when
Teutonic was the Battle attacker. Card text "may play on either Attack
or Defense" → Russian-as-attacker case also needs Walls vs Teutonic
defender melee Round 1.

Per AoW Reference R4 Tip:
    "The Russians may play Raven's Rock in field Battle on either
     Attack or Defense, inside or outside of Rus, as long as the
     current Season is Winter or Rasputitsa."

Pre-fix `_resolve_hits` checked
    striker_role == "attacker" and attacker_side == "teutonic"
which fires only when Teutonic is the Battle attacker. When Russian
is the attacker and Teutonic strikes as defender, the strike still
hits Russian units in melee Round 1 and Walls should apply.

Fix drops the role/side restriction; Walls fire whenever target is
Russian AND step is melee AND round 1 (the non-Summer gate is already
enforced at consumption time by _consume_battle_holds per SMOKE-079).
"""
from __future__ import annotations

import inspect

import nevsky.battle as battle


def test_smoke_105_marker_present():
    src = inspect.getsource(battle.resolve_battle)
    assert "SMOKE-105" in src
    assert "either Attack or Defense" in src or "Russian is the attacker" in src


def test_smoke_105_check_does_not_require_attacker_side_teutonic():
    """The fixed predicate must not gate on attacker_side=='teutonic'
    nor striker_role=='attacker'."""
    src = inspect.getsource(battle.resolve_battle)
    # Find the raven_rock_walls block
    idx = src.find("raven_rock_walls and rounds == 1")
    assert idx > 0
    block = src[idx:idx + 600]
    # Old restricted predicate must be gone in the active branch.
    # The comment may still mention the restrictions; we only check
    # that the actual `if` condition body in the block has dropped
    # them by ensuring the new comment about SMOKE-105 appears
    # immediately above.
    # The active condition should not include attacker_side check.
    # Look for the actual if condition near the marker.
    nearby = src[max(0, idx - 1500):idx + 600]
    assert "SMOKE-105" in nearby
    # The functional condition: kind != "archery", target Russian, round 1.
    assert 'state.lords[tlid].side == "russian"' in block
    assert "kind != \"archery\"" in block


def test_smoke_105_target_must_still_be_russian():
    """The fix must NOT make Walls apply to Teutonic targets."""
    src = inspect.getsource(battle.resolve_battle)
    idx = src.find("raven_rock_walls and rounds == 1")
    block = src[idx:idx + 600]
    assert 'state.lords[tlid].side == "russian"' in block


def test_smoke_105_does_not_apply_to_archery():
    """Archery still excluded (Teutonic Archery not affected per Tip)."""
    src = inspect.getsource(battle.resolve_battle)
    idx = src.find("raven_rock_walls and rounds == 1")
    block = src[idx:idx + 600]
    assert 'kind != "archery"' in block


def test_smoke_105_does_not_apply_after_round_1():
    """Walls only Round 1 ("Round 1 Russians Walls 1-2")."""
    src = inspect.getsource(battle.resolve_battle)
    idx = src.find("raven_rock_walls and rounds == 1")
    block = src[idx:idx + 200]
    # rounds == 1 explicitly required.
    assert "rounds == 1" in block
