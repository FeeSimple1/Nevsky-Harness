"""TEST FIXTURE / engine-soundness smoke driver — NOT part of the shipped harness.

Peipus full playthrough — Russians on the offensive, 4 turns.

Strategy (from Strategy reference + R18 helpers):
- Aleksandr + Andrey at Novgorod are the Russian hammer (3K each).
- Yaroslav alone at Pskov is the brittle Teuton.
- Plan: Aleksandr Marches Novgorod -> Sablia (or via Volkhov spine) -> Pskov.
  If Yaroslav Avoids/Withdraws into Pskov, Aleksandr Sieges (per Volko's
  advice: Yaroslav Disbands box 14 from short Service if denied Tax).
- Andrey supports Aleksandr or pushes a different VP target.
- Domash holds Novgorod. Karelians may raid (R12/R14 Raiders).
- Hermann at Dorpat is too far away to threaten in 4 turns.
"""
from __future__ import annotations
import json, traceback
from nevsky.scenarios import load_scenario
from nevsky.actions import apply_action, IllegalAction
from nevsky.legal_moves import legal_moves
from nevsky.render import render_summary, lord_combat_summary
from nevsky.previews import vp_forecast
from nevsky.static_data import load_cards


def step(s, act, expect_illegal=False, label=""):
    try:
        r = apply_action(s, act)
        head = json.dumps(r, default=str)[:120]
        print(f"  OK {act['type']:30} {label}-> {head}")
        return r
    except IllegalAction as e:
        if expect_illegal:
            return None
        print(f"  IL {act['type']:30} {label}-> {e.code}: {e}")
        return None


def implement_drawn(s, side):
    cards = load_cards()
    deck = s.decks.teutonic if side == "teutonic" else s.decks.russian
    while deck.pending_draw:
        cid = deck.pending_draw[0]
        c = cards[cid]
        scope = c["capability_scope"]
        cap = c["capability_name"]
        if side == "russian":
            # Russian priority: Druzhina/Streltsy on Aleksandr; Stone Kremlin on Domash.
            pin = "aleksandr"
            if cap == "Stone Kremlin":
                pin = "domash"
            elif cap == "Luchniki":
                pin = "karelians"
        else:
            pin = "hermann"
            if cap in ("Halbbrueder", "Warrior Monks", "Trebuchets", "Stonemasons"):
                pin = "hermann"
        if scope == "side_wide":
            r = step(s, {"type": "aow_implement_card", "side": side, "args": {}},
                     label=f"impl {cid}({cap}) ")
        elif scope == "this_lord":
            r = step(s, {"type": "aow_implement_card", "side": side,
                         "args": {"lord_id": pin}},
                     label=f"impl {cid}({cap}->{pin}) ")
        else:
            deck.pending_draw.pop(0); deck.discard.append(cid)
            r = "discard"
        if r is None and deck.pending_draw and deck.pending_draw[0] == cid:
            deck.pending_draw.pop(0); deck.discard.append(cid)


def levy_phase(s, turn=1):
    print(f"\n--- LEVY turn {turn} arts_of_war ---")
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
    # muster — both sides skip (no Mustering needed beyond what's already up).
    step(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    step(s, {"type": "advance_step", "side": "russian", "args": {}})
    # call_to_arms
    step(s, {"type": "legate_skip", "side": "teutonic", "args": {}})
    step(s, {"type": "aow_discard_this_levy", "side": "teutonic", "args": {}})
    step(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    step(s, {"type": "veche_action", "side": "russian", "args": {"option": "skip"}})
    step(s, {"type": "aow_discard_this_levy", "side": "russian", "args": {}})
    step(s, {"type": "advance_step", "side": "russian", "args": {}})


def make_plan(s, side, intended):
    from nevsky.campaign import _plan_target_size
    target = _plan_target_size(s.meta.box)
    plan = []
    for c in intended:
        if c == "pass":
            plan.append("pass")
        elif c in s.lords and s.lords[c].state == "mustered" and plan.count(c) == 0:
            plan.append(c)
        else:
            plan.append("pass")
    while len(plan) < target:
        plan.append("pass")
    plan = plan[:target]
    for c in plan:
        step(s, {"type": "plan_add_card", "side": side, "args": {"card": c}})
    step(s, {"type": "finalize_plan", "side": side, "args": {}})


def execute_lord_card(s, side, active):
    """Strategy:
    - Aleksandr / Andrey / Domash / Karelians: march toward Pskov via available
      shortest route, place Siege; or pass if already there.
    - Yaroslav: stay at Pskov (defender). Withdraw into stronghold if attacked.
    - Hermann at Dorpat: pass (no nearby threat to engage in 4 turns).
    """
    lord = s.lords[active]
    loc = lord.location
    # Print Lord summary so the LLM-style decision is informed.
    summary = lord_combat_summary(s, active)
    print(f"     loc={loc}, forces={summary.get('forces')}, "
          f"feed={summary.get('feed_cost_prov')} prov; service_box={summary.get('service_disband_box')}")

    # March toward Pskov for Russian offensive Lords.
    if side == "russian" and active in ("aleksandr", "andrey"):
        # Try to get to Pskov via shortest path. Novgorod -> Sablia/Tesovo -> ... -> Pskov.
        # Use legal_moves to see what's reachable.
        moves = legal_moves(s)
        march_options = [m for m in moves if m["type"] == "cmd_march"]
        # Prefer destinations that move toward the Russian heartland Pskov.
        # Path-finding: BFS from current location to "pskov".
        from nevsky.static_data import load_ways
        ways = load_ways()
        adj = {}
        for w in ways:
            adj.setdefault(w["a"], []).append(w["b"])
            adj.setdefault(w["b"], []).append(w["a"])
        # BFS
        visited = {loc: []}
        frontier = [loc]
        while frontier:
            new_front = []
            for n in frontier:
                for m in adj.get(n, []):
                    if m not in visited:
                        visited[m] = visited[n] + [m]
                        new_front.append(m)
                        if m == "pskov":
                            break
                if "pskov" in visited:
                    break
            frontier = new_front
            if "pskov" in visited:
                break
        path = visited.get("pskov", [])
        print(f"     path to pskov: {path}")
        if not path:
            step(s, {"type": "cmd_pass", "side": side, "args": {"lord_id": active}})
            return
        # March one hop. The cmd_march into an enemy stronghold ends the card
        # (places Siege). Otherwise we use up to actions_remaining-1 hops to
        # leave room for one more action (Storm or such).
        next_hop = path[0]
        step(s, {"type": "cmd_march", "side": side,
                 "args": {"lord_id": active, "to": next_hop}})
        # If still actions remaining and not yet at Pskov, hop again.
        while (s.lords[active].location != "pskov"
               and s.campaign_turn.actions_remaining > 0
               and len(path) > 1):
            path = visited[s.lords[active].location] if s.lords[active].location in visited else []
            # Re-BFS from current.
            visited2 = {s.lords[active].location: []}
            frontier2 = [s.lords[active].location]
            while frontier2:
                nf = []
                for n in frontier2:
                    for m in adj.get(n, []):
                        if m not in visited2:
                            visited2[m] = visited2[n] + [m]
                            nf.append(m)
                            if m == "pskov":
                                break
                    if "pskov" in visited2:
                        break
                frontier2 = nf
                if "pskov" in visited2:
                    break
            path = visited2.get("pskov", [])
            if not path:
                break
            r = step(s, {"type": "cmd_march", "side": side,
                         "args": {"lord_id": active, "to": path[0]}}, expect_illegal=True)
            if r is None:
                break
        # If actions remain and we're at Pskov besieging, Storm.
        if (s.lords[active].location == "pskov"
                and s.locales["pskov"].siege_markers > 0
                and s.campaign_turn.actions_remaining > 0):
            fc = vp_forecast(s, {"type": "cmd_storm", "side": side,
                                  "args": {"lord_id": active}}, preview_trials=30)
            print(f"     storm forecast: {fc.get('note')}")
            step(s, {"type": "cmd_storm", "side": side,
                     "args": {"lord_id": active}}, expect_illegal=True)
        if s.campaign_turn.actions_remaining > 0 and not s.campaign_turn.in_feed_pay_disband:
            step(s, {"type": "cmd_pass", "side": side, "args": {"lord_id": active}}, expect_illegal=True)
    else:
        step(s, {"type": "cmd_pass", "side": side, "args": {"lord_id": active}})


def activations(s, turn):
    print(f"\n--- TURN {turn} ACTIVATIONS ---")
    safety = 80
    while s.meta.campaign_step == "command" and safety > 0:
        # Combat-pending response branch.
        if s.combat_pending is not None:
            cp = s.combat_pending
            print(f"  CP: {cp.attacker_side} marching {cp.from_locale}->{cp.to_locale}; "
                  f"defender_lords={cp.defender_lords}; pending_response_by={cp.pending_response_by}")
            # Defender chooses: Withdraw if there's a Stronghold; else Stand.
            if cp.pending_response_by == "teutonic":
                # Yaroslav at Pskov defending: Withdraw into Pskov stronghold (it's
                # Teuton-Conquered, so Friendly to Teutons).
                step(s, {"type": "withdraw", "side": "teutonic", "args": {}}, expect_illegal=True)
                if s.combat_pending is not None:
                    step(s, {"type": "stand_battle", "side": "teutonic", "args": {}})
            else:
                step(s, {"type": "stand_battle", "side": "russian", "args": {}})
            continue
        side = s.campaign_turn.next_to_reveal
        if not s.campaign_turn.in_feed_pay_disband:
            step(s, {"type": "command_reveal", "side": side, "args": {}})
            active = s.campaign_turn.active_lord
            if active:
                print(f"\n  >> {side}/{active} actions={s.campaign_turn.actions_remaining}")
                execute_lord_card(s, side, active)
            if s.campaign_turn.actions_remaining > 0 and not s.campaign_turn.in_feed_pay_disband:
                step(s, {"type": "end_card", "side": side, "args": {}}, expect_illegal=True)
        step(s, {"type": "fpd_resolve", "side": "teutonic", "args": {}}, expect_illegal=True)
        step(s, {"type": "fpd_resolve", "side": "russian", "args": {}}, expect_illegal=True)
        safety -= 1
    if s.meta.campaign_step == "end_campaign":
        step(s, {"type": "end_campaign_resolve", "side": "teutonic", "args": {}})
        step(s, {"type": "end_campaign_resolve", "side": "russian", "args": {}})


# =======================================================================
print("=" * 70)
print("PEIPUS full playthrough — Russians on the offensive")
print("=" * 70)
s = load_scenario("peipus", seed=1)
step(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
step(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})
print()
print(render_summary(s))

turn = 1
while s.meta.box <= s.meta.span_end_box and turn <= 6:
    if s.meta.phase != "levy":
        break
    print(f"\n=== TURN {turn} (box {s.meta.box}) ===")
    levy_phase(s, turn=turn)
    print("\n" + render_summary(s))
    print(f"\n--- TURN {turn} PLAN ---")
    teu_intent = ["yaroslav", "hermann"] + ["pass"] * 6
    rus_intent = ["aleksandr", "andrey", "domash", "karelians"] + ["pass"] * 6
    make_plan(s, "teutonic", teu_intent)
    make_plan(s, "russian", rus_intent)
    activations(s, turn)
    turn += 1

print("\n\n=== END OF SCENARIO ===")
print(render_summary(s))
print(f"\nFinal VP: T={s.calendar.teutonic_vp}, R={s.calendar.russian_vp}")
print(f"Phase: {s.meta.phase}/{s.meta.campaign_step}, box: {s.meta.box}")
print(f"Removed Lords: T={[lid for lid,l in s.lords.items() if l.side=='teutonic' and l.state=='removed']}")
print(f"               R={[lid for lid,l in s.lords.items() if l.side=='russian' and l.state=='removed']}")
print(f"Conquest/ravage markers:")
for lid, loc in s.locales.items():
    if loc.teutonic_conquered or loc.russian_conquered or loc.teutonic_ravaged or loc.russian_ravaged or loc.siege_markers:
        print(f"  {lid}: T_conq={loc.teutonic_conquered} R_conq={loc.russian_conquered} "
              f"T_rav={loc.teutonic_ravaged} R_rav={loc.russian_ravaged} siege={loc.siege_markers}")
