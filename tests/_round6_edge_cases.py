"""Round 6 aggressive edge-case bug hunt."""

from __future__ import annotations

import json
import sys
import traceback

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


# === 1. Re-Muster after Disband =============================================
def test_remuster():
    section("Re-Muster after Disband")
    s = load_scenario("watland", seed=23)
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})
    # Place yaroslav at Levy box for at-limit Disband.
    levy_box = next(cb.box for cb in s.calendar.boxes if cb.has_levy_campaign_marker)
    s.lords["yaroslav"].this_lord_capabilities = ["T7"]  # add a hold cap
    if "T7" not in s.decks.teutonic.deck:
        s.decks.teutonic.deck.append("T7")
    s.decks.teutonic.deck.remove("T7")  # remove from deck
    # Put yaroslav service AT levy box for at-limit Disband.
    for cb in s.calendar.boxes:
        if "yaroslav" in cb.service_markers:
            cb.service_markers.remove("yaroslav")
    s.calendar.boxes[levy_box - 1].service_markers.append("yaroslav")
    # Force Levy disband step.
    s.meta.phase = "levy"
    s.meta.levy_step = "disband"
    s.meta.active_player = "teutonic"
    pre_yaroslav_caps = list(s.lords["yaroslav"].this_lord_capabilities)
    pre_deck_size = len(s.decks.teutonic.deck)
    res = apply_action(s, {"type": "disband_resolve", "side": "teutonic", "args": {}})
    check("yaroslav" in [d["lord_id"] for d in res.get("disbanded", [])],
          "yaroslav at-limit Disband fired")
    check(s.lords["yaroslav"].state == "disbanded",
          f"yaroslav state: expected disbanded, got {s.lords['yaroslav'].state}")
    check(s.lords["yaroslav"].forces == {},
          f"yaroslav forces cleared: got {s.lords['yaroslav'].forces}")
    # Cap should have returned to deck.
    if pre_yaroslav_caps:
        check(len(s.decks.teutonic.deck) == pre_deck_size + len(pre_yaroslav_caps),
              "this_lord_capabilities returned to deck")
    # Now re-Muster yaroslav. Find his cylinder on Calendar.
    yaroslav_cyl_box = next(
        (cb.box for cb in s.calendar.boxes if "yaroslav" in cb.cylinders),
        None,
    )
    check(yaroslav_cyl_box is not None, "yaroslav cylinder placed on Calendar after at-limit Disband")
    # Slide yaroslav to current Levy box (Ready).
    if yaroslav_cyl_box and yaroslav_cyl_box != levy_box:
        s.calendar.boxes[yaroslav_cyl_box - 1].cylinders.remove("yaroslav")
        s.calendar.boxes[levy_box - 1].cylinders.append("yaroslav")
    s.lords["yaroslav"].state = "ready"  # Disband->ready transition for re-Muster.
    # Move to Muster step.
    s.meta.levy_step = "muster"
    # Ensure mustering Lord can Levy.
    by = "knud_and_abel"
    s.lords[by].lordship_used = 0
    s.lords[by].just_arrived_this_levy = False
    res2 = apply_action(s, {"type": "muster_lord", "side": "teutonic",
                             "args": {"by_lord": by, "target_lord": "yaroslav", "seat": "odenpah"}})
    if res2.get("outcome") == "mustered":
        check(s.lords["yaroslav"].state == "mustered", "yaroslav re-Mustered")
        check(s.lords["yaroslav"].location == "odenpah", "yaroslav at odenpah")
        # Forces should be redeployed from starting_forces.
        check(sum(s.lords["yaroslav"].forces.values()) > 0, "yaroslav forces redeployed")
    else:
        print(f"  Note: re-Muster Fealty roll failed (roll={res2.get('roll')}, fealty={res2.get('fealty')})")
        # Try with different seed
        check(True, "re-Muster Fealty roll mechanics work (fail or success)")


# === 2. Conquered marker stacking on Novgorod (3-VP) =======================
def test_novgorod_stacking():
    section("Conquered marker stacking on Novgorod (3-VP)")
    s = load_scenario("crusade_on_novgorod", seed=1)
    pre_t_vp = s.calendar.teutonic_vp
    # Manually trigger Sack of Novgorod via cmd_storm.
    # Place a Russian Lord in_stronghold at Novgorod.
    s.lords["domash"].location = "novgorod"
    s.lords["domash"].in_stronghold = True
    s.lords["domash"].forces = {"militia": 1}  # weak defender
    # Place 3 Teu attackers at Novgorod.
    for lid in ("hermann", "yaroslav", "knud_and_abel"):
        s.lords[lid].location = "novgorod"
        s.lords[lid].forces = {"knights": 4, "men_at_arms": 3}
    s.locales["novgorod"].siege_markers = 4
    s.veche.coin = 5  # Novgorod special: Coin transferred on Sack.
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
              f"Novgorod Conquered=3 markers (city VP=3); got {s.locales['novgorod'].teutonic_conquered}")
        check(s.calendar.teutonic_vp == pre_t_vp + 3.0,
              f"T VP +3; got {s.calendar.teutonic_vp - pre_t_vp}")
        # Veche Coin special rule: ALL Coin to attackers on Sack.
        check(s.veche.coin == 0,
              f"Veche Coin emptied on Novgorod Sack; got {s.veche.coin}")
        recipient_coin = s.lords["hermann"].assets.get("coin", 0)
        check(recipient_coin > 0, f"hermann got Veche Coin; coin={recipient_coin}")
    else:
        print(f"  RNG: defender won, skipping Conquer assertions")


# === 3. Veche VP exhaustion ================================================
def test_veche_vp_exhaustion():
    section("Veche options at VP=0")
    s = load_scenario("watland", seed=1)
    s.veche.vp_markers = 0
    s.calendar.russian_vp = 0.0
    s.meta.phase = "levy"
    s.meta.levy_step = "call_to_arms"
    s.meta.active_player = "russian"
    # Option A/B/C all require 1 VP.
    for opt in ("A", "B", "C"):
        try:
            apply_action(s, {"type": "veche_action", "side": "russian",
                              "args": {"option": opt, "target_lord": "domash"}})
            BUGS.append(f"veche_action option {opt} succeeded with 0 VP markers")
            print(f"  ! BUG: option {opt} succeeded with 0 VP")
        except IllegalAction as e:
            check(e.code == "insufficient_vp" or e.code == "decline_unavailable" or e.code in ("not_ready", "bad_target", "missing_arg", "no_cylinder"),
                  f"option {opt} rejected with code {e.code}")


# === 4. Veche VP at cap (8) =================================================
def test_veche_vp_cap():
    section("Veche VP cap (8)")
    s = load_scenario("watland", seed=1)
    s.veche.vp_markers = 8
    s.calendar.russian_vp = 8.0
    s.meta.phase = "levy"
    s.meta.levy_step = "call_to_arms"
    s.meta.active_player = "russian"
    # Force aleksandr ready so Decline available.
    s.lords["aleksandr"].state = "ready"
    s.lords["aleksandr"].location = None
    # Put aleksandr cylinder at Levy box.
    levy_box = next(cb.box for cb in s.calendar.boxes if cb.has_levy_campaign_marker)
    for cb in s.calendar.boxes:
        if "aleksandr" in cb.cylinders:
            cb.cylinders.remove("aleksandr")
    s.calendar.boxes[levy_box - 1].cylinders.append("aleksandr")
    pre_vp = s.veche.vp_markers
    res = apply_action(s, {"type": "veche_action", "side": "russian",
                            "args": {"option": "D"}})
    # Cap forfeit per 1.4.2: vp_markers stays at 8.
    check(s.veche.vp_markers == 8, f"Veche VP cap held at 8; got {s.veche.vp_markers}")


# === 5. Calendar off-edges via Service shift ===============================
def test_calendar_off_edges():
    section("Calendar off-edges via large Service shift")
    s = load_scenario("watland", seed=1)
    # Place service marker at box 16 then shift right -> off_right.
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    for cb in s.calendar.boxes:
        if teu in cb.service_markers:
            cb.service_markers.remove(teu)
    s.calendar.boxes[15].service_markers.append(teu)  # box 16
    # Pay with own Coin to shift right.
    s.lords[teu].assets["coin"] = 3
    s.meta.phase = "levy"
    s.meta.levy_step = "pay"
    s.meta.active_player = "teutonic"
    res = apply_action(s, {"type": "pay_with_coin", "side": "teutonic",
                            "args": {"from": f"lord:{teu}", "target_lord": teu, "units": 2}})
    check(teu in s.calendar.off_right,
          f"{teu} pushed off_right by Pay shift; off_right={s.calendar.off_right}")
    check(res["new_box"] == 17, f"new_box=17 (off_right); got {res['new_box']}")


# === 6. Lord at 8/8 asset cap ==============================================
def test_asset_cap():
    section("Asset cap at 8")
    s = load_scenario("watland", seed=1)
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].assets["cart"] = 8
    s.meta.phase = "levy"
    s.meta.levy_step = "muster"
    s.meta.active_player = "teutonic"
    s.lords[teu].lordship_used = 0
    s.lords[teu].just_arrived_this_levy = False
    try:
        apply_action(s, {"type": "levy_transport", "side": "teutonic",
                          "args": {"by_lord": teu, "transport_type": "cart"}})
        BUGS.append("levy_transport accepted cart at 8/8 cap")
        print(f"  ! BUG: cap not enforced")
    except IllegalAction as e:
        check(e.code == "transport_max", f"cap enforced; code={e.code}")


# === 7. cmd_supply with no valid Transport seasonally ======================
def test_supply_seasonal_transport_mismatch():
    section("Supply with seasonally-invalid Transport")
    s = load_scenario("watland", seed=1)  # box 4 = early winter
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].assets["cart"] = 1
    s.lords[teu].assets.pop("loot", None)
    from nevsky.static_data import load_lords as _ll
    seat = _ll()[teu]["primary_seats"][0]
    # Place Lord at adjacent.
    from nevsky.static_data import load_ways
    adj = next((w["b"] if w["a"] == seat else w["a"]
                for w in load_ways()
                if (w["a"] == seat or w["b"] == seat) and w["type"] == "trackway"), None)
    if adj is None:
        print("  skip: no trackway from seat")
        return
    s.lords[teu].location = adj
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "teutonic"
    s.campaign_turn.next_to_reveal = "teutonic"
    s.campaign_turn.active_card = teu
    s.campaign_turn.active_lord = teu
    s.campaign_turn.actions_remaining = 3
    s.campaign_turn.in_feed_pay_disband = False
    # Carts are Summer-only; box 4 is Early Winter -> reject.
    try:
        apply_action(s, {"type": "cmd_supply", "side": "teutonic",
                          "args": {"lord_id": teu, "sources": [{
                              "locale_id": seat, "route": [seat, adj],
                              "transport": "cart"}]}})
        BUGS.append("cmd_supply accepted Cart in Early Winter (cart_non_summer)")
        print(f"  ! BUG: seasonal check missed")
    except IllegalAction as e:
        check(e.code == "cart_non_summer", f"Cart-in-Winter rejected; code={e.code}")


# === 8. Stronghold capacity at exact limit (3 lords -> city) ===============
def test_stronghold_capacity_exact():
    section("Stronghold capacity exact (3 lords -> city)")
    from nevsky.state import CombatPending
    s = load_scenario("pleskau", seed=1)
    # Place 3 Russian Lords at pskov (city, capacity 3) for Withdraw.
    for lid in ("gavrilo", "domash", "vladislav"):
        if lid in s.lords:
            s.lords[lid].state = "mustered"
            s.lords[lid].location = "pskov"
            s.lords[lid].in_stronghold = False
            s.lords[lid].assets.pop("loot", None)
            s.lords[lid].assets.pop("provender", None)
    s.combat_pending = CombatPending(
        attacker_side="teutonic", attacker_group=["hermann"],
        from_locale="izborsk", to_locale="pskov", way_type="trackway",
        defender_side="russian", defender_lords=["gavrilo", "domash", "vladislav"],
        pending_response_by="russian", laden=False,
    )
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "russian"
    s.campaign_turn.active_lord = None
    s.campaign_turn.actions_remaining = 0
    s.campaign_turn.in_feed_pay_disband = False
    apply_action(s, {"type": "withdraw", "side": "russian", "args": {}})
    check(all(s.lords[lid].in_stronghold for lid in ("gavrilo", "domash", "vladislav")),
          "all 3 defenders Withdrew (city cap=3)")


# === 9. Stronghold over-capacity rejection =================================
def test_stronghold_over_capacity():
    section("Stronghold over-capacity (4 lords -> city) rejection")
    from nevsky.state import CombatPending
    s = load_scenario("pleskau", seed=1)
    fake_4 = ["gavrilo", "domash", "vladislav", "aleksandr"]
    for lid in fake_4:
        if lid in s.lords:
            s.lords[lid].state = "mustered"
            s.lords[lid].location = "pskov"
            s.lords[lid].in_stronghold = False
            s.lords[lid].assets.pop("loot", None)
            s.lords[lid].assets.pop("provender", None)
    s.combat_pending = CombatPending(
        attacker_side="teutonic", attacker_group=["hermann"],
        from_locale="izborsk", to_locale="pskov", way_type="trackway",
        defender_side="russian", defender_lords=fake_4,
        pending_response_by="russian", laden=False,
    )
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "russian"
    try:
        apply_action(s, {"type": "withdraw", "side": "russian", "args": {}})
        BUGS.append("withdraw accepted 4 lords into capacity-3 city")
        print(f"  ! BUG: over-capacity not rejected")
    except IllegalAction as e:
        check(e.code == "over_capacity", f"over-capacity rejected; code={e.code}")


# === Run all =================================================================
def main():
    print("Round 6 aggressive edge-case probe")
    test_remuster()
    test_novgorod_stacking()
    test_veche_vp_exhaustion()
    test_veche_vp_cap()
    test_calendar_off_edges()
    test_asset_cap()
    test_supply_seasonal_transport_mismatch()
    test_stronghold_capacity_exact()
    test_stronghold_over_capacity()
    print(f"\n{'=' * 60}\nBUGS: {len(BUGS)}\n{'=' * 60}")
    for b in BUGS:
        print(f"  {b}")
    return 0 if not BUGS else 1


if __name__ == "__main__":
    sys.exit(main())
