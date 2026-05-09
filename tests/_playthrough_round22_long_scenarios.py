"""Generic active scenario player: drives any scenario end-to-end with
a simple aggressive-but-safe agent. Each side's Lords march toward the
opposing side's Strongholds, place Sieges, Storm when win-prob > 50%,
Avoid Battle when significantly outnumbered, otherwise Stand. Russians
use Veche option B to auto-Muster Ready Lords when VP markers are
available.

Run: PYTHONPATH=src python3 /tmp/active_scenario.py <scenario_id>
"""
from __future__ import annotations
import json, sys, traceback
from copy import deepcopy
from nevsky.scenarios import load_scenario
from nevsky.actions import apply_action, IllegalAction
from nevsky.legal_moves import legal_moves
from nevsky.render import render_summary, lord_combat_summary, paths_from
from nevsky.previews import vp_forecast, battle_preview
from nevsky.static_data import load_cards, load_lords as _load_lords, load_locales, load_strongholds


def step(s, act, expect_illegal=False, label=""):
    try:
        r = apply_action(s, act)
        return r
    except IllegalAction as e:
        if expect_illegal:
            return None
        return {"_il": e.code}
    except Exception as e:
        return {"_ex": f"{type(e).__name__}: {e}"}


def implement_drawn(s, side):
    cards = load_cards()
    deck = s.decks.teutonic if side == "teutonic" else s.decks.russian
    while deck.pending_draw:
        cid = deck.pending_draw[0]
        c = cards[cid]
        scope = c["capability_scope"]
        cap = c["capability_name"]
        # Heuristic: pin this_lord caps on highest-Lordship Mustered Lord on the side.
        candidates = [lid for lid, l in s.lords.items()
                       if l.side == side and l.state == "mustered"]
        pin = candidates[0] if candidates else None
        if scope == "side_wide":
            r = step(s, {"type": "aow_implement_card", "side": side, "args": {}})
        elif scope == "this_lord" and pin:
            r = step(s, {"type": "aow_implement_card", "side": side, "args": {"lord_id": pin}})
        else:
            deck.pending_draw.pop(0); deck.discard.append(cid)
            continue
        if isinstance(r, dict) and ("_il" in r or "_ex" in r):
            if deck.pending_draw and deck.pending_draw[0] == cid:
                deck.pending_draw.pop(0); deck.discard.append(cid)


def levy_phase(s):
    """Both sides through arts_of_war / pay / disband / muster / cta / done."""
    step(s, {"type": "aow_shuffle", "side": "teutonic", "args": {}})
    step(s, {"type": "aow_draw", "side": "teutonic", "args": {}})
    implement_drawn(s, "teutonic")
    step(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    step(s, {"type": "aow_shuffle", "side": "russian", "args": {}})
    step(s, {"type": "aow_draw", "side": "russian", "args": {}})
    implement_drawn(s, "russian")
    step(s, {"type": "advance_step", "side": "russian", "args": {}})
    # pay (skip)
    step(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    step(s, {"type": "advance_step", "side": "russian", "args": {}})
    # disband (auto via engine)
    step(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    step(s, {"type": "advance_step", "side": "russian", "args": {}})
    # muster (try to auto-Muster Ready Lords with available Lordship)
    moves = legal_moves(s, with_previews=False)
    for m in moves:
        if m["type"] == "muster_lord":
            step(s, m, expect_illegal=True)
            break
    step(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    # Russian: Veche B for any Ready Lord, else skip; then advance
    moves = legal_moves(s, with_previews=False)
    veche_b_options = [m for m in moves
                        if m["type"] == "veche_action"
                        and m["args"].get("option") == "B"]
    if veche_b_options:
        step(s, veche_b_options[0])
    moves = legal_moves(s, with_previews=False)
    muster_opts = [m for m in moves if m["type"] == "muster_lord"]
    if muster_opts:
        step(s, muster_opts[0], expect_illegal=True)
    step(s, {"type": "advance_step", "side": "russian", "args": {}})
    # call_to_arms
    step(s, {"type": "legate_skip", "side": "teutonic", "args": {}})
    step(s, {"type": "aow_discard_this_levy", "side": "teutonic", "args": {}})
    step(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    moves = legal_moves(s, with_previews=False)
    veche = next((m for m in moves if m["type"] == "veche_action"), None)
    if veche:
        step(s, veche)
    else:
        step(s, {"type": "veche_action", "side": "russian", "args": {"option": "skip"}}, expect_illegal=True)
    step(s, {"type": "aow_discard_this_levy", "side": "russian", "args": {}})
    step(s, {"type": "advance_step", "side": "russian", "args": {}})


def make_plan(s):
    from nevsky.campaign import _plan_target_size
    target = _plan_target_size(s.meta.box)
    for side in ("teutonic", "russian"):
        # Order: Mustered Lords by Lordship rating desc, then pad with pass.
        own_mustered = [
            lid for lid, l in s.lords.items()
            if l.side == side and l.state == "mustered"
        ]
        # Cap to plan target.
        plan = own_mustered[:target]
        while len(plan) < target:
            plan.append("pass")
        for c in plan:
            step(s, {"type": "plan_add_card", "side": side, "args": {"card": c}}, expect_illegal=True)
        step(s, {"type": "finalize_plan", "side": side, "args": {}}, expect_illegal=True)


def _enemy_strongholds(s, side):
    """Return list of (locale_id, stronghold_vp, conquered_status) for
    enemy-territory strongholds, sorted by reachability + VP."""
    static = load_locales()
    strongholds = load_strongholds()
    out = []
    for lid, loc in s.locales.items():
        l_static = static.get(lid, {})
        sh = strongholds.get(l_static.get("type"), {})
        if not sh or sh.get("no_storm"):
            continue
        terr = l_static.get("territory")
        # Enemy-owned: territory != side AND not own-conquered.
        own_conq = (loc.teutonic_conquered if side == "teutonic" else loc.russian_conquered)
        enemy_terr = (
            (side == "teutonic" and terr == "russian")
            or (side == "russian" and terr in ("teutonic", "crusader"))
        )
        if enemy_terr and own_conq == 0:
            out.append((lid, int(sh.get("vp", 0))))
    return out


def execute_lord_card(s, side, active):
    """Strategy:
    - If at an enemy-stronghold besieged, Storm if expected VP > 0.5.
    - Else if at an enemy-stronghold with no siege, place siege via Siege.
    - Else march one hop toward nearest enemy Stronghold via paths_from.
    - If active Lord has 6+ units and no clear path, Tax/Forage to refill.
    - Default fallback: pass.
    """
    if active not in s.lords:
        step(s, {"type": "cmd_pass", "side": side, "args": {"lord_id": active}}, expect_illegal=True)
        return
    lord = s.lords[active]
    loc = lord.location
    if loc is None:
        step(s, {"type": "cmd_pass", "side": side, "args": {"lord_id": active}}, expect_illegal=True)
        return

    # Already at enemy Stronghold with siege?
    if s.locales[loc].siege_markers > 0:
        # We're besieger or besieged?
        from nevsky.campaign import _is_besieged
        if not _is_besieged(s, active):
            # Try Storm if win prob is reasonable.
            try:
                fc = vp_forecast(s, {"type": "cmd_storm", "side": side,
                                      "args": {"lord_id": active}}, preview_trials=10)
                prev = fc.get("preview") or {}
                win = prev.get("attacker_winrate", 0)
                if win > 0.4:
                    r = step(s, {"type": "cmd_storm", "side": side,
                                  "args": {"lord_id": active}}, expect_illegal=True)
                    if not (isinstance(r, dict) and "_il" in r):
                        return
            except Exception:
                pass

    # Path to nearest enemy Stronghold.
    targets = _enemy_strongholds(s, side)
    if targets:
        paths = paths_from(s, loc, max_hops=5)
        # Find shortest reachable target.
        best = None
        best_len = 999
        for tgt, vp in targets:
            if tgt in paths and len(paths[tgt]) < best_len:
                best = tgt; best_len = len(paths[tgt])
        if best and best_len > 0:
            # March to first hop.
            next_hop = paths[best][0]
            r = step(s, {"type": "cmd_march", "side": side,
                          "args": {"lord_id": active, "to": next_hop}}, expect_illegal=True)
            # If actions remain and not at target / not entered enemy
            # Stronghold (which would have ended card), continue.
            # Bound the loop to prevent infinite cycles when paths_from
            # returns valid hops that cmd_march refuses (e.g., no
            # in-Season transport).
            inner_safety = 4
            while (inner_safety > 0
                    and s.campaign_turn.actions_remaining > 0
                    and s.lords[active].location != best
                    and s.combat_pending is None):
                inner_safety -= 1
                cur = s.lords[active].location
                if cur is None:
                    break
                paths2 = paths_from(s, cur, max_hops=5)
                if best not in paths2 or not paths2[best]:
                    break
                hop = paths2[best][0]
                r2 = step(s, {"type": "cmd_march", "side": side,
                               "args": {"lord_id": active, "to": hop}}, expect_illegal=True)
                if isinstance(r2, dict) and "_il" in r2:
                    break

    # Use remaining actions: try Storm if at target, else pass.
    if (s.lords.get(active) and s.lords[active].location is not None
            and s.locales[s.lords[active].location].siege_markers > 0
            and s.campaign_turn.actions_remaining > 0):
        try:
            fc = vp_forecast(s, {"type": "cmd_storm", "side": side,
                                  "args": {"lord_id": active}}, preview_trials=10)
            prev = fc.get("preview") or {}
            win = prev.get("attacker_winrate", 0)
            if win > 0.4:
                step(s, {"type": "cmd_storm", "side": side,
                          "args": {"lord_id": active}}, expect_illegal=True)
        except Exception:
            pass

    if (s.lords.get(active) and s.campaign_turn.actions_remaining > 0
            and not s.campaign_turn.in_feed_pay_disband):
        step(s, {"type": "cmd_pass", "side": side, "args": {"lord_id": active}}, expect_illegal=True)


def handle_combat_pending(s):
    cp = s.combat_pending
    if cp is None:
        return
    side = cp.pending_response_by
    # Forecast the Battle.
    try:
        fc = vp_forecast(s, {"type": "stand_battle", "side": side, "args": {}}, preview_trials=10)
        prev = fc.get("preview") or {}
        # Defender win rate from the defender's perspective.
        # battle_preview returns attacker_winrate / defender_winrate.
        # If the responder is attacker (rare; usually defender responds),
        # use attacker_winrate.
        if side == cp.attacker_side:
            win = prev.get("attacker_winrate", 0)
        else:
            win = prev.get("defender_winrate", 0)
    except Exception:
        win = 0.5
    # If outnumbered (winrate < 30%): Avoid (if Unladen) or Withdraw.
    if win < 0.3 and not cp.laden:
        moves = legal_moves(s, with_previews=False)
        avoid = [m for m in moves if m["type"] == "avoid_battle"]
        if avoid:
            step(s, avoid[0], expect_illegal=True)
            return
    # Try Withdraw into Stronghold.
    r = step(s, {"type": "withdraw", "side": side, "args": {}}, expect_illegal=True)
    if not (isinstance(r, dict) and "_il" in r):
        return
    # Stand if neither works.
    step(s, {"type": "stand_battle", "side": side, "args": {}}, expect_illegal=True)


def activations(s):
    safety = 100
    cp_safety = 6  # max combat-pending iterations before forcing stand
    while s.meta.campaign_step == "command" and safety > 0:
        if s.combat_pending is not None:
            cp_safety -= 1
            if cp_safety <= 0:
                # Force stand_battle to escape; defender takes its lumps.
                step(s, {"type": "stand_battle",
                          "side": s.combat_pending.pending_response_by,
                          "args": {}}, expect_illegal=True)
                cp_safety = 6
                continue
            handle_combat_pending(s)
            continue
        cp_safety = 6
        side = s.campaign_turn.next_to_reveal
        prev_seq = s.meta.sequence
        if not s.campaign_turn.in_feed_pay_disband:
            r = step(s, {"type": "command_reveal", "side": side, "args": {}}, expect_illegal=True)
            active = s.campaign_turn.active_lord
            if active:
                execute_lord_card(s, side, active)
            if s.campaign_turn.actions_remaining > 0 and not s.campaign_turn.in_feed_pay_disband:
                step(s, {"type": "end_card", "side": side, "args": {}}, expect_illegal=True)
        step(s, {"type": "fpd_resolve", "side": "teutonic", "args": {}}, expect_illegal=True)
        step(s, {"type": "fpd_resolve", "side": "russian", "args": {}}, expect_illegal=True)
        # Forward-progress safety: if no action consumed, abort.
        if s.meta.sequence == prev_seq:
            break
        safety -= 1
    if s.meta.campaign_step == "end_campaign":
        step(s, {"type": "end_campaign_resolve", "side": "teutonic", "args": {}})
        step(s, {"type": "end_campaign_resolve", "side": "russian", "args": {}})


def play_scenario(scenario_id, seed=1, max_turns=20):
    s = load_scenario(scenario_id, seed=seed)
    step(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    step(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})
    initial_t_vp = s.calendar.teutonic_vp
    initial_r_vp = s.calendar.russian_vp
    log = {"scenario": scenario_id, "seed": seed,
           "initial_t_vp": initial_t_vp, "initial_r_vp": initial_r_vp,
           "turns": [], "errors": []}
    turn = 0
    while s.meta.box <= s.meta.span_end_box and turn < max_turns:
        if s.meta.phase != "levy":
            break
        turn += 1
        try:
            levy_phase(s)
        except Exception as e:
            log["errors"].append(f"levy t{turn}: {type(e).__name__}: {e}")
            traceback.print_exc()
            break
        try:
            make_plan(s)
        except Exception as e:
            log["errors"].append(f"plan t{turn}: {type(e).__name__}: {e}")
            traceback.print_exc()
            break
        try:
            activations(s)
        except Exception as e:
            log["errors"].append(f"activations t{turn}: {type(e).__name__}: {e}")
            traceback.print_exc()
            break
        log["turns"].append({
            "turn": turn, "box": s.meta.box,
            "t_vp": s.calendar.teutonic_vp,
            "r_vp": s.calendar.russian_vp,
            "phase": s.meta.phase,
            "campaign_step": s.meta.campaign_step,
        })
    log["final"] = {
        "t_vp": s.calendar.teutonic_vp,
        "r_vp": s.calendar.russian_vp,
        "turns_played": turn,
        "phase": s.meta.phase, "campaign_step": s.meta.campaign_step,
        "box": s.meta.box,
        "winner": ("teutonic" if s.calendar.teutonic_vp > s.calendar.russian_vp
                   else "russian" if s.calendar.russian_vp > s.calendar.teutonic_vp
                   else "tie"),
        "removed_t": [lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "removed"],
        "removed_r": [lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "removed"],
        "conq": [(lid, "T", loc.teutonic_conquered) for lid, loc in s.locales.items() if loc.teutonic_conquered]
              + [(lid, "R", loc.russian_conquered) for lid, loc in s.locales.items() if loc.russian_conquered],
        "ravaged": [(lid, "T") for lid, loc in s.locales.items() if loc.teutonic_ravaged]
                 + [(lid, "R") for lid, loc in s.locales.items() if loc.russian_ravaged],
    }
    return log


if __name__ == "__main__":
    sid = sys.argv[1] if len(sys.argv) > 1 else "watland"
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    out = play_scenario(sid, seed=seed)
    print(json.dumps(out, indent=2, default=str))
