"""Engagement preview + VP forecast helpers for LLM consumers.

These let an LLM agent ask "if I commit this Battle / Storm / Ravage,
what's likely to happen?" without re-reading the rules or running the
combat math by hand. Each helper deep-copies the state per trial, so
the caller's state is never mutated.

Trials default to a modest count (100) so previews are cheap enough to
attach to legal_moves notes without exploding response time.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from nevsky.battle import (
    BattleDecisionContext,
    resolve_battle,
    resolve_storm,
)
from nevsky.state import GameState, Side


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _force_total(forces: dict) -> int:
    return sum(forces.values()) if forces else 0


def _side_units(state: GameState, lord_ids: list[str]) -> int:
    return sum(_force_total(state.lords[lid].forces) for lid in lord_ids if lid in state.lords)


# ---------------------------------------------------------------------------
# battle_preview
# ---------------------------------------------------------------------------


def battle_preview(
    state: GameState,
    attacker_side: Side,
    attacker_lords: list[str],
    defender_lords: list[str],
    *,
    trials: int = 100,
    max_rounds: int = 10,
    seed_base: int = 0,
) -> dict[str, Any]:
    """Run `trials` deep-copied resolve_battle simulations of the
    candidate engagement and return aggregate outcome stats.

    Returns:
      {
        "trials": N,
        "attacker_winrate": float,
        "defender_winrate": float,
        "avg_rounds": float,
        "attacker_units_pre": int,   # average pre-battle force
        "defender_units_pre": int,
        "avg_attacker_units_lost": float,
        "avg_defender_units_lost": float,
        "avg_attacker_loss_pct": float,
        "avg_defender_loss_pct": float,
      }
    """
    if not attacker_lords or not defender_lords:
        return {
            "trials": 0, "attacker_winrate": 0.0, "defender_winrate": 0.0,
            "avg_rounds": 0.0,
            "attacker_units_pre": 0, "defender_units_pre": 0,
            "avg_attacker_units_lost": 0.0, "avg_defender_units_lost": 0.0,
            "avg_attacker_loss_pct": 0.0, "avg_defender_loss_pct": 0.0,
            "error": "empty side(s)",
        }
    # Validate all lord_ids exist (catches typos before the simulation
    # silently treats unknown ids as 0-unit Lords and reports a confident
    # but meaningless winrate).
    bad = [lid for lid in (list(attacker_lords) + list(defender_lords))
           if lid not in state.lords]
    if bad:
        return {
            "trials": 0, "attacker_winrate": 0.0, "defender_winrate": 0.0,
            "avg_rounds": 0.0,
            "attacker_units_pre": 0, "defender_units_pre": 0,
            "avg_attacker_units_lost": 0.0, "avg_defender_units_lost": 0.0,
            "avg_attacker_loss_pct": 0.0, "avg_defender_loss_pct": 0.0,
            "error": f"unknown lord_id(s): {bad}",
        }

    defender_side: Side = "russian" if attacker_side == "teutonic" else "teutonic"
    atk_wins = 0
    def_wins = 0
    rounds_sum = 0
    atk_loss_sum = 0
    def_loss_sum = 0
    atk_pre_sum = 0
    def_pre_sum = 0
    failed_trials = 0
    last_error: str | None = None

    for t in range(trials):
        scopy = deepcopy(state)
        # Per-trial seed so the trial-set is reproducible but each trial
        # rolls different dice.
        scopy.meta.rng_state = seed_base + t * 7919 + 1
        atk_pre = _side_units(scopy, attacker_lords)
        def_pre = _side_units(scopy, defender_lords)
        try:
            res = resolve_battle(
                scopy,
                attacker_side=attacker_side,
                attacker_lords=list(attacker_lords),
                defender_lords=list(defender_lords),
                max_rounds=max_rounds,
                decision_ctx=BattleDecisionContext(),
            )
        except Exception as e:  # noqa: BLE001 - tracked, not silenced
            failed_trials += 1
            last_error = f"{type(e).__name__}: {e}"
            continue
        winner = res.get("winner")
        if winner == attacker_side:
            atk_wins += 1
        elif winner == defender_side:
            def_wins += 1
        rounds_sum += res.get("rounds", 0)
        atk_loss_sum += atk_pre - _side_units(scopy, attacker_lords)
        def_loss_sum += def_pre - _side_units(scopy, defender_lords)
        atk_pre_sum += atk_pre
        def_pre_sum += def_pre

    successful = max(1, trials - failed_trials)
    out_d = {
        "trials": trials,
        "successful_trials": trials - failed_trials,
        "attacker_winrate": atk_wins / successful,
        "defender_winrate": def_wins / successful,
        "avg_rounds": rounds_sum / successful,
        "attacker_units_pre": atk_pre_sum / successful,
        "defender_units_pre": def_pre_sum / successful,
        "avg_attacker_units_lost": atk_loss_sum / successful,
        "avg_defender_units_lost": def_loss_sum / successful,
        "avg_attacker_loss_pct": atk_loss_sum / max(1, atk_pre_sum),
        "avg_defender_loss_pct": def_loss_sum / max(1, def_pre_sum),
    }
    if failed_trials:
        out_d["failed_trials"] = failed_trials
        out_d["last_error"] = last_error
    return out_d


# ---------------------------------------------------------------------------
# storm_preview
# ---------------------------------------------------------------------------


def storm_preview(
    state: GameState,
    attacker_side: Side,
    attacker_lords: list[str],
    locale_id: str,
    *,
    defender_lords: list[str] | None = None,
    trials: int = 100,
    seed_base: int = 0,
) -> dict[str, Any]:
    """Run `trials` deep-copied resolve_storm simulations against the
    Stronghold at `locale_id`. Walls, Garrison, and Siege markers are
    pulled from the current state.

    Returns the same shape as battle_preview plus garrison loss stats:
      avg_garrison_units_pre, avg_garrison_units_lost, avg_garrison_loss_pct.
    """
    from nevsky.static_data import load_locales, load_strongholds

    if not attacker_lords:
        return {"trials": 0, "error": "no attacker lords"}
    if locale_id not in state.locales:
        return {"trials": 0, "error": f"unknown locale {locale_id}"}

    static_loc = load_locales().get(locale_id)
    if static_loc is None:
        return {"trials": 0, "error": f"no static data for {locale_id}"}
    sh = load_strongholds().get(static_loc["type"])
    if sh is None:
        return {"trials": 0, "error": f"{locale_id} ({static_loc['type']}) is not a stormable Stronghold"}
    if sh.get("no_storm"):
        return {"trials": 0, "error": f"{static_loc['type']} cannot be Stormed"}

    walls_max = int(sh.get("walls_max", 0))
    # Walls +1 marker on the Locale.
    if state.locales[locale_id].walls_plus_one:
        walls_max += 1
    siege_markers = int(state.locales[locale_id].siege_markers)
    garrison_template = dict(sh.get("garrison", {}))

    if defender_lords is None:
        # Default: Lords inside the Stronghold (Besieged) on the
        # defender side.
        defender_side: Side = "russian" if attacker_side == "teutonic" else "teutonic"
        defender_lords = [
            lid for lid, l in state.lords.items()
            if l.side == defender_side and l.location == locale_id and l.in_stronghold
        ]
    else:
        defender_lords = list(defender_lords)
    # Validate lord_ids exist.
    bad = [lid for lid in (list(attacker_lords) + defender_lords)
           if lid not in state.lords]
    if bad:
        return {"trials": 0, "error": f"unknown lord_id(s): {bad}"}

    atk_wins = 0
    def_wins = 0
    rounds_sum = 0
    atk_loss_sum = 0
    def_loss_sum = 0
    g_loss_sum = 0
    atk_pre_sum = 0
    def_pre_sum = 0
    g_pre_sum = 0
    failed_trials = 0
    last_error: str | None = None

    for t in range(trials):
        scopy = deepcopy(state)
        scopy.meta.rng_state = seed_base + t * 7919 + 1
        atk_pre = _side_units(scopy, attacker_lords)
        def_pre = _side_units(scopy, defender_lords)
        g_pre = sum(garrison_template.values())
        try:
            res = resolve_storm(
                scopy,
                attacker_side=attacker_side,
                attacker_lords=list(attacker_lords),
                defender_lords=list(defender_lords),
                locale_id=locale_id,
                walls_max=walls_max,
                siege_markers=siege_markers,
                garrison=dict(garrison_template),
                decision_ctx=BattleDecisionContext(),
            )
        except Exception as e:  # noqa: BLE001 - tracked, not silenced
            failed_trials += 1
            last_error = f"{type(e).__name__}: {e}"
            continue
        winner = res.get("winner")
        if winner == "attacker":
            atk_wins += 1
        elif winner == "defender":
            def_wins += 1
        rounds_sum += res.get("rounds", 0)
        atk_loss_sum += atk_pre - _side_units(scopy, attacker_lords)
        def_loss_sum += def_pre - _side_units(scopy, defender_lords)
        g_post = sum(res.get("garrison_remaining", {}).values())
        g_loss_sum += g_pre - g_post
        atk_pre_sum += atk_pre
        def_pre_sum += def_pre
        g_pre_sum += g_pre

    successful = max(1, trials - failed_trials)
    out_d = {
        "trials": trials,
        "successful_trials": trials - failed_trials,
        "locale_id": locale_id,
        "stronghold_type": static_loc["type"],
        "walls_max": walls_max,
        "siege_markers": siege_markers,
        "attacker_winrate": atk_wins / successful,
        "defender_winrate": def_wins / successful,
        "avg_rounds": rounds_sum / successful,
        "attacker_units_pre": atk_pre_sum / successful,
        "defender_units_pre": def_pre_sum / successful,
        "avg_garrison_units_pre": g_pre_sum / successful,
        "avg_attacker_units_lost": atk_loss_sum / successful,
        "avg_defender_units_lost": def_loss_sum / successful,
        "avg_garrison_units_lost": g_loss_sum / successful,
        "avg_attacker_loss_pct": atk_loss_sum / max(1, atk_pre_sum),
        "avg_defender_loss_pct": def_loss_sum / max(1, def_pre_sum),
        "avg_garrison_loss_pct": g_loss_sum / max(1, g_pre_sum),
        "stronghold_vp": int(sh.get("vp", 0)),
    }
    if failed_trials:
        out_d["failed_trials"] = failed_trials
        out_d["last_error"] = last_error
    return out_d


# ---------------------------------------------------------------------------
# vp_forecast
# ---------------------------------------------------------------------------


def vp_forecast(state: GameState, action: dict[str, Any], *, preview_trials: int = 50) -> dict[str, Any]:
    """Return expected VP deltas for a candidate action.

    Result shape:
      {
        "action_type": str,
        "side": "teutonic" | "russian",
        "kind": "deterministic" | "probabilistic" | "noop",
        "attacker_vp_delta": float,
        "defender_vp_delta": float,
        "note": str,                 # short explanation
        "preview": dict | None,      # storm/battle preview if probabilistic
      }
    """
    atype = action.get("type")
    args = action.get("args", {})
    side = action.get("side")
    res = {
        "action_type": atype,
        "side": side,
        "kind": "noop",
        "attacker_vp_delta": 0.0,
        "defender_vp_delta": 0.0,
        "note": "",
        "preview": None,
    }

    # Deterministic actions.
    if atype == "cmd_ravage":
        # Own-color Ravaged on a Locale: +0.5 VP for the placing side.
        # The 2E rule "Ravage costs 2 actions if Unbesieged enemy adjacent"
        # affects feasibility, not VP delta.
        res["kind"] = "deterministic"
        res["attacker_vp_delta"] = 0.5
        res["note"] = f"Ravage at {args.get('locale_id', '?')} -> +0.5 VP for {side}"
        return res

    if atype in ("cmd_tax", "cmd_forage", "cmd_supply", "cmd_pass",
                 "cmd_march", "cmd_sail", "end_card"):
        res["note"] = "no immediate VP impact"
        return res

    if atype == "stand_battle":
        # Probabilistic: run battle_preview from the pending Combat.
        cp = state.combat_pending
        if cp is None:
            res["note"] = "no combat_pending; cannot forecast"
            return res
        res["kind"] = "probabilistic"
        attacker_side = cp.attacker_side
        defender_side = "russian" if attacker_side == "teutonic" else "teutonic"
        prev = battle_preview(
            state, attacker_side, list(cp.attacker_group), list(cp.defender_lords),
            trials=preview_trials,
        )
        res["preview"] = prev
        # VP from removed enemy Lords; in Pleskau scenario, +1 VP per
        # Lord removed. Standard scenarios don't grant per-lord VP; here
        # we report the bare outcome, plus Spoils + Loot are tracked
        # at end-of-battle but not encoded as VP. Keep it simple:
        # report 0 VP delta for the attacker_side from the win itself.
        res["note"] = (
            f"battle: A{prev['attacker_winrate']*100:.0f}%/D{prev['defender_winrate']*100:.0f}% win, "
            f"avg A_loss {prev['avg_attacker_loss_pct']*100:.0f}% / D_loss {prev['avg_defender_loss_pct']*100:.0f}%"
        )
        return res

    if atype == "cmd_storm":
        lord_id = args.get("lord_id")
        if not lord_id or lord_id not in state.lords:
            res["note"] = "missing lord_id"
            return res
        lord = state.lords[lord_id]
        locale_id = lord.location
        if locale_id is None:
            res["note"] = "lord has no location"
            return res
        res["kind"] = "probabilistic"
        # Attacker = list of all besieging Lords on side at locale.
        attacker_side = lord.side
        attacker_lords = [
            lid for lid, l in state.lords.items()
            if l.side == attacker_side and l.location == locale_id
            and not l.in_stronghold
        ]
        prev = storm_preview(
            state, attacker_side, attacker_lords, locale_id,
            trials=preview_trials,
        )
        res["preview"] = prev
        win_p = prev.get("attacker_winrate", 0.0)
        sh_vp = prev.get("stronghold_vp", 0)
        # On attacker win: +stronghold_vp for attacker, lose any prior
        # defender Conquered marker. Approximate VP delta = win_p * vp.
        res["attacker_vp_delta"] = win_p * sh_vp
        res["note"] = (
            f"storm {locale_id}: A_win {win_p*100:.0f}%, expected +{res['attacker_vp_delta']:.2f} VP "
            f"(VP={sh_vp}); avg A_loss {prev['avg_attacker_loss_pct']*100:.0f}% / G_loss {prev['avg_garrison_loss_pct']*100:.0f}%"
        )
        return res

    if atype == "cmd_sally":
        # Sally is a Storm-shape combat with Besieged Lord(s) attacking
        # Besiegers. Treat similar to storm_preview but flipped: the
        # Besieged Lords are the "attacker" and the Besiegers defend.
        lord_id = args.get("lord_id")
        if not lord_id or lord_id not in state.lords:
            res["note"] = "missing lord_id"
            return res
        lord = state.lords[lord_id]
        locale_id = lord.location
        if locale_id is None:
            res["note"] = "lord has no location"
            return res
        res["kind"] = "probabilistic"
        attacker_side = lord.side  # the Sallying side
        defender_side = "russian" if attacker_side == "teutonic" else "teutonic"
        attacker_lords = [
            lid for lid, l in state.lords.items()
            if l.side == attacker_side and l.location == locale_id and l.in_stronghold
        ]
        defender_lords = [
            lid for lid, l in state.lords.items()
            if l.side == defender_side and l.location == locale_id and not l.in_stronghold
        ]
        prev = battle_preview(
            state, attacker_side, attacker_lords, defender_lords,
            trials=preview_trials,
        )
        res["preview"] = prev
        res["note"] = (
            f"sally: Sallier_win {prev['attacker_winrate']*100:.0f}%, "
            f"avg Sally_loss {prev['avg_attacker_loss_pct']*100:.0f}% / Besieger_loss {prev['avg_defender_loss_pct']*100:.0f}%"
        )
        return res

    res["note"] = f"no VP forecast wired for {atype}"
    return res
