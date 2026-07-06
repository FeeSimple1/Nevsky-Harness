"""PLAY-1/2/3 (Fable interactive playtest of crusade_on_novgorod):
three engine bugs surfaced by LLM-vs-LLM play through nevsky.llm.

PLAY-1 — AoW decks were never shuffled. SoP 3.1.1 has each side
shuffle all unused own AoW cards (deck + discard) into a fresh deck
at every Levy's Arts of War step, but the harness only enumerated
aow_shuffle when the deck was empty and never shuffled otherwise.
Result: every game opened with the sorted draws T1+T10 / R1+R10 and
continued deterministically, REGARDLESS of seed. Fix: _h_aow_draw
performs the 3.1.1 shuffle (deck + discard pooled, holds /
capabilities-in-play / removed untouched) before drawing, once per
side per Levy (guarded by the aow_drawn_{t,r} latch).

PLAY-2 — Avoid Battle ended the Marching side's Command card. Per
4.3.4 a fully-Avoided Approach produces NO Battle; only a Battle or
Storm ("blocks any further Command actions", 4.4.4 Recovery) or
Encamp (4.3.5) ends the card. _h_avoid_battle unconditionally zeroed
actions_remaining and entered 4.8. Fix: the attacker's card continues
with its remaining actions unless the Approach left it Besieging.

PLAY-3 — Stale Siege markers when the besiegers left by a path other
than a plain March: (a) Avoid Battle out of the Siege Locale, (b) the
Approach branch of cmd_march (early return skipped the R215 sweep),
(c) cmd_sail departure. Per 4.3.5 "If all Besieging Lords later
depart, remove all Siege markers." Observed live: Hermann sat
"Besieged" inside Teuton-Conquered Izborsk after the lone Russian
besieger Avoided away; his only moves were Sally (which raises
no_defenders) and Pass. Fix: route all three paths through
_lift_siege_if_no_besiegers.
"""
from __future__ import annotations

import nevsky.actions  # noqa: F401 — register handlers
from nevsky.actions import apply_action
from nevsky.scenarios import load_scenario
from nevsky.state import CombatPending


# ----- PLAY-1: 3.1.1 shuffle ----------------------------------------------


def _first_draw(seed: int, side: str = "teutonic") -> list[str]:
    s = load_scenario("crusade_on_novgorod", seed=seed)
    s.meta.phase = "levy"
    s.meta.levy_step = "arts_of_war"
    s.meta.active_player = side
    res = apply_action(s, {"type": "aow_draw", "side": side, "args": {}})
    return res["drawn"]


def test_play1_draws_vary_by_seed():
    """Pre-fix every seed drew the sorted-head pair (T1, T10)."""
    draws = {tuple(_first_draw(seed)) for seed in range(1, 9)}
    assert len(draws) > 1, (
        f"first-Levy draws identical across 8 seeds: {draws} — deck unshuffled"
    )


def test_play1_draw_reproducible_per_seed():
    assert _first_draw(3) == _first_draw(3)


def test_play1_shuffle_pools_discard():
    """3.1.1: unused = deck + discard; discard must be empty post-draw."""
    s = load_scenario("crusade_on_novgorod", seed=5)
    s.meta.phase = "levy"
    s.meta.levy_step = "arts_of_war"
    s.meta.active_player = "teutonic"
    # Simulate a card sitting in discard from a prior Levy.
    cid = s.decks.teutonic.deck.pop()
    s.decks.teutonic.discard.append(cid)
    n_total = len(s.decks.teutonic.deck) + 1
    apply_action(s, {"type": "aow_draw", "side": "teutonic", "args": {}})
    assert s.decks.teutonic.discard == []
    assert len(s.decks.teutonic.deck) == n_total - 2
    held_out = set(s.decks.teutonic.holds) | set(
        s.decks.teutonic.capabilities_in_play) | set(s.decks.teutonic.removed)
    assert not held_out & set(s.decks.teutonic.deck)


# ----- helpers for PLAY-2 / PLAY-3 -----------------------------------------


def _approach_state(*, defender_inside: str | None = None,
                    siege_markers: int = 0,
                    izborsk_teuton_conquered: bool = False,
                    attacker_actions: int = 3):
    """Russian Domash approaches Izborsk where Teuton Hermann defends
    in the open; optionally another Teuton sits inside the Stronghold
    under an existing Russian Siege."""
    s = load_scenario("crusade_on_novgorod", seed=11)
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.first_levy_done = True

    s.lords["domash"].state = "mustered"
    s.lords["domash"].location = "pskov"
    s.lords["domash"].forces = {"men_at_arms": 2, "militia": 2}
    s.lords["domash"].in_stronghold = False

    s.lords["hermann"].state = "mustered"
    s.lords["hermann"].location = "izborsk"
    s.lords["hermann"].forces = {"knights": 1, "sergeants": 1}
    s.lords["hermann"].in_stronghold = False

    if defender_inside:
        s.lords[defender_inside].state = "mustered"
        s.lords[defender_inside].location = "izborsk"
        s.lords[defender_inside].forces = {"sergeants": 1}
        s.lords[defender_inside].in_stronghold = True
    if izborsk_teuton_conquered:
        s.locales["izborsk"].teutonic_conquered = 1
    s.locales["izborsk"].siege_markers = siege_markers

    s.meta.active_player = "russian"
    s.campaign_turn.active_card = "domash"
    s.campaign_turn.active_lord = "domash"
    s.campaign_turn.actions_remaining = attacker_actions
    s.campaign_turn.in_feed_pay_disband = False
    return s


# ----- PLAY-2: attacker card continues after full Avoid ---------------------


def test_play2_attacker_card_continues_after_avoid():
    s = _approach_state(izborsk_teuton_conquered=False)
    res = apply_action(s, {"type": "cmd_march", "side": "russian",
                           "args": {"lord_id": "domash", "to": "izborsk",
                                    "way_type": "trackway"}})
    assert res.get("approach") is True
    assert s.campaign_turn.actions_remaining == 2  # 3 - march cost 1
    res2 = apply_action(s, {"type": "avoid_battle", "side": "teutonic",
                            "args": {"to": "ugaunia"}})
    # Izborsk (unconquered Russian Fort) is FRIENDLY to the attacker:
    # no Encamp, so Domash's card continues.
    assert res2["placed_siege"] is False
    assert s.combat_pending is None
    assert s.meta.active_player == "russian"
    assert s.campaign_turn.actions_remaining == 2
    assert s.campaign_turn.in_feed_pay_disband is False


def test_play2_encamp_after_avoid_still_ends_card():
    """If the Avoid leaves the attacker Besieging an enemy Stronghold,
    ENCAMP (4.3.5) ends the card as before."""
    s = _approach_state(izborsk_teuton_conquered=True)
    apply_action(s, {"type": "cmd_march", "side": "russian",
                     "args": {"lord_id": "domash", "to": "izborsk",
                              "way_type": "trackway"}})
    res2 = apply_action(s, {"type": "avoid_battle", "side": "teutonic",
                            "args": {"to": "ugaunia"}})
    assert res2["placed_siege"] is True
    assert s.campaign_turn.actions_remaining == 0
    assert s.campaign_turn.in_feed_pay_disband is True


# ----- PLAY-3: sieges lift when the besiegers leave --------------------------


def test_play3_avoid_lifts_stale_siege():
    """Hermann besieges nobody after the lone Russian besieger Avoids
    away — wait, inverse arrangement: Russian Domash besieged a Teuton
    inside Teuton-Conquered Izborsk; Domash (in the open) Avoids away
    from an approaching Teuton relief force. The Siege must lift."""
    s = load_scenario("crusade_on_novgorod", seed=11)
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.first_levy_done = True

    # Hermann inside Teuton-Conquered Izborsk, Besieged by Domash.
    s.locales["izborsk"].teutonic_conquered = 1
    s.locales["izborsk"].siege_markers = 1
    s.lords["hermann"].state = "mustered"
    s.lords["hermann"].location = "izborsk"
    s.lords["hermann"].forces = {"sergeants": 1}
    s.lords["hermann"].in_stronghold = True
    s.lords["domash"].state = "mustered"
    s.lords["domash"].location = "izborsk"
    s.lords["domash"].forces = {"men_at_arms": 2, "militia": 2}
    s.lords["domash"].in_stronghold = False
    # Teuton relief: Andreas approaches from Lettgallia.
    s.lords["andreas"].state = "mustered"
    s.lords["andreas"].location = "lettgallia"
    s.lords["andreas"].forces = {"knights": 2, "sergeants": 2}
    s.lords["andreas"].in_stronghold = False

    s.meta.active_player = "teutonic"
    s.campaign_turn.active_card = "andreas"
    s.campaign_turn.active_lord = "andreas"
    s.campaign_turn.actions_remaining = 3
    res = apply_action(s, {"type": "cmd_march", "side": "teutonic",
                           "args": {"lord_id": "andreas", "to": "izborsk",
                                    "way_type": "trackway"}})
    assert res.get("approach") is True
    assert res["defender_lords"] == ["domash"]
    apply_action(s, {"type": "avoid_battle", "side": "russian",
                     "args": {"to": "pskov"}})
    assert s.locales["izborsk"].siege_markers == 0, "stale Siege not lifted"
    assert s.lords["hermann"].in_stronghold is False


def test_play3_march_approach_lifts_siege_at_source():
    """A lone besieger who Marches off the Siege Locale INTO an
    Approach elsewhere also ends the Siege at the source (the early-
    return Approach branch skipped the R215 sweep)."""
    s = _approach_state(izborsk_teuton_conquered=False)
    # Domash currently (pre-march) besieges a Teuton inside Pskov.
    # (Gavrilo starts the scenario mustered at Pskov; move him away so
    # Domash is the LONE besieger.)
    s.lords["gavrilo"].location = "novgorod"
    s.locales["pskov"].teutonic_conquered = 1
    s.locales["pskov"].siege_markers = 1
    s.lords["rudolf"].state = "mustered"
    s.lords["rudolf"].location = "pskov"
    s.lords["rudolf"].forces = {"sergeants": 1}
    s.lords["rudolf"].in_stronghold = True
    res = apply_action(s, {"type": "cmd_march", "side": "russian",
                           "args": {"lord_id": "domash", "to": "izborsk",
                                    "way_type": "trackway"}})
    assert res.get("approach") is True
    assert s.locales["pskov"].siege_markers == 0
    assert s.lords["rudolf"].in_stronghold is False


# ===========================================================================
# PLAY-7..10 (Fable adversarial audit, 2026-07-05): siege lifecycle
# ===========================================================================
#
# PLAY-7 — 4.5.1 Surrender: "Remove Siege markers." The engine kept the
# markers on a successful Surrender and then ran the Siegeworks step
# unconditionally (rules: only "If the Stronghold did not Surrender"),
# leaving the new owner's own city a permanent Siege Locale — and offering
# cmd_siege / cmd_storm against their own Stronghold on later cards. Also
# 4.5.1 "the Besieging side MAY roll": declining the roll is now a legal,
# enumerated choice (Siegeworks still applies when declining).
#
# PLAY-8 — 4.3.5 / 4.4.5: when the losing besiegers depart the field by
# battle RETREAT (relief battle), the Siege must lift. PLAY-3 fixed the
# avoid/march/sail departure paths; the retreat path was missed.
#
# PLAY-9 — 4.3.5 Besiege "WHENEVER ...": winning a field Battle outside an
# Unbesieged enemy Stronghold (no enemy Lords left outside) begins the
# Siege immediately (4.4.5 "If the combat created ... a Siege").
#
# PLAY-10 — after a won Sally the Siege is over; the sallying winners'
# in_stronghold flag must clear so a later enemy March triggers a fresh
# 4.3.4 Approach instead of silently re-Besieging them.


def _siege_state(*, markers: int = 3, besieged_inside: str | None = None,
                 besieger: str = "hermann", seed: int = 11):
    """Teuton `besieger` besieging Russian fort Izborsk."""
    s = load_scenario("crusade_on_novgorod", seed=seed)
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.first_levy_done = True
    s.lords[besieger].state = "mustered"
    s.lords[besieger].location = "izborsk"
    s.lords[besieger].forces = {"knights": 2, "sergeants": 2}
    s.lords[besieger].in_stronghold = False
    if besieged_inside:
        s.lords[besieged_inside].state = "mustered"
        s.lords[besieged_inside].location = "izborsk"
        s.lords[besieged_inside].forces = {"militia": 1}
        s.lords[besieged_inside].in_stronghold = True
    s.locales["izborsk"].siege_markers = markers
    s.meta.active_player = "teutonic"
    s.campaign_turn.active_card = besieger
    s.campaign_turn.active_lord = besieger
    from nevsky.campaign import _effective_command_rating
    s.campaign_turn.actions_remaining = _effective_command_rating(s, besieger)
    s.campaign_turn.in_feed_pay_disband = False
    return s


def test_play7_surrender_removes_siege_markers():
    """On Surrender success: markers removed, no Siegeworks. On failure:
    Siegeworks may add. Sweep seeds so both branches are exercised."""
    saw_success = saw_failure = False
    for seed in range(1, 25):
        s = _siege_state(markers=3, seed=seed)
        res = apply_action(s, {"type": "cmd_siege", "side": "teutonic",
                               "args": {"lord_id": "hermann"}})
        sur = res["surrender"]
        if sur and sur.get("conquered"):
            saw_success = True
            assert s.locales["izborsk"].siege_markers == 0, (
                f"seed {seed}: Surrender left Siege markers")
            assert res["siege_added"] is False, (
                f"seed {seed}: Siegeworks ran after Surrender")
            assert s.locales["izborsk"].teutonic_conquered > 0
        else:
            saw_failure = True
            # No surrender: siegeworks check as before (1 besieger >=
            # fort capacity 1 -> add, up to 4).
            assert s.locales["izborsk"].siege_markers == 4
        if saw_success and saw_failure:
            break
    assert saw_success and saw_failure, "seed sweep failed to hit both branches"


def test_play7_decline_surrender_roll():
    s = _siege_state(markers=2)
    res = apply_action(s, {"type": "cmd_siege", "side": "teutonic",
                           "args": {"lord_id": "hermann",
                                    "decline_surrender": True}})
    assert res["surrender"] == {"conquered": False, "declined": True}
    # Siegeworks still applies when declining (4.5.1).
    assert res["siege_added"] is True
    assert s.locales["izborsk"].siege_markers == 3
    assert s.locales["izborsk"].teutonic_conquered == 0


def test_play7_decline_enumerated_only_without_besieged_lords():
    from nevsky.legal_moves import legal_moves
    s = _siege_state(markers=2)
    moves = [m for m in legal_moves(s) if m["type"] == "cmd_siege"]
    assert any(m["args"].get("decline_surrender") for m in moves)
    s2 = _siege_state(markers=2, besieged_inside="gavrilo")
    moves2 = [m for m in legal_moves(s2) if m["type"] == "cmd_siege"]
    assert moves2, "cmd_siege gone entirely"
    assert not any(m["args"].get("decline_surrender") for m in moves2), (
        "decline offered although no Surrender roll would occur")


def _relief_battle_state():
    """Russian Domash besieges Hermann inside Teuton-Conquered Izborsk;
    Teuton relief (Andreas, overwhelming) approaches from Lettgallia."""
    s = load_scenario("crusade_on_novgorod", seed=11)
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.first_levy_done = True
    s.locales["izborsk"].teutonic_conquered = 1
    s.locales["izborsk"].siege_markers = 2
    s.lords["hermann"].state = "mustered"
    s.lords["hermann"].location = "izborsk"
    s.lords["hermann"].forces = {"sergeants": 1}
    s.lords["hermann"].in_stronghold = True
    s.lords["domash"].state = "mustered"
    s.lords["domash"].location = "izborsk"
    s.lords["domash"].forces = {"men_at_arms": 2}
    s.lords["domash"].in_stronghold = False
    s.lords["andreas"].state = "mustered"
    s.lords["andreas"].location = "lettgallia"
    s.lords["andreas"].forces = {"knights": 4, "sergeants": 4}
    s.lords["andreas"].in_stronghold = False
    s.meta.active_player = "teutonic"
    s.campaign_turn.active_card = "andreas"
    s.campaign_turn.active_lord = "andreas"
    s.campaign_turn.actions_remaining = 3
    s.campaign_turn.in_feed_pay_disband = False
    apply_action(s, {"type": "cmd_march", "side": "teutonic",
                     "args": {"lord_id": "andreas", "to": "izborsk",
                              "way_type": "trackway"}})
    return s


def test_play8_relief_battle_retreat_lifts_siege():
    """Losing besieger Concedes Round 1 and Retreats alive; the Siege
    must lift (4.3.5 departure) instead of stranding Hermann."""
    s = _relief_battle_state()
    res = apply_action(s, {"type": "stand_battle", "side": "russian",
                           "args": {"concede": "defender"}})
    assert res["winner"] == "teutonic"
    # Domash retreated alive (conceded round 1: no strikes exchanged).
    assert "domash" in s.lords and s.lords["domash"].location != "izborsk"
    assert s.locales["izborsk"].siege_markers == 0, (
        "Siege markers survived the besieger's battle-retreat departure")
    assert s.lords["hermann"].in_stronghold is False, (
        "Hermann still Besieged by nobody")


def test_play9_battle_win_begins_siege():
    """Teutons defeat the open defender at Russian fort Izborsk; per
    4.3.5 'Whenever' the winners now Besiege the empty Stronghold."""
    s = load_scenario("crusade_on_novgorod", seed=11)
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.first_levy_done = True
    s.lords["andreas"].state = "mustered"
    s.lords["andreas"].location = "lettgallia"
    s.lords["andreas"].forces = {"knights": 4, "sergeants": 4}
    s.lords["domash"].state = "mustered"
    s.lords["domash"].location = "izborsk"
    s.lords["domash"].forces = {"militia": 1}
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
    assert res["winner"] == "teutonic"
    assert res.get("placed_siege") is True
    assert s.locales["izborsk"].siege_markers == 1, (
        "winning the Battle outside the enemy Stronghold must begin the Siege")


def test_play9_no_siege_at_own_locale():
    """Negative control: defender wins at its own Stronghold Locale —
    no Siege marker appears."""
    s = load_scenario("crusade_on_novgorod", seed=11)
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.first_levy_done = True
    s.lords["andreas"].state = "mustered"
    s.lords["andreas"].location = "lettgallia"
    s.lords["andreas"].forces = {"militia": 1}
    s.lords["domash"].state = "mustered"
    s.lords["domash"].location = "izborsk"
    s.lords["domash"].forces = {"knights": 4, "men_at_arms": 4}
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
    assert res["winner"] == "russian"
    assert s.locales["izborsk"].siege_markers == 0


def test_play10_sally_win_clears_in_stronghold():
    """Hermann (overwhelming) sallies and breaks the Siege; his
    in_stronghold flag must clear so a later Approach fires."""
    s = load_scenario("crusade_on_novgorod", seed=11)
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.first_levy_done = True
    s.locales["izborsk"].teutonic_conquered = 1
    s.locales["izborsk"].siege_markers = 2
    s.lords["hermann"].state = "mustered"
    s.lords["hermann"].location = "izborsk"
    s.lords["hermann"].forces = {"knights": 4, "sergeants": 4}
    s.lords["hermann"].in_stronghold = True
    s.lords["domash"].state = "mustered"
    s.lords["domash"].location = "izborsk"
    s.lords["domash"].forces = {"militia": 1}
    s.lords["domash"].in_stronghold = False
    s.meta.active_player = "teutonic"
    s.campaign_turn.active_card = "hermann"
    s.campaign_turn.active_lord = "hermann"
    from nevsky.campaign import _effective_command_rating
    s.campaign_turn.actions_remaining = _effective_command_rating(s, "hermann")
    s.campaign_turn.in_feed_pay_disband = False
    res = apply_action(s, {"type": "cmd_sally", "side": "teutonic",
                           "args": {"lord_id": "hermann"}})
    assert res.get("sally_outcome") == "broken_siege"
    assert s.locales["izborsk"].siege_markers == 0
    assert s.lords["hermann"].in_stronghold is False, (
        "sally winner still flagged in_stronghold; later enemy March "
        "would skip the 4.3.4 Approach and silently re-Besiege him")
