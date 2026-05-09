"""TEST FIXTURE / engine-soundness smoke driver — NOT part of the shipped harness.

Watland — playing as the LLM consumer with real strategic judgment.

Setup (box 4, Early Winter 1240):
  T VP: 4 (Pskov 2 + Izborsk 1 + Pskov-rav .5 + Dubrovno-rav .5)
  R VP: 1 (Veche marker)
  T mustered: Andreas@Fellin (Marshal cmd 3), Yaroslav@Pskov (Disbands box 5),
              Knud&Abel@Wesenberg (Disbands box 6)
  R mustered: Domash@Novgorod, Vladislav@Ladoga
  T calendar: Heinrich/Rudolf box 4, Hermann box 8
  R calendar: Karelians box 4, Andrey box 5, Aleksandr box 7

Watland 2E victory: T win iff T_VP >= 7 AND T_VP >= 2*R_VP. Else R wins.
T at 4 needs +3, but defender prevention raises R from 1 — so probably +4.

PLAN:
  Teutons:
    - Levy: Halbbrueder on Andreas (Sergeants/MaA Armor +1); Treaty of
      Stensby (T1 — both Knud&Abel and Heinrich +1 cmd). Muster Rudolf
      at Wenden, Heinrich at Leal/Reval.
    - Andreas Fellin -> Koporye (R castle): ~3-hop march. T1 march, T2
      arrive at adjacent locale + place Siege, T3 Storm. Castle conquest
      worth +1 VP and removes R castle (-1 R VP).
    - Knud & Abel Sail Wesenberg -> Reval/Narwia/Pernau coastal pressure.
      Sail is Seaport->Seaport entire card. He has Ships.
    - Yaroslav Tax at Pskov (T-conquered, his Seat-by-Capability — no,
      Pskov Russian-territory). Just sit and Forage. Disbands box 5.
  Russians:
    - Levy: Stone Kremlin (R18) on Domash for Walls +1 at Novgorod.
      Black Sea Trade (R8) for Coin engine. Druzhina (R5/R6) on Aleksandr
      when he arrives. Possibly Steppe Warriors (R10) for Mongol vassals.
    - Veche: spend 1 VP marker to shift Andrey left (he's box 5 -> 3),
      bring him in earlier.
    - Vladislav: raid Estonia. Ladoga -> Karelia? -> Wesenberg? raid
      Wesenberg-area for ½ VP each. Disbands box 6.
    - Domash: hold Novgorod.
    - Karelians: muster, raid south.
"""
from __future__ import annotations
import json, sys, time
from copy import deepcopy
from nevsky.scenarios import load_scenario, set_optional_rule, determine_scenario_winner
from nevsky.actions import apply_action, IllegalAction
from nevsky.legal_moves import legal_moves
from nevsky.render import render_summary, lord_combat_summary, paths_from
from nevsky.previews import vp_forecast
from nevsky.static_data import load_cards


def step(s, act, expect_illegal=False, label=""):
    try:
        r = apply_action(s, act)
        head = json.dumps(r, default=str)[:90]
        print(f"  OK {act['type']:25} {label}-> {head}")
        return r
    except IllegalAction as e:
        if not expect_illegal:
            print(f"  IL {act['type']:25} {label}-> {e.code}: {e}")
        return None


def implement_drawn(s, side):
    """My capability picks for Watland.
    Teu priorities: T1 Treaty of Stensby (Heinrich/Knud cmd+1),
                    T9/T10 Halbbrueder (Andreas/Hermann),
                    T7/T15 Warrior Monks (Andreas/Hermann),
                    T11 Crusade (Andreas Summer Crusader vassals),
                    T18 Cogs (Knud&Abel Ships+).
    Rus priorities: R8 Black Sea Trade (side-wide Coin),
                    R18 Stone Kremlin (Domash Walls+1),
                    R5/R6 Druzhina (Aleksandr/Andrey when in),
                    R10 Steppe Warriors (Mongol vassals)."""
    cards = load_cards()
    deck = s.decks.teutonic if side == "teutonic" else s.decks.russian
    while deck.pending_draw:
        cid = deck.pending_draw[0]
        c = cards[cid]
        scope = c["capability_scope"]
        cap = c["capability_name"]
        if side == "teutonic":
            # Pin this_lord caps on Andreas (the hammer).
            pin = "andreas"
            if cap in ("Cogs",):
                pin = "knud_and_abel"
        else:
            pin = "domash"  # Stone Kremlin, defending lord
            if cap in ("Druzhina", "Steppe Warriors"):
                # Defer to Aleksandr if available, else Domash.
                pin = "aleksandr" if s.lords["aleksandr"].state == "mustered" else "domash"
            elif cap == "Luchniki":
                pin = "vladislav"
        print(f"  -> impl {cid}({cap},{scope}) for {side}, pin={pin}")
        if scope == "side_wide":
            r = step(s, {"type": "aow_implement_card", "side": side, "args": {}})
        elif scope == "this_lord":
            r = step(s, {"type": "aow_implement_card", "side": side,
                         "args": {"lord_id": pin}})
        else:
            deck.pending_draw.pop(0); deck.discard.append(cid); continue
        if r is None and deck.pending_draw and deck.pending_draw[0] == cid:
            deck.pending_draw.pop(0); deck.discard.append(cid)


def levy_phase(s, turn):
    print(f"\n=== TURN {turn} LEVY (box {s.meta.box}) ===")
    step(s, {"type": "aow_shuffle", "side": "teutonic", "args": {}})
    step(s, {"type": "aow_draw", "side": "teutonic", "args": {}})
    print(f"  Teu drew: {s.decks.teutonic.pending_draw}")
    implement_drawn(s, "teutonic")
    step(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    step(s, {"type": "aow_shuffle", "side": "russian", "args": {}})
    step(s, {"type": "aow_draw", "side": "russian", "args": {}})
    print(f"  Rus drew: {s.decks.russian.pending_draw}")
    implement_drawn(s, "russian")
    step(s, {"type": "advance_step", "side": "russian", "args": {}})
    # pay
    step(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    step(s, {"type": "advance_step", "side": "russian", "args": {}})
    # disband
    step(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    step(s, {"type": "advance_step", "side": "russian", "args": {}})
    # muster — try one Lord per side
    moves = legal_moves(s, with_previews=False)
    teu_musters = [m for m in moves if m["type"] == "muster_lord"]
    if teu_musters:
        # Prefer mustering the strongest available Lord.
        # Heinrich/Rudolf are box-4 ready in Watland.
        chosen = next((m for m in teu_musters if m["args"]["target_lord"] == "heinrich"), teu_musters[0])
        step(s, chosen)
    step(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    moves = legal_moves(s, with_previews=False)
    veche_b = [m for m in moves if m["type"] == "veche_action" and m["args"].get("option") == "B"]
    if veche_b:
        # Russians: auto-muster Karelians at Karelia (or whoever is ready).
        step(s, veche_b[0])
    moves = legal_moves(s, with_previews=False)
    rus_musters = [m for m in moves if m["type"] == "muster_lord"]
    if rus_musters:
        step(s, rus_musters[0], expect_illegal=True)
    step(s, {"type": "advance_step", "side": "russian", "args": {}})
    # call_to_arms
    step(s, {"type": "legate_skip", "side": "teutonic", "args": {}})
    step(s, {"type": "aow_discard_this_levy", "side": "teutonic", "args": {}})
    step(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    # Russian Veche choices: shift Andrey left if option A available; else skip.
    moves = legal_moves(s, with_previews=False)
    veche_a = [m for m in moves
                if m["type"] == "veche_action"
                and m["args"].get("option") == "A"
                and m["args"].get("target_lord") == "andrey"]
    if veche_a:
        step(s, veche_a[0])
    else:
        veche_a_aleks = [m for m in moves
                          if m["type"] == "veche_action"
                          and m["args"].get("option") == "A"
                          and m["args"].get("target_lord") == "aleksandr"]
        if veche_a_aleks:
            step(s, veche_a_aleks[0])
        else:
            step(s, {"type": "veche_action", "side": "russian", "args": {"option": "skip"}}, expect_illegal=True)
    step(s, {"type": "aow_discard_this_levy", "side": "russian", "args": {}})
    step(s, {"type": "advance_step", "side": "russian", "args": {}})


def make_plan(s, turn):
    """Plan: order Lords by tactical priority. Andreas (storming hammer)
    first. Knud & Abel (sailor) middle. Yaroslav last (he Disbands soon).
    Russians: Vladislav first (raids), Domash (defend), Aleksandr/Andrey
    when present."""
    from nevsky.campaign import _plan_target_size
    target = _plan_target_size(s.meta.box)
    print(f"\n=== TURN {turn} PLAN (size {target}) ===")
    # Teu: prioritize cards that need actions (Andreas marching), pad pass.
    teu_priority = ["andreas", "knud_and_abel", "heinrich", "rudolf", "yaroslav", "hermann"]
    teu_plan = []
    for lid in teu_priority:
        if (lid in s.lords and s.lords[lid].state == "mustered"
                and lid not in teu_plan):
            teu_plan.append(lid)
        if len(teu_plan) == target:
            break
    while len(teu_plan) < target:
        teu_plan.append("pass")
    teu_plan = teu_plan[:target]
    for c in teu_plan:
        step(s, {"type": "plan_add_card", "side": "teutonic", "args": {"card": c}}, expect_illegal=True)
    step(s, {"type": "finalize_plan", "side": "teutonic", "args": {}})
    # Rus
    rus_priority = ["vladislav", "aleksandr", "andrey", "domash", "karelians", "gavrilo"]
    rus_plan = []
    for lid in rus_priority:
        if (lid in s.lords and s.lords[lid].state == "mustered"
                and lid not in rus_plan):
            rus_plan.append(lid)
        if len(rus_plan) == target:
            break
    while len(rus_plan) < target:
        rus_plan.append("pass")
    rus_plan = rus_plan[:target]
    for c in rus_plan:
        step(s, {"type": "plan_add_card", "side": "russian", "args": {"card": c}}, expect_illegal=True)
    step(s, {"type": "finalize_plan", "side": "russian", "args": {}})


def execute_lord(s, side, active):
    """Per-Lord strategy:
    - Andreas: Fellin -> Koporye (R castle). Once at Koporye, Storm.
    - Knud & Abel: Sail Wesenberg -> Reval/Pernau coastal. If at Russian
      Seaport (Neva/Luga), threaten + Storm.
    - Yaroslav: Tax/Forage at Pskov; ravage to flip a marker.
    - Heinrich/Rudolf: support march toward Vod/Karelia.
    - Vladislav: raid Estonia (Adsel/Wesenberg vicinity for ½ VP each).
    - Domash: hold Novgorod.
    - Aleksandr/Andrey: when on map, march toward most threatened
      Russian locale OR counterattack into Estonia."""
    if active not in s.lords:
        step(s, {"type": "cmd_pass", "side": side, "args": {"lord_id": active}}, expect_illegal=True)
        return
    lord = s.lords[active]
    loc = lord.location
    if loc is None:
        step(s, {"type": "cmd_pass", "side": side, "args": {"lord_id": active}}, expect_illegal=True)
        return

    # Lord-specific destinations.
    target = None
    if active == "andreas":
        # If at Koporye and besieged, Storm. Else march toward Koporye.
        target = "koporye"
    elif active == "knud_and_abel":
        # If at Wesenberg (own Seaport), Sail to Pernau or Narwia (closer
        # to Russian heart). Or just stay and threaten.
        # Try Sail to a useful Seaport.
        # For simplicity, try to move toward neva.
        target = "neva"
    elif active == "vladislav":
        # Raid Estonia: march toward Wesenberg or Adsel.
        target = "adsel"
    elif active == "aleksandr" or active == "andrey":
        # Counterattack: march toward closest T-conquered or T-ravaged
        # Russian locale.
        # Pskov is T-conquered. Vod/Sablia/Tesovo are T-ravaged.
        target = "pskov"
    elif active == "domash":
        target = None  # hold
    elif active == "karelians":
        target = "kaibolovo"  # raid south for ½ VP
    elif active in ("heinrich", "rudolf", "hermann"):
        # Support drive south.
        target = "koporye"
    elif active == "yaroslav":
        # Hold Pskov; ravage Russian neighbor for ½ VP if possible.
        # Actually Yaroslav is at Pskov which is already T-Conquered + T-rav.
        # His best move: ravage adjacent locale like Ostrov (Russian terr).
        target = "ostrov"
    
    if target is None:
        # Pass.
        step(s, {"type": "cmd_pass", "side": side, "args": {"lord_id": active}}, expect_illegal=True)
        return

    # If at target with Siege > 0 not besieged, Storm.
    if loc == target and s.locales[loc].siege_markers > 0:
        from nevsky.campaign import _is_besieged
        if not _is_besieged(s, active):
            fc = vp_forecast(s, {"type": "cmd_storm", "side": side,
                                  "args": {"lord_id": active}}, preview_trials=10)
            note = fc.get("note", "?")
            print(f"     storm forecast: {note}")
            r = step(s, {"type": "cmd_storm", "side": side,
                          "args": {"lord_id": active}}, expect_illegal=True)
            if r is not None:
                return

    # If at target without siege, the next March will place one. We're
    # already there → just pass / consider Ravage.
    if loc == target:
        # Already at target. Try Ravage if Russian terr.
        try:
            from nevsky.static_data import load_locales
            stat = load_locales().get(loc, {})
            if stat.get("territory") == ("russian" if side == "teutonic" else "teutonic"):
                r = step(s, {"type": "cmd_ravage", "side": side,
                              "args": {"lord_id": active, "locale_id": loc}}, expect_illegal=True)
                if r is not None and not (isinstance(r, dict) and "_il" in str(r)):
                    return
        except Exception:
            pass
        step(s, {"type": "cmd_pass", "side": side, "args": {"lord_id": active}}, expect_illegal=True)
        return

    # Compute path.
    paths = paths_from(s, loc, max_hops=5)
    if target not in paths or not paths[target]:
        # Unreachable; pass.
        step(s, {"type": "cmd_pass", "side": side, "args": {"lord_id": active}}, expect_illegal=True)
        return
    next_hop = paths[target][0]
    r = step(s, {"type": "cmd_march", "side": side,
                  "args": {"lord_id": active, "to": next_hop}}, expect_illegal=True)
    if isinstance(r, dict) and "_il" in str(r):
        # March failed (winter sleds, transport issue). Pass.
        step(s, {"type": "cmd_pass", "side": side, "args": {"lord_id": active}}, expect_illegal=True)
        return
    # If actions remain and combat_pending isn't set, try one more hop.
    inner = 3
    while (inner > 0 and s.campaign_turn.actions_remaining > 0
            and s.combat_pending is None
            and active in s.lords
            and s.lords[active].location is not None
            and s.lords[active].location != target):
        inner -= 1
        cur = s.lords[active].location
        paths2 = paths_from(s, cur, max_hops=5)
        if target not in paths2 or not paths2[target]:
            break
        hop = paths2[target][0]
        r2 = step(s, {"type": "cmd_march", "side": side,
                       "args": {"lord_id": active, "to": hop}}, expect_illegal=True)
        if isinstance(r2, dict) and "_il" in str(r2):
            break
    if (s.lords.get(active) and s.campaign_turn.actions_remaining > 0
            and not s.campaign_turn.in_feed_pay_disband
            and s.combat_pending is None):
        step(s, {"type": "cmd_pass", "side": side, "args": {"lord_id": active}}, expect_illegal=True)


def handle_combat_pending(s):
    cp = s.combat_pending
    if cp is None: return
    side = cp.pending_response_by
    # I'd avoid Battle if outnumbered; otherwise Withdraw if I have a Stronghold.
    fc = vp_forecast(s, {"type": "stand_battle", "side": side, "args": {}}, preview_trials=10)
    prev = fc.get("preview") or {}
    win = prev.get("attacker_winrate" if side == cp.attacker_side else "defender_winrate", 0)
    print(f"     CP {cp.from_locale}->{cp.to_locale}: my win = {win:.0%}")
    if win >= 0.5:
        step(s, {"type": "stand_battle", "side": side, "args": {}}, expect_illegal=True)
        return
    if not cp.laden:
        moves = legal_moves(s, with_previews=False)
        avoid = [m for m in moves if m["type"] == "avoid_battle"]
        if avoid:
            step(s, avoid[0], expect_illegal=True); return
    r = step(s, {"type": "withdraw", "side": side, "args": {}}, expect_illegal=True)
    if r is None:
        step(s, {"type": "stand_battle", "side": side, "args": {}}, expect_illegal=True)


def activations(s, turn):
    print(f"\n=== TURN {turn} ACTIVATIONS ===")
    safety = 80
    cp_safety = 6
    while s.meta.campaign_step == "command" and safety > 0:
        if s.combat_pending is not None:
            cp_safety -= 1
            if cp_safety <= 0:
                step(s, {"type": "stand_battle",
                          "side": s.combat_pending.pending_response_by,
                          "args": {}}, expect_illegal=True)
                cp_safety = 6; continue
            handle_combat_pending(s); continue
        cp_safety = 6
        side = s.campaign_turn.next_to_reveal
        prev_seq = s.meta.sequence
        if not s.campaign_turn.in_feed_pay_disband:
            step(s, {"type": "command_reveal", "side": side, "args": {}}, expect_illegal=True)
            active = s.campaign_turn.active_lord
            if active:
                print(f"  >> {side}/{active} actions={s.campaign_turn.actions_remaining}")
                execute_lord(s, side, active)
            if s.campaign_turn.actions_remaining > 0 and not s.campaign_turn.in_feed_pay_disband:
                step(s, {"type": "end_card", "side": side, "args": {}}, expect_illegal=True)
        step(s, {"type": "fpd_resolve", "side": "teutonic", "args": {}}, expect_illegal=True)
        step(s, {"type": "fpd_resolve", "side": "russian", "args": {}}, expect_illegal=True)
        if s.meta.sequence == prev_seq:
            break
        safety -= 1
    if s.meta.campaign_step == "end_campaign":
        step(s, {"type": "end_campaign_resolve", "side": "teutonic", "args": {}})
        step(s, {"type": "end_campaign_resolve", "side": "russian", "args": {}})
    print(f"  end of turn {turn}: T={s.calendar.teutonic_vp} R={s.calendar.russian_vp} box={s.meta.box}")


# ========================================================================
print("=" * 70)
print("WATLAND — LLM-driven play (Teutons aggressor, 5 turns)")
print("=" * 70)
s = load_scenario("watland", seed=1)
step(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
step(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})
print(render_summary(s))

turn = 1
while s.meta.box <= s.meta.span_end_box and turn <= 6:
    if s.meta.phase != "levy":
        break
    levy_phase(s, turn)
    make_plan(s, turn)
    activations(s, turn)
    turn += 1

print("\n" + "=" * 70)
print("END OF SCENARIO")
print("=" * 70)
final = determine_scenario_winner(s)
print(f"Final: {json.dumps(final, indent=2)}")
print(f"Conquered: {[(lid, loc.teutonic_conquered or 0, loc.russian_conquered or 0) for lid, loc in s.locales.items() if loc.teutonic_conquered or loc.russian_conquered]}")
print(f"Ravaged Russian-color: {[lid for lid, loc in s.locales.items() if loc.russian_ravaged]}")
print(f"Ravaged Teutonic-color: {[lid for lid, loc in s.locales.items() if loc.teutonic_ravaged]}")
print(f"Removed lords T={[lid for lid,l in s.lords.items() if l.side=='teutonic' and l.state=='removed']}")
print(f"               R={[lid for lid,l in s.lords.items() if l.side=='russian' and l.state=='removed']}")
