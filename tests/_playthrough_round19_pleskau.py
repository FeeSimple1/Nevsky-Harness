"""Pleskau full playthrough — Teutons aggressor, 2 turns.
Adapts: if Muster fails, fall back to Veche B (auto-Muster). If Domash
still not Mustered at plan time, swap to Pass."""
from __future__ import annotations
import json, traceback, sys
from copy import deepcopy
from nevsky.scenarios import load_scenario
from nevsky.actions import apply_action, IllegalAction
from nevsky.legal_moves import legal_moves
from nevsky.render import render_summary, lord_combat_summary
from nevsky.previews import vp_forecast
from nevsky.static_data import load_cards


def step(s, act, *, expect_illegal=False, label=""):
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
        if side == "teutonic":
            pin = "knud_and_abel"
            if cap in ("Halbbrueder", "Warrior Monks", "Trebuchets", "Stonemasons", "Raiders"):
                pin = "hermann"
        else:
            pin = "gavrilo"
            if cap == "Luchniki":
                pin = "vladislav"
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

    # muster — Teu skips; Rus doesn't try regular Muster (use Veche B for Domash)
    print(f"\n--- LEVY turn {turn} muster ---")
    step(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    step(s, {"type": "advance_step", "side": "russian", "args": {}})

    # call_to_arms
    print(f"\n--- LEVY turn {turn} call_to_arms ---")
    step(s, {"type": "legate_skip", "side": "teutonic", "args": {}})
    step(s, {"type": "aow_discard_this_levy", "side": "teutonic", "args": {}})
    step(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    # Russian Veche: option B if Domash Ready and we have VP marker.
    if s.lords["domash"].state == "ready" and s.veche.vp_markers > 0:
        print(f"  -> Veche B: auto-Muster Domash (no Fealty roll)")
        step(s, {"type": "veche_action", "side": "russian",
                 "args": {"option": "B", "target_lord": "domash", "seat": "novgorod"}})
    else:
        step(s, {"type": "veche_action", "side": "russian", "args": {"option": "skip"}})
    step(s, {"type": "aow_discard_this_levy", "side": "russian", "args": {}})
    step(s, {"type": "advance_step", "side": "russian", "args": {}})


def make_plan(s, side, intended):
    """Build a plan; replace any non-Mustered Lord with 'pass'."""
    from nevsky.campaign import _plan_target_size
    target = _plan_target_size(s.meta.box)
    plan = []
    for c in intended:
        if c == "pass":
            plan.append("pass")
        elif c in s.lords and s.lords[c].state == "mustered":
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
    """Apply the strategy for the active Lord."""
    if active == "hermann":
        loc = s.lords["hermann"].location
        # If already at Izborsk with Siege, Storm. Otherwise march toward it.
        if loc == "izborsk" and s.locales["izborsk"].siege_markers > 0:
            fc = vp_forecast(s, {"type": "cmd_storm", "side": "teutonic",
                                  "args": {"lord_id": "hermann"}}, preview_trials=30)
            print(f"     storm forecast: {fc.get('note')}")
            step(s, {"type": "cmd_storm", "side": "teutonic",
                     "args": {"lord_id": "hermann"}})
        else:
            # March toward Izborsk.
            if loc == "dorpat":
                step(s, {"type": "cmd_march", "side": "teutonic",
                         "args": {"lord_id": "hermann", "to": "ugaunia"}})
            if (s.lords["hermann"].location == "ugaunia"
                    and s.campaign_turn.actions_remaining > 0):
                step(s, {"type": "cmd_march", "side": "teutonic",
                         "args": {"lord_id": "hermann", "to": "izborsk"}})
            # cmd_march into enemy Stronghold ends the card; if there
            # are residual actions try Storm (likely won't fire but
            # harmless).
            if (s.lords["hermann"].location == "izborsk"
                    and s.locales["izborsk"].siege_markers > 0
                    and s.campaign_turn.actions_remaining > 0):
                step(s, {"type": "cmd_storm", "side": "teutonic",
                         "args": {"lord_id": "hermann"}}, expect_illegal=True)
        if s.campaign_turn.actions_remaining > 0:
            step(s, {"type": "cmd_pass", "side": "teutonic",
                     "args": {"lord_id": "hermann"}}, expect_illegal=True)
    else:
        step(s, {"type": "cmd_pass", "side": side,
                 "args": {"lord_id": active}})


def activations(s, turn):
    print(f"\n--- TURN {turn} ACTIVATIONS ---")
    safety = 80
    while s.meta.campaign_step == "command" and safety > 0:
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
print("PLESKAU full playthrough")
print("=" * 70)
s = load_scenario("pleskau", seed=1)
step(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
step(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})

# ===== TURN 1 =====
levy_phase(s, turn=1)
print("\n" + render_summary(s))
print("\n--- TURN 1 PLAN ---")
make_plan(s, "teutonic", ["hermann", "yaroslav", "knud_and_abel"])
make_plan(s, "russian", ["gavrilo", "vladislav", "domash"])
activations(s, 1)

print("\n\n=== END OF TURN 1 ===")
print(render_summary(s))
print(f"\nIzborsk: T_conq={s.locales['izborsk'].teutonic_conquered}, "
      f"siege={s.locales['izborsk'].siege_markers}")
print(f"Hermann: loc={s.lords['hermann'].location}, "
      f"forces={s.lords['hermann'].forces}, "
      f"assets={s.lords['hermann'].assets}, "
      f"routed={s.lords['hermann'].routed_units}")

# Loop turns 2..end while in scenario span.
turn = 2
while s.meta.box <= s.meta.span_end_box:
    if s.meta.phase != "levy":
        break
    print(f"\n=== TURN {turn} ===")
    levy_phase(s, turn=turn)
    print("\n" + render_summary(s))
    print(f"\n--- TURN {turn} PLAN ---")
    make_plan(s, "teutonic", ["hermann", "yaroslav", "knud_and_abel"])
    make_plan(s, "russian", ["gavrilo", "vladislav", "domash"])
    activations(s, turn)
    turn += 1
    if turn > 6:
        break

print("\n\n=== END OF SCENARIO ===")
print(render_summary(s))
print(f"\nFinal VP: T={s.calendar.teutonic_vp}, R={s.calendar.russian_vp}")
print(f"Phase: {s.meta.phase} / {s.meta.campaign_step}")
print(f"Box: {s.meta.box}")
print(f"Removed Lords: T={[lid for lid,l in s.lords.items() if l.side=='teutonic' and l.state=='removed']}")
print(f"               R={[lid for lid,l in s.lords.items() if l.side=='russian' and l.state=='removed']}")
print(f"Locales conquered: ")
for lid, loc in s.locales.items():
    if loc.teutonic_conquered or loc.russian_conquered or loc.teutonic_ravaged or loc.russian_ravaged:
        print(f"  {lid}: T_conq={loc.teutonic_conquered} R_conq={loc.russian_conquered} "
              f"T_rav={loc.teutonic_ravaged} R_rav={loc.russian_ravaged}")
