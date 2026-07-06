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


# ===========================================================================
# PLAY-11..14 (Fable adversarial audit, 2026-07-05): battle aftermath
# ===========================================================================
#
# PLAY-11 — 4.4.4 Losses: "BOTH SIDES determine the fate of their Routed
# units." Winners rolled nothing (restore-all, per a rule misquote in the
# SMOKE-093/098/099 lineage). Now: Battle/Sally winners roll each Routed
# unit at unmodified Protection ("stood_field"); Storm attackers keep
# Routed units only on a roll of 1 even when they Sack (4.5.2); Storm
# defenders always roll Protection. Zero-unit winners are permanently
# removed (4.4.4).
#
# PLAY-12 — 4.4.3: "All losing Lords must either Retreat ... OR Withdraw
# ... OR Be permanently removed. The owning player chooses." A fully-
# Routed loser was auto-removed with no Losses roll; now he Retreats (or
# Withdraws via withdraw_losers, or is removed via the new remove_losers
# arg) and resolves 4.4.4. LOSSES are also ordered before SPOILS per
# 4.4.3, so Lords Removed-by-Losses transfer all Assets except Ships.
#
# PLAY-13 — 4.4.5 Conquest: Battle in a Trade Route flips Conquered
# status immediately, not on the next movement entry.
#
# PLAY-14 — 4.4.1 Relief Sally: "any Besieged Lords MAY join" (opt-in
# via cmd_march args.sally_join); joiners are Attacking Lords and are
# marked Moved/Fought per 4.4.5.


def _field_battle(att_forces, def_forces, *, seed=11, locale="izborsk",
                  frm="lettgallia"):
    s = load_scenario("crusade_on_novgorod", seed=seed)
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.first_levy_done = True
    s.lords["andreas"].state = "mustered"
    s.lords["andreas"].location = frm
    s.lords["andreas"].forces = dict(att_forces)
    s.lords["domash"].state = "mustered"
    s.lords["domash"].location = locale
    s.lords["domash"].forces = dict(def_forces)
    s.lords["domash"].in_stronghold = False
    s.meta.active_player = "teutonic"
    s.campaign_turn.active_card = "andreas"
    s.campaign_turn.active_lord = "andreas"
    s.campaign_turn.actions_remaining = 3
    s.campaign_turn.in_feed_pay_disband = False
    apply_action(s, {"type": "cmd_march", "side": "teutonic",
                     "args": {"lord_id": "andreas", "to": locale,
                              "way_type": "trackway"}})
    return s


def test_play11_winner_routed_pile_always_resolved():
    """Whatever the outcome, no Lord ends a Battle with an unresolved
    routed_units pile, and winners provably lose units sometimes."""
    lost_any = False
    for seed in range(1, 30):
        s = _field_battle({"knights": 2, "militia": 4}, {"light_horse": 2},
                          seed=seed)
        res = apply_action(s, {"type": "stand_battle", "side": "russian",
                               "args": {}})
        for lid, l in s.lords.items():
            assert not l.routed_units, f"{lid} routed pile unresolved"
        if res["winner"] == "teutonic" and "andreas" in s.lords:
            if sum(s.lords["andreas"].forces.values()) < 6:
                lost_any = True
    assert lost_any, "winners never lost a routed unit in 29 games"


def test_play12_fully_routed_loser_retreats_alive():
    """A loser whose units all Routed (but has a routed pile) retreats
    and rolls Losses instead of being auto-removed. With militia
    (Protection 1-2) some survive across seeds."""
    survived = False
    for seed in range(1, 40):
        s = _field_battle({"knights": 4, "sergeants": 4},
                          {"militia": 4}, seed=seed)
        res = apply_action(s, {"type": "stand_battle", "side": "russian",
                               "args": {}})
        if res["winner"] != "teutonic":
            continue
        if "domash" in s.lords and s.lords["domash"].state == "mustered":
            assert s.lords["domash"].location != "izborsk", "loser did not retreat"
            assert sum(s.lords["domash"].forces.values()) > 0
            survived = True
            break
    assert survived, (
        "fully-routed loser never survived via 4.4.4 Protection rolls "
        "across 39 seeds — the 4.4.3 fate choice is still bypassed")


def test_play12_remove_losers_is_a_choice():
    s = _field_battle({"knights": 4, "sergeants": 4}, {"militia": 4})
    res = apply_action(s, {"type": "stand_battle", "side": "russian",
                           "args": {"remove_losers": ["domash"]}})
    assert res["winner"] == "teutonic"
    assert "domash" in res["removed"]
    assert "domash" not in s.lords or s.lords["domash"].state == "removed"


def test_play13_trade_route_flips_after_battle_win():
    """Teutons defeat the Russian defender AT a Trade Route; Conquered
    status must adjust immediately (4.4.5), not on next entry."""
    from nevsky.static_data import load_locales as _ll
    # Find a trade route adjacent to somewhere reachable: neva borders
    # kopor'e / ladoga per the map; use static data to pick one.
    trade_routes = [k for k, v in _ll().items() if v["type"] == "trade_route"]
    assert trade_routes
    # Use novgorod-adjacent 'neva' if present, else first with a trackway.
    from nevsky.static_data import load_ways as _lw
    pick = None
    for tr in trade_routes:
        for w in _lw():
            if tr in (w["a"], w["b"]):
                other = w["b"] if w["a"] == tr else w["a"]
                pick = (tr, other, w["type"])
                break
        if pick:
            break
    assert pick, "no trade route with a Way found"
    tr, frm, wtype = pick
    s = load_scenario("crusade_on_novgorod", seed=11)
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.first_levy_done = True
    s.lords["andreas"].state = "mustered"
    s.lords["andreas"].location = frm
    s.lords["andreas"].forces = {"knights": 4, "sergeants": 4}
    s.lords["andreas"].in_stronghold = False
    s.lords["domash"].state = "mustered"
    s.lords["domash"].location = tr
    s.lords["domash"].forces = {"militia": 1}
    s.lords["domash"].in_stronghold = False
    s.locales[tr].teutonic_conquered = 0
    s.meta.active_player = "teutonic"
    s.campaign_turn.active_card = "andreas"
    s.campaign_turn.active_lord = "andreas"
    s.campaign_turn.actions_remaining = 3
    s.campaign_turn.in_feed_pay_disband = False
    apply_action(s, {"type": "cmd_march", "side": "teutonic",
                     "args": {"lord_id": "andreas", "to": tr,
                              "way_type": wtype}})
    res = apply_action(s, {"type": "stand_battle", "side": "russian",
                           "args": {}})
    assert res["winner"] == "teutonic"
    assert s.locales[tr].teutonic_conquered > 0, (
        "Trade Route did not change hands after the Battle (4.4.5)")


def _relief_setup():
    s = load_scenario("crusade_on_novgorod", seed=11)
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.first_levy_done = True
    s.locales["izborsk"].teutonic_conquered = 1
    s.locales["izborsk"].siege_markers = 2
    s.lords["hermann"].state = "mustered"
    s.lords["hermann"].location = "izborsk"
    s.lords["hermann"].forces = {"sergeants": 2}
    s.lords["hermann"].in_stronghold = True
    s.lords["domash"].state = "mustered"
    s.lords["domash"].location = "izborsk"
    s.lords["domash"].forces = {"men_at_arms": 2}
    s.lords["domash"].in_stronghold = False
    s.lords["andreas"].state = "mustered"
    s.lords["andreas"].location = "lettgallia"
    s.lords["andreas"].forces = {"knights": 4, "sergeants": 4}
    s.meta.active_player = "teutonic"
    s.campaign_turn.active_card = "andreas"
    s.campaign_turn.active_lord = "andreas"
    s.campaign_turn.actions_remaining = 3
    s.campaign_turn.in_feed_pay_disband = False
    return s


def test_play14_relief_sally_join_optional():
    """sally_join=[] keeps Hermann out of the relief Battle; he stays
    inside, unmarked, with his forces untouched."""
    s = _relief_setup()
    apply_action(s, {"type": "cmd_march", "side": "teutonic",
                     "args": {"lord_id": "andreas", "to": "izborsk",
                              "way_type": "trackway", "sally_join": []}})
    res = apply_action(s, {"type": "stand_battle", "side": "russian",
                           "args": {}})
    assert "relief_sally" not in res["battle"]
    assert s.lords["hermann"].moved_fought is False
    assert s.lords["hermann"].forces == {"sergeants": 2}


def test_play14_relief_sally_joiners_marked_moved_fought():
    s = _relief_setup()
    apply_action(s, {"type": "cmd_march", "side": "teutonic",
                     "args": {"lord_id": "andreas", "to": "izborsk",
                              "way_type": "trackway"}})
    res = apply_action(s, {"type": "stand_battle", "side": "russian",
                           "args": {}})
    assert res["battle"]["relief_sally"]["sallying_lords"] == ["hermann"]
    if "hermann" in s.lords and s.lords["hermann"].state == "mustered":
        assert s.lords["hermann"].moved_fought is True, (
            "Sallying joiner fought but skipped Moved/Fought (4.4.5) — "
            "and would dodge Feed (4.8.1)")


# ===========================================================================
# PLAY-15..16 (Fable adversarial audit, 2026-07-05): battle-hold events
# ===========================================================================
#
# PLAY-15 — T6/R6 Ambush Round-1 mode: the card names the suppressed
# SIDE ("ignore Russian left and right" for T6), not a combat role. The
# engine hardcoded ambush_disable_for="attacker", inverting the card
# whenever its owner attacked.
#
# PLAY-16 — T4/R1 Bridge: "May play on FRONT CENTER [enemy] Lord in
# non-Winter Battle." A Winter play is rejected at consumption (was:
# consumed + discarded with no effect); the melee cap follows the
# targeted side's actual front-center Lord, not any named Lord.


def _ambush_probe(card, attacker_side):
    """Resolve a 3v3 battle with `card` in holds; return the battle log."""
    from nevsky.battle import resolve_battle
    s = load_scenario("crusade_on_novgorod", seed=17)
    teu = ["andreas", "hermann", "knud_and_abel"]
    rus = ["aleksandr", "andrey", "domash"]
    for lid in teu:
        s.lords[lid].state = "mustered"
        s.lords[lid].location = "izborsk"
        s.lords[lid].forces = {"men_at_arms": 2}
    for lid in rus:
        s.lords[lid].state = "mustered"
        s.lords[lid].location = "izborsk"
        s.lords[lid].forces = {"men_at_arms": 2}
    atk, dfd = (teu, rus) if attacker_side == "teutonic" else (rus, teu)
    return resolve_battle(
        s, attacker_side=attacker_side, attacker_lords=atk,
        defender_lords=dfd, holds={"ambush": card},
        concede_decisions={2: "defender"},
    )


def _round1_suppressed(result):
    """Lords logged as ambush-suppressed in Round 1."""
    out = set()
    for rl in result["log"]:
        if isinstance(rl, dict) and rl.get("round") == 1:
            for step in rl.get("steps", []):
                for e in step.get("events", []):
                    if isinstance(e, dict) and "ambush" in str(e).lower():
                        out.add(str(e))
    return out


def test_play15_t6_suppresses_russian_flanks_even_when_teutons_attack():
    """Teutons attack AND play T6: the Russian flank lords must be the
    uninvolved ones. Pre-fix the code disabled the attacker (Teutons)."""
    res = _ambush_probe("T6", "teutonic")
    # The defender (russian) flanks must not strike in round 1: verify
    # via per-round strike attribution in the log.
    r1 = next(rl for rl in res["log"] if rl.get("round") == 1)
    striker_ids = set()
    for st in r1.get("steps", []):
        for hit in st.get("per_striker", []):
            striker_ids.add(hit.get("striker"))
    rus_flank = {l for l, p in res["defender_positions"].items()
                 if p in ("left", "right")}
    teu_flank = {l for l, p in res["attacker_positions"].items()
                 if p in ("left", "right")}
    assert not (rus_flank & striker_ids), (
        f"T6 played by attacking Teutons must suppress RUSSIAN flanks; "
        f"russian flank lords struck: {rus_flank & striker_ids}")
    assert teu_flank & striker_ids, (
        "Teutonic flank lords (the card owner's) should still strike")


def test_play15_r6_suppresses_teutonic_flanks_when_russians_attack():
    res = _ambush_probe("R6", "russian")
    r1 = next(rl for rl in res["log"] if rl.get("round") == 1)
    striker_ids = set()
    for st in r1.get("steps", []):
        for hit in st.get("per_striker", []):
            striker_ids.add(hit.get("striker"))
    teu_flank = {l for l, p in res["defender_positions"].items()
                 if p in ("left", "right")}
    assert not (teu_flank & striker_ids), "R6 must suppress TEUTONIC flanks"


def test_play16_bridge_rejected_in_winter():
    """Winter play of T4 Bridge is rejected at consumption, keeping the
    card in holds."""
    import pytest
    from nevsky.actions import IllegalAction
    s = _relief_setup()  # box/season varies; force a Winter box
    # crusade_on_novgorod spans boxes; find a winter box for the state.
    from nevsky.scenarios import _season_for_box
    for box in range(1, 17):
        if _season_for_box(box) in ("early_winter", "late_winter"):
            s.meta.box = box
            break
    s.decks.teutonic.holds.append("T4")
    apply_action(s, {"type": "cmd_march", "side": "teutonic",
                     "args": {"lord_id": "andreas", "to": "izborsk",
                              "way_type": "trackway", "sally_join": []}})
    with pytest.raises(IllegalAction) as ei:
        apply_action(s, {"type": "stand_battle", "side": "russian",
                         "args": {"holds": {"bridge": "T4",
                                            "bridge_target_lord": "domash"}}})
    assert ei.value.code == "season_blocked"
    assert "T4" in s.decks.teutonic.holds, "card must stay in holds"


def test_play16_bridge_cap_follows_front_center():
    """Bridge names a reserve/left lord; the melee cap must land on the
    targeted side's front-center lord instead."""
    from nevsky.battle import resolve_battle
    s = load_scenario("crusade_on_novgorod", seed=17)
    from nevsky.scenarios import _season_for_box
    for box in range(1, 17):
        if _season_for_box(box) == "summer":
            s.meta.box = box
            break
    teu = ["andreas"]
    rus = ["aleksandr", "andrey", "domash"]
    s.lords["andreas"].state = "mustered"
    s.lords["andreas"].location = "izborsk"
    s.lords["andreas"].forces = {"men_at_arms": 2}
    for lid in rus:
        s.lords[lid].state = "mustered"
        s.lords[lid].location = "izborsk"
        s.lords[lid].forces = {"men_at_arms": 4}
    res = resolve_battle(
        s, attacker_side="teutonic", attacker_lords=teu,
        defender_lords=rus,
        holds={"bridge": "T4", "bridge_target_lord": "domash"},
        concede_decisions={2: "attacker"},
    )
    center = next(l for l, p in res["defender_positions"].items()
                  if p == "center")
    if center != "domash":
        redirects = [e for e in res["log"]
                     if isinstance(e, dict)
                     and e.get("event") == "bridge_target_redirected"]
        assert redirects and redirects[0]["front_center"] == center, (
            "Bridge cap must follow the front-center Lord (card text)")


# ===========================================================================
# PLAY-17..21 (Fable adversarial audit, 2026-07-05): End Campaign / Levy
# ===========================================================================
#
# PLAY-17 — 4.9 order: Plow & Reap (4.9.3) precedes Wastage (4.9.4).
# PLAY-18 — Veche Option C may target Muster-segment arrivals.
# PLAY-19 — 3.3 Disband is mandatory; advance_step is guarded.
# PLAY-20 — R9 sea trade: Lodya contributes at most 2 Boats-as-Ships.
# PLAY-21 — 4.9.5 Reset: sides may return held AoW cards to the deck;
#            Grow selection + reset discard now enumerated.


def _end_campaign_state(box, side="teutonic", seed=3):
    s = load_scenario("crusade_on_novgorod", seed=seed)
    s.meta.phase = "campaign"
    s.meta.campaign_step = "end_campaign"
    s.meta.first_levy_done = True
    s.meta.box = box
    # Levy/Campaign marker on `box` so calendar advance works.
    for cb in s.calendar.boxes:
        cb.has_levy_campaign_marker = (cb.box == box)
        cb.levy_campaign_face = "campaign" if cb.box == box else None
    s.meta.active_player = side
    return s


def test_play17_plow_and_reap_before_wastage():
    """Box 6 (end of Late Winter), Andreas holds 4 Sleds and nothing
    else: flip -> 4 Carts, halve -> 2 Carts, Wastage discards 1 -> 1.
    Pre-fix: Wastage ate a Sled first, leaving 2 Carts."""
    s = _end_campaign_state(6)
    s.lords["andreas"].state = "mustered"
    s.lords["andreas"].location = "riga"
    s.lords["andreas"].assets = {"sled": 4}
    res = apply_action(s, {"type": "end_campaign_resolve",
                           "side": "teutonic",
                           "args": {"wastage": {"andreas": "cart"}}})
    assert s.lords["andreas"].assets.get("cart", 0) == 1, (
        f"expected 1 Cart after 4.9.3-then-4.9.4; got "
        f"{s.lords['andreas'].assets}")
    assert s.lords["andreas"].assets.get("sled", 0) == 0


def test_play17_wastage_candidates_post_flip():
    """The palette's wastage candidates at a flip box must name the
    post-flip Transport type."""
    from nevsky.legal_moves import legal_moves
    s = _end_campaign_state(6)
    s.lords["andreas"].state = "mustered"
    s.lords["andreas"].location = "riga"
    s.lords["andreas"].assets = {"sled": 4}
    mv = next(m for m in legal_moves(s)
              if m["type"] == "end_campaign_resolve")
    cands = mv.get("candidates", {}).get("wastage", {})
    assert cands.get("andreas") == ["cart"], (
        f"candidates must reflect post-Plow-and-Reap assets; got {cands}")


def test_play18_veche_c_allows_muster_segment_arrival():
    s = load_scenario("crusade_on_novgorod", seed=3)
    s.meta.phase = "levy"
    s.meta.levy_step = "call_to_arms"
    s.meta.active_player = "russian"
    s.lords["domash"].state = "mustered"
    s.lords["domash"].location = "novgorod"
    s.lords["domash"].just_arrived_this_levy = True  # Muster-segment arrival
    s.veche.vp_markers = 2
    res = apply_action(s, {"type": "veche_action", "side": "russian",
                           "args": {"option": "C", "target_lord": "domash"}})
    assert res["option"] == "C" and res["target_lord"] == "domash"
    assert "extra_muster" in res


def test_play19_advance_step_blocked_by_mandatory_disband():
    import pytest
    from nevsky.actions import IllegalAction
    s = load_scenario("crusade_on_novgorod", seed=3)
    s.meta.phase = "levy"
    s.meta.levy_step = "disband"
    s.meta.active_player = "teutonic"
    s.lords["andreas"].state = "mustered"
    s.lords["andreas"].location = "riga"
    # Service marker LEFT of the Levy box -> mandatory removal.
    levy_box = next(cb.box for cb in s.calendar.boxes
                    if cb.has_levy_campaign_marker)
    for cb in s.calendar.boxes:
        if "andreas" in cb.service_markers:
            cb.service_markers.remove("andreas")
    target = s.calendar.boxes[max(0, levy_box - 3)]
    target.service_markers.append("andreas")
    with pytest.raises(IllegalAction) as ei:
        apply_action(s, {"type": "advance_step", "side": "teutonic",
                         "args": {}})
    assert ei.value.code == "must_disband"
    # disband_resolve then unblocks advance_step.
    apply_action(s, {"type": "disband_resolve", "side": "teutonic",
                     "args": {}})
    apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})


def test_play20_lodya_caps_at_two_phantom_ships():
    from nevsky.campaign import lodya_comparison_ships
    s = load_scenario("crusade_on_novgorod", seed=3)
    lid = "aleksandr"
    s.lords[lid].state = "mustered"
    s.lords[lid].location = "novgorod"
    s.lords[lid].assets = {"boat": 4}
    s.lords[lid].this_lord_capabilities.append("R16")
    from nevsky.capabilities import has_lord_capability
    assert has_lord_capability(s, lid, "Lodya")
    assert lodya_comparison_ships(s, lid) == 2
    s.lords[lid].assets = {"boat": 1}
    assert lodya_comparison_ships(s, lid) == 1


def test_play21_reset_discard_returns_holds_to_deck():
    s = _end_campaign_state(3)
    s.decks.teutonic.holds.append("T6")
    n_deck = len(s.decks.teutonic.deck)
    res = apply_action(s, {"type": "end_campaign_resolve",
                           "side": "teutonic",
                           "args": {"reset_discard": ["T6"]}})
    assert res["reset_discard"] == ["T6"]
    assert "T6" not in s.decks.teutonic.holds
    assert len(s.decks.teutonic.deck) == n_deck + 1


def test_play21_enumeration_offers_grow_and_reset():
    from nevsky.legal_moves import legal_moves
    s = _end_campaign_state(8)
    s.decks.teutonic.holds.append("T6")
    # Two Russian Ravaged markers -> Grow removes 1 (half up remain).
    locs = [k for k in list(s.locales.keys())[:2]]
    for k in locs:
        s.locales[k].russian_ravaged = True
    mv = next(m for m in legal_moves(s)
              if m["type"] == "end_campaign_resolve")
    cands = mv.get("candidates", {})
    assert cands.get("reset_discard") == ["T6"]
    assert cands.get("grow_remove", {}).get("choose_exactly") == 1


# ===========================================================================
# PLAY-22..24 (Fable adversarial audit, 2026-07-05): march / capabilities
# ===========================================================================
#
# PLAY-22 — 4.3.1: "The Lord beneath a Marching Lieutenant (4.1.3) must
# move with the Lieutenant" — including a NON-active Lieutenant inside a
# Marshal-led group (and the Sail mirror).
#
# PLAY-23 — 3.4.4: "Such Capabilities when Levied will affect only the
# Lord WHO LEVIED IT" — a This-Lord Capability cannot be tucked under a
# different Lord's mat.
#
# PLAY-24 — 3.4.4: "A Lord may have at most two 'This Lord' Capabilities
# at a time—the owning player must immediately discard any excess" — a
# third Levy is legal as a swap (args.discard_capability), not a hard
# rejection.


def test_play22_marshal_group_cannot_split_lieutenant_pair():
    import pytest
    from nevsky.actions import IllegalAction
    s = load_scenario("crusade_on_novgorod", seed=11)
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.first_levy_done = True
    for lid in ("andreas", "hermann", "rudolf"):
        s.lords[lid].state = "mustered"
        s.lords[lid].location = "wenden"
        s.lords[lid].forces = {"men_at_arms": 2}
    # Hermann is a Lieutenant with Rudolf beneath him.
    s.lords["hermann"].has_lower_lord = "rudolf"
    s.meta.active_player = "teutonic"
    s.campaign_turn.active_card = "andreas"
    s.campaign_turn.active_lord = "andreas"
    s.campaign_turn.actions_remaining = 3
    s.campaign_turn.in_feed_pay_disband = False
    with pytest.raises(IllegalAction) as ei:
        apply_action(s, {"type": "cmd_march", "side": "teutonic",
                         "args": {"lord_id": "andreas", "to": "tolowa",
                                  "way_type": "trackway",
                                  "group": ["andreas", "hermann"]}})
    assert ei.value.code == "lower_lord_required"
    # Full pair in group is fine.
    res = apply_action(s, {"type": "cmd_march", "side": "teutonic",
                           "args": {"lord_id": "andreas", "to": "tolowa",
                                    "way_type": "trackway",
                                    "group": ["andreas", "hermann", "rudolf"]}})
    assert s.lords["rudolf"].location == "tolowa"


def test_play23_this_lord_capability_only_under_levier():
    import pytest
    from nevsky.actions import IllegalAction
    s = load_scenario("crusade_on_novgorod", seed=3)
    s.meta.phase = "levy"
    s.meta.levy_step = "muster"
    s.meta.active_player = "teutonic"
    for lid in ("andreas", "rudolf"):
        s.lords[lid].state = "mustered"
        s.lords[lid].location = "riga"
        s.lords[lid].lordship_used = 0
    # T9 Halbbruder is a this_lord capability leviable by Teutons.
    from nevsky.static_data import load_cards
    cards = load_cards()
    tl = next(cid for cid in s.decks.teutonic.deck
              if cards[cid]["capability_scope"] == "this_lord"
              and not cards[cid]["no_event"])
    with pytest.raises(IllegalAction) as ei:
        apply_action(s, {"type": "levy_capability", "side": "teutonic",
                         "args": {"by_lord": "andreas", "card_id": tl,
                                  "lord_id": "rudolf"}})
    assert ei.value.code in ("bad_target", "not_eligible")


def test_play24_levy_and_swap_third_capability():
    import pytest
    from nevsky.actions import IllegalAction
    from nevsky.static_data import load_cards
    s = load_scenario("crusade_on_novgorod", seed=3)
    s.meta.phase = "levy"
    s.meta.levy_step = "muster"
    s.meta.active_player = "teutonic"
    s.lords["andreas"].state = "mustered"
    s.lords["andreas"].location = "riga"
    s.lords["andreas"].lordship_used = 0
    cards = load_cards()
    # Three distinct-name this_lord capabilities Andreas may levy.
    eligible = []
    for cid in list(s.decks.teutonic.deck):
        c = cards[cid]
        if c["capability_scope"] != "this_lord" or c["no_event"]:
            continue
        try:
            from nevsky.actions import _check_capability_eligibility
            _check_capability_eligibility(c, "andreas", role="levyer")
            _check_capability_eligibility(c, "andreas", role="target")
        except Exception:
            continue
        if all(cards[e]["capability_name"] != c["capability_name"]
               for e in eligible):
            eligible.append(cid)
        if len(eligible) == 3:
            break
    assert len(eligible) == 3, f"fixture needs 3 distinct capabilities, got {eligible}"
    a, b, c3 = eligible
    apply_action(s, {"type": "levy_capability", "side": "teutonic",
                     "args": {"by_lord": "andreas", "card_id": a}})
    apply_action(s, {"type": "levy_capability", "side": "teutonic",
                     "args": {"by_lord": "andreas", "card_id": b}})
    s.lords["andreas"].lordship_used = 0  # fresh Lordship for the swap
    # Third without discard choice -> cap_limit with swap hint.
    with pytest.raises(IllegalAction) as ei:
        apply_action(s, {"type": "levy_capability", "side": "teutonic",
                         "args": {"by_lord": "andreas", "card_id": c3}})
    assert ei.value.code == "cap_limit"
    # Swap out `a`.
    res = apply_action(s, {"type": "levy_capability", "side": "teutonic",
                           "args": {"by_lord": "andreas", "card_id": c3,
                                    "discard_capability": a}})
    assert res["discarded_capability"] == a
    assert sorted(s.lords["andreas"].this_lord_capabilities) == sorted([b, c3])
    assert a in s.decks.teutonic.discard


def test_play24_swap_enumerated_with_candidates():
    from nevsky.legal_moves import legal_moves
    from nevsky.static_data import load_cards
    s = load_scenario("crusade_on_novgorod", seed=3)
    s.meta.phase = "levy"
    s.meta.levy_step = "muster"
    s.meta.active_player = "teutonic"
    s.lords["andreas"].state = "mustered"
    s.lords["andreas"].location = "riga"
    s.lords["andreas"].lordship_used = 0
    cards = load_cards()
    have = []
    for cid in list(s.decks.teutonic.deck):
        c = cards[cid]
        if c["capability_scope"] != "this_lord" or c["no_event"]:
            continue
        try:
            from nevsky.actions import _check_capability_eligibility
            _check_capability_eligibility(c, "andreas", role="levyer")
        except Exception:
            continue
        if all(cards[e]["capability_name"] != c["capability_name"] for e in have):
            have.append(cid)
        if len(have) == 2:
            break
    for cid in have:
        s.decks.teutonic.deck.remove(cid)
        s.lords["andreas"].this_lord_capabilities.append(cid)
    swaps = [m for m in legal_moves(s)
             if m["type"] == "levy_capability"
             and m.get("candidates", {}).get("discard_capability")]
    assert swaps, "at 2-card cap the palette must offer Levy-and-swap"
    assert swaps[0]["candidates"]["discard_capability"] == have


# ===========================================================================
# PLAY-25 (Fable adversarial audit, 2026-07-05): Conquered Strongholds
# defend with their CURRENT owner, not their static territory side
# ===========================================================================


def _conquered_izborsk_state(active, active_side, seed=11):
    """Hermann Withdrawn inside Teuton-Conquered Izborsk (SMOKE-130
    state); Domash besieging outside."""
    s = load_scenario("crusade_on_novgorod", seed=seed)
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.first_levy_done = True
    s.locales["izborsk"].teutonic_conquered = 1
    s.locales["izborsk"].siege_markers = 2
    s.lords["hermann"].state = "mustered"
    s.lords["hermann"].location = "izborsk"
    s.lords["hermann"].forces = {"knights": 1, "sergeants": 1}
    s.lords["hermann"].in_stronghold = True
    s.lords["domash"].state = "mustered"
    s.lords["domash"].location = "izborsk"
    s.lords["domash"].forces = {"men_at_arms": 4, "militia": 4}
    s.lords["domash"].in_stronghold = False
    s.meta.active_player = active_side
    s.campaign_turn.active_card = active
    s.campaign_turn.active_lord = active
    from nevsky.campaign import _effective_command_rating
    s.campaign_turn.actions_remaining = _effective_command_rating(s, active)
    s.campaign_turn.in_feed_pay_disband = False
    return s


def test_play25_owner_helper():
    from nevsky.campaign import _effective_stronghold_owner
    s = _conquered_izborsk_state("domash", "russian")
    assert _effective_stronghold_owner(s, "izborsk") == "teutonic"
    s.locales["izborsk"].teutonic_conquered = 0
    assert _effective_stronghold_owner(s, "izborsk") == "russian"


def test_play25_besieger_gets_siege_and_no_surrender_roll():
    """The RUSSIAN besieger of Teuton-Conquered Izborsk may Siege, and
    no Surrender roll fires while Hermann is Besieged inside."""
    from nevsky.legal_moves import legal_moves
    s = _conquered_izborsk_state("domash", "russian")
    moves = [m["type"] for m in legal_moves(s)]
    assert "cmd_siege" in moves and "cmd_storm" in moves, (
        f"besieger of a Conquered Stronghold must get Siege/Storm; got {moves}")
    res = apply_action(s, {"type": "cmd_siege", "side": "russian",
                           "args": {"lord_id": "domash"}})
    assert res["surrender"] is None, (
        "Surrender rolled although an enemy Lord is Besieged inside (4.5.1)")


def test_play25_owner_cannot_siege_own_conquered_stronghold():
    from nevsky.legal_moves import legal_moves
    s = _conquered_izborsk_state("hermann", "teutonic")
    # Hermann is inside/besieged; use a fresh outside Teuton instead.
    s.lords["andreas"].state = "mustered"
    s.lords["andreas"].location = "izborsk"
    s.lords["andreas"].forces = {"knights": 2}
    s.lords["andreas"].in_stronghold = False
    s.lords["domash"].state = "ready"      # remove the Russian besieger
    s.lords["domash"].location = None
    s.campaign_turn.active_card = "andreas"
    s.campaign_turn.active_lord = "andreas"
    from nevsky.campaign import _effective_command_rating
    s.campaign_turn.actions_remaining = _effective_command_rating(s, "andreas")
    moves = [m["type"] for m in legal_moves(s)]
    assert "cmd_siege" not in moves and "cmd_storm" not in moves, (
        f"owner side offered Siege/Storm against its own Stronghold: {moves}")
    import pytest
    from nevsky.actions import IllegalAction
    with pytest.raises(IllegalAction) as ei:
        apply_action(s, {"type": "cmd_siege", "side": "teutonic",
                         "args": {"lord_id": "andreas"}})
    assert ei.value.code in ("own_stronghold", "no_siege")


def test_play25_storm_arrays_and_sacks_the_inside_lord():
    """Russians Storm Teuton-Conquered Izborsk: Hermann defends and on
    a Sack he is permanently removed (4.5.2), the fort liberated."""
    sacked = False
    for seed in range(1, 30):
        s = _conquered_izborsk_state("domash", "russian", seed=seed)
        s.lords["domash"].forces = {"knights": 4, "men_at_arms": 4}
        res = apply_action(s, {"type": "cmd_storm", "side": "russian",
                               "args": {"lord_id": "domash"}})
        b = res.get("battle") or res
        if res.get("besieged_removed"):
            sacked = True
            assert "hermann" in res["besieged_removed"]
            assert "hermann" not in s.lords or s.lords["hermann"].state == "removed"
            assert s.locales["izborsk"].teutonic_conquered == 0, "liberation"
            break
    assert sacked, "storm never sacked across 29 seeds — inside Lord not defending?"
