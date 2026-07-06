"""Round 118 (SMOKE-098/099), superseded by PLAY-11 (Fable audit,
2026-07-05): WINNERS also roll 4.4.4 Losses.

Round 118 added restore-all loops for Storm/Sally winners on the
premise "the Winner's Routed units automatically return to Forces;
only the Loser rolls Losses". That sentence appears nowhere in the
rulebook or the reference .txt. The printed 4.4.4 says "BOTH SIDES
determine the fate of their Routed units", with per-state thresholds;
4.5.2 adds for Storm: "Both sides' Forces take Losses per Battle
(4.4.4), except that Routed Defending units always roll against
Protection and Routed Attacking units that fail to roll a '1' are
removed" — explicitly including winners.

PLAY-11 therefore replaced all four winner-restore loops with
apply_losses_rolls calls:
  - Battle winner:            "stood_field"    (Protection range)
  - Storm attacker (winner):  "storm_attacker" (keep on 1)
  - Storm defender (winner):  "storm_defender" (Protection range)
  - Sally winner (either):    "stood_field"    (Protection range)
plus 4.4.4 zero-unit permanent removal for winners.

These tests pin the new behavior (source-inspection, mirroring the
original Round-118 style, plus a behavioral check).
"""
from __future__ import annotations

import inspect

import nevsky.actions  # noqa: F401
import nevsky.campaign as camp


def test_storm_sack_winner_rolls_storm_attacker_losses():
    src = inspect.getsource(camp._h_cmd_storm)
    idx = src.find("Novgorod special")
    assert idx > 0
    block = src[idx:idx + 2000]
    assert "PLAY-11" in block
    assert '"storm_attacker"' in block


def test_storm_failed_defender_rolls_protection_losses():
    src = inspect.getsource(camp._h_cmd_storm)
    idx = src.find("storm_failed")
    assert idx > 0
    block = src[idx:idx + 3000]
    assert '"storm_defender"' in block


def test_sally_withdrew_besieger_winners_roll_stood_field():
    src = inspect.getsource(camp._h_cmd_sally)
    idx = src.find('aftermath["sally_outcome"] = "withdrew"')
    assert idx > 0
    block = src[idx:idx + 3500]
    assert '"stood_field"' in block
    assert "for did in list(defenders)" in block


def test_sally_won_attacker_winners_roll_stood_field():
    src = inspect.getsource(camp._h_cmd_sally)
    idx = src.find('aftermath["sally_outcome"] = "broken_siege"')
    assert idx > 0
    before = src[max(0, idx - 3000):idx]
    assert '"stood_field"' in before
    assert "for alid in list(attackers)" in before


def test_no_unconditional_winner_restore_loops_remain():
    """The 'restore routed -> forces unconditionally' pattern must be
    gone from every aftermath (the assignment `routed_units = {}` was
    its signature)."""
    full = inspect.getsource(camp)
    assert "routed_units = {}" not in full


def test_battle_winner_losses_behavioral():
    """Battle winner with routed units either loses some units or keeps
    them via Protection rolls — but never bypasses the roll: sweep seeds
    until at least one unit is lost to prove rolls happen."""
    from nevsky.actions import apply_action
    from nevsky.scenarios import load_scenario

    saw_loss = False
    saw_keep = False
    for seed in range(1, 40):
        s = load_scenario("crusade_on_novgorod", seed=seed)
        s.meta.phase = "campaign"
        s.meta.campaign_step = "command"
        s.meta.first_levy_done = True
        s.lords["andreas"].state = "mustered"
        s.lords["andreas"].location = "lettgallia"
        # Militia screen big enough that some units rout before the
        # (inevitable) win over a lone serf.
        s.lords["andreas"].forces = {"knights": 2, "militia": 4}
        s.lords["domash"].state = "mustered"
        s.lords["domash"].location = "izborsk"
        s.lords["domash"].forces = {"light_horse": 2}
        s.lords["domash"].in_stronghold = False
        s.meta.active_player = "teutonic"
        s.campaign_turn.active_card = "andreas"
        s.campaign_turn.active_lord = "andreas"
        s.campaign_turn.actions_remaining = 3
        s.campaign_turn.in_feed_pay_disband = False
        apply_action(s, {"type": "cmd_march", "side": "teutonic",
                         "args": {"lord_id": "andreas", "to": "izborsk",
                                  "way_type": "trackway"}})
        res = apply_action(s, {"type": "stand_battle", "side": "russian",
                               "args": {}})
        if res["winner"] != "teutonic" or "andreas" not in s.lords:
            continue
        total = sum(s.lords["andreas"].forces.values())
        assert not s.lords["andreas"].routed_units, "routed pile unresolved"
        if total < 6:
            saw_loss = True
        elif total == 6:
            saw_keep = True
        if saw_loss and saw_keep:
            break
    assert saw_loss, "winner never lost a routed unit across 39 seeds — Losses not rolled"
