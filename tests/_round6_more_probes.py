"""Round 6 part 2: more aggressive edge cases hunting for latent bugs."""

from __future__ import annotations

from nevsky.actions import IllegalAction, apply_action
from nevsky.scenarios import load_scenario


BUGS = []


def check(condition, msg):
    if not condition:
        BUGS.append(msg)
        print(f"  ! BUG: {msg}")
    else:
        print(f"  OK: {msg}")


def section(title):
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


# === Test 1: Novgorod Sack with overwhelming force ==========================
def test_novgorod_sack_strong_force():
    section("Novgorod Sack with strong force")
    s = load_scenario("crusade_on_novgorod", seed=42)
    s.lords["domash"].location = "novgorod"
    s.lords["domash"].in_stronghold = True
    s.lords["domash"].forces = {"militia": 1}
    for lid in ("hermann", "yaroslav", "knud_and_abel"):
        s.lords[lid].location = "novgorod"
        s.lords[lid].forces = {"knights": 8, "men_at_arms": 8}  # crushing force
    s.locales["novgorod"].siege_markers = 4
    s.veche.coin = 5
    pre_t_vp = s.calendar.teutonic_vp
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "teutonic"
    s.campaign_turn.next_to_reveal = "teutonic"
    s.campaign_turn.active_card = "hermann"
    s.campaign_turn.active_lord = "hermann"
    s.campaign_turn.actions_remaining = 3
    res = apply_action(s, {"type": "cmd_storm", "side": "teutonic",
                            "args": {"lord_id": "hermann"}})
    if res["battle"]["winner"] == "attacker":
        check(s.locales["novgorod"].teutonic_conquered == 3,
              f"Novgorod stacks 3 Conquered markers; got {s.locales['novgorod'].teutonic_conquered}")
        check(s.calendar.teutonic_vp == pre_t_vp + 3.0,
              f"T VP +3; got delta {s.calendar.teutonic_vp - pre_t_vp}")
        check(s.veche.coin == 0, f"Veche Coin emptied; got {s.veche.coin}")
        check(s.lords["hermann"].assets.get("coin", 0) > 0,
              f"hermann got Veche Coin: {s.lords['hermann'].assets.get('coin', 0)}")
        check(s.locales["novgorod"].walls_plus_one is False,
              "Walls +1 cleared on Sack")
    else:
        print(f"  RNG defender won; skip")


# === Test 2: Lord with only Serfs (no Protection) ==========================
def test_serfs_only_battle():
    section("Lord with only Serfs (no Protection)")
    from nevsky.battle import resolve_battle
    s = load_scenario("watland", seed=7)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    s.lords[teu].forces = {"knights": 3}
    s.lords[rus].forces = {"serfs": 4}  # Serfs only; no Protection
    res = resolve_battle(s, "teutonic", [teu], [rus])
    check(res["winner"] == "teutonic",
          f"Knights crush Serfs; winner={res['winner']}")
    check(s.lords[rus].forces.get("serfs", 0) == 0,
          f"Serfs all routed; got {s.lords[rus].forces.get('serfs', 0)}")


# === Test 3: aow_play_hold with card not in holds =========================
def test_play_hold_not_in_holds():
    section("aow_play_hold: card not in holds")
    s = load_scenario("watland", seed=1)
    s.decks.russian.holds = []
    try:
        apply_action(s, {"type": "aow_play_hold", "side": "russian",
                          "args": {"card_id": "R3", "target": "domash"}})
        BUGS.append("aow_play_hold accepted card not in holds")
    except IllegalAction as e:
        check(e.code == "not_in_holds", f"rejected; code={e.code}")


# === Test 4: Decline with only one Ready prince ============================
def test_decline_one_prince():
    section("Veche Decline with only Andrey Ready")
    s = load_scenario("return_of_the_prince", seed=1)
    # Andrey starts on Calendar, Aleksandr is Mustered.
    # Force just Andrey ready; aleksandr off-Calendar (mustered).
    levy_box = next(cb.box for cb in s.calendar.boxes if cb.has_levy_campaign_marker)
    # Move andrey cylinder to Levy box.
    for cb in s.calendar.boxes:
        if "andrey" in cb.cylinders:
            cb.cylinders.remove("andrey")
    s.calendar.boxes[levy_box - 1].cylinders.append("andrey")
    s.lords["andrey"].state = "ready"
    s.meta.phase = "levy"
    s.meta.levy_step = "call_to_arms"
    s.meta.active_player = "russian"
    s.veche.acted_this_call_to_arms = False
    pre_vp = s.veche.vp_markers
    res = apply_action(s, {"type": "veche_action", "side": "russian", "args": {"option": "D"}})
    check(res["slid"] == ["andrey"], f"Decline slid only andrey; got {res['slid']}")
    check(s.veche.vp_markers == min(8, pre_vp + 1),
          f"Veche VP +1; got delta {s.veche.vp_markers - pre_vp}")


# === Test 5: Decline rejects when both princes not Ready ===================
def test_decline_neither_ready():
    section("Veche Decline rejects when neither prince Ready")
    s = load_scenario("return_of_the_prince", seed=1)
    # Move both princes off-Calendar.
    for prince in ("aleksandr", "andrey"):
        for cb in s.calendar.boxes:
            if prince in cb.cylinders:
                cb.cylinders.remove(prince)
        s.lords[prince].state = "mustered"
        s.lords[prince].location = "novgorod"
    s.meta.phase = "levy"
    s.meta.levy_step = "call_to_arms"
    s.meta.active_player = "russian"
    s.veche.acted_this_call_to_arms = False
    try:
        apply_action(s, {"type": "veche_action", "side": "russian", "args": {"option": "D"}})
        BUGS.append("Decline accepted with neither prince Ready")
    except IllegalAction as e:
        check(e.code == "decline_unavailable", f"rejected; code={e.code}")


# === Test 6: cmd_pass when 0 actions remaining ==============================
def test_pass_with_zero_actions():
    section("cmd_pass with 0 actions")
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "teutonic"
    s.campaign_turn.next_to_reveal = "teutonic"
    s.campaign_turn.active_card = teu
    s.campaign_turn.active_lord = teu
    s.campaign_turn.actions_remaining = 0
    s.campaign_turn.in_feed_pay_disband = False
    # cmd_pass should fail because no_actions_left.
    try:
        apply_action(s, {"type": "cmd_pass", "side": "teutonic",
                          "args": {"lord_id": teu}})
        # Pass might be allowed even with 0 actions; check outcome.
        check(s.campaign_turn.in_feed_pay_disband,
              "cmd_pass with 0 actions transitioned to FPD anyway")
    except IllegalAction as e:
        check(e.code == "no_actions_left",
              f"cmd_pass with 0 actions rejected; code={e.code}")


# === Test 7: sail to non-Seaport rejected ===================================
def test_sail_non_seaport():
    section("Sail to non-Seaport rejected")
    s = load_scenario("watland", seed=1)
    s.meta.box = 1  # summer
    teu = next(lid for lid, l in s.lords.items()
               if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].location = "riga"  # seaport
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "teutonic"
    s.campaign_turn.next_to_reveal = "teutonic"
    s.campaign_turn.active_card = teu
    s.campaign_turn.active_lord = teu
    s.campaign_turn.actions_remaining = 3
    s.campaign_turn.in_feed_pay_disband = False
    try:
        apply_action(s, {"type": "cmd_sail", "side": "teutonic",
                          "args": {"lord_id": teu, "destination": "novgorod"}})
        # Novgorod is NOT a seaport per locales.
        BUGS.append("Sail to non-Seaport (novgorod) accepted")
    except IllegalAction as e:
        check(e.code == "not_seaport", f"rejected; code={e.code}")


# === Test 8: Levy capability with 'no_event' card ==========================
def test_levy_capability_no_event_card():
    section("levy_capability rejects No-Event card")
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.meta.phase = "levy"
    s.meta.levy_step = "muster"
    s.meta.active_player = "teutonic"
    # Place a no-event card in deck.
    s.decks.teutonic.deck.append("T_no_event_1")
    try:
        apply_action(s, {"type": "levy_capability", "side": "teutonic",
                          "args": {"by_lord": teu, "card_id": "T_no_event_1"}})
        BUGS.append("levy_capability accepted no-event card")
    except IllegalAction as e:
        check(e.code == "bad_card", f"rejected; code={e.code}")


# === Test 9: Pay with 0 units ==============================================
def test_pay_zero_units():
    section("Pay with 0 units rejected")
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].assets["coin"] = 5
    s.meta.phase = "levy"
    s.meta.levy_step = "pay"
    s.meta.active_player = "teutonic"
    try:
        apply_action(s, {"type": "pay_with_coin", "side": "teutonic",
                          "args": {"from": f"lord:{teu}", "target_lord": teu, "units": 0}})
        BUGS.append("Pay accepted 0 units")
    except IllegalAction as e:
        check(e.code == "bad_units", f"rejected; code={e.code}")


# === Test 10: muster_lord roll determinism =================================
def test_muster_roll_deterministic():
    section("muster_lord roll determinism (same seed -> same roll)")
    rolls = []
    for _ in range(2):
        s = load_scenario("watland", seed=99)
        apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
        apply_action(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})
        s.meta.phase = "levy"
        s.meta.levy_step = "muster"
        s.meta.active_player = "teutonic"
        # Place Heinrich on Calendar and try to muster him via knud_and_abel.
        # Heinrich is mustered at start in watland.
        if s.lords["heinrich"].state == "mustered":
            s.lords["heinrich"].state = "ready"
            s.lords["heinrich"].location = None
            for cb in s.calendar.boxes:
                if "heinrich" not in cb.cylinders:
                    pass
            levy_box = next(cb.box for cb in s.calendar.boxes if cb.has_levy_campaign_marker)
            s.calendar.boxes[levy_box - 1].cylinders.append("heinrich")
        # heinrich seat is reval/wesenberg; pick one with no enemy.
        try:
            res = apply_action(s, {
                "type": "muster_lord", "side": "teutonic",
                "args": {"by_lord": "knud_and_abel",
                         "target_lord": "heinrich", "seat": "reval"},
            })
            rolls.append(res.get("roll"))
        except IllegalAction as e:
            print(f"  muster failed: {e}")
            return
    check(len(rolls) == 2 and rolls[0] == rolls[1],
          f"Same seed -> same muster roll; got {rolls}")


def main():
    test_novgorod_sack_strong_force()
    test_serfs_only_battle()
    test_play_hold_not_in_holds()
    test_decline_one_prince()
    test_decline_neither_ready()
    test_pass_with_zero_actions()
    test_sail_non_seaport()
    test_levy_capability_no_event_card()
    test_pay_zero_units()
    test_muster_roll_deterministic()
    print(f"\n{'=' * 60}\nBUGS: {len(BUGS)}\n{'=' * 60}")
    for b in BUGS:
        print(f"  {b}")
    return 0 if not BUGS else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
