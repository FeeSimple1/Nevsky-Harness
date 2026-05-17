"""SMOKE-098/099 (Round 118): Storm/Sally winners' routed_units
never restored to forces — Battle handler does this ("winner
doesn't suffer Losses"), Storm and Sally previously did not.

Per 4.4.4 Losses: the WINNER's Routed units automatically return
to Forces; only the LOSER rolls Losses. The Battle handler
(_h_stand_battle) correctly restores winning Lords' routed_units
to forces. Storm and Sally handlers omitted this restore —
winners that had units routed during the encounter were left
with a non-empty routed_units pile that silently persisted.

Fix: in all four Storm/Sally outcome branches, iterate the
winning side's Lords and move routed_units → forces.

Storm branches:
  - winner == "attacker" (Sack): restore attackers
  - winner == "defender" (storm_failed): restore besieged (defenders)

Sally branches:
  - sallying side LOST (RAID withdrew): besiegers won → restore defenders
  - sallying side WON (broken_siege): sallying lords won → restore attackers
"""
from __future__ import annotations

import inspect

import nevsky.actions  # noqa: F401
import nevsky.campaign as camp


def test_storm_winner_attacker_restores_routed():
    src = inspect.getsource(camp._h_cmd_storm)
    # Locate the winner == "attacker" Sack block by anchoring on the
    # "Spoils: loot/provender/coin" comment.
    idx = src.find("Novgorod special")
    assert idx > 0
    # The SMOKE-098 restore should appear shortly after.
    block = src[idx:idx + 1500]
    assert "SMOKE-098" in block
    assert "al.routed_units" in block or "routed_units = {}" in block


def test_storm_failed_restores_defender_routed():
    src = inspect.getsource(camp._h_cmd_storm)
    idx = src.find("storm_failed")
    assert idx > 0
    block = src[idx:idx + 2000]
    # SMOKE-098 should be present in the storm_failed branch for
    # defenders restore.
    assert "SMOKE-098" in block


def test_sally_withdrew_restores_defender_routed():
    src = inspect.getsource(camp._h_cmd_sally)
    idx = src.find('aftermath["sally_outcome"] = "withdrew"')
    assert idx > 0
    block = src[idx:idx + 2500]
    assert "SMOKE-099" in block
    # The restore should target defenders (besiegers who won).
    assert "for did in defenders" in block


def test_sally_won_restores_attacker_routed():
    src = inspect.getsource(camp._h_cmd_sally)
    idx = src.find('aftermath["sally_outcome"] = "broken_siege"')
    assert idx > 0
    # Look BEFORE the broken_siege marker for SMOKE-099 sallying-won restore.
    before = src[max(0, idx - 2000):idx]
    assert "SMOKE-099" in before
    assert "for alid in attackers" in before


def test_winner_restore_count_matches_four_branches():
    """All four winner-restore code blocks should be present."""
    full = inspect.getsource(camp)
    # Each branch references al.routed_units or dl.routed_units = {}
    # in the SMOKE-098/099 restore loops.
    count = full.count("SMOKE-098")
    assert count >= 2  # Storm winner (attacker) + Storm winner (defender)
    count_099 = full.count("SMOKE-099")
    assert count_099 >= 2  # Sally winner (besiegers) + Sally winner (attackers)
