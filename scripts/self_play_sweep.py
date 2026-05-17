"""Run scripts/self_play.step_self_play across all loadable scenarios x N seeds.
Print a summary table and report any errors (not just expected agent
gaps but actual harness exceptions).
"""
from __future__ import annotations

import json
import sys
import importlib.util

# Load self_play module
spec = importlib.util.spec_from_file_location("sp", "scripts/self_play.py")
sp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sp)


SCENARIOS = [
    "watland",
    "pleskau",
    "peipus",
    "return_of_the_prince",
    "return_of_the_prince_nicolle",
    "crusade_on_novgorod",
]


def main():
    seeds = list(range(1, 51))  # 50 seeds per scenario
    rows = []
    real_errors = []
    for sc in SCENARIOS:
        for seed in seeds:
            try:
                r = sp.step_self_play(sc, seed=seed, max_steps=20000, verbose=False)
            except Exception as e:
                r = {"scenario": sc, "seed": seed,
                     "error": {"reason": "driver_exception",
                               "exception_type": type(e).__name__,
                               "exception_msg": str(e)[:200]}}
            rows.append(r)
            status = "OK" if r.get("terminal") else "STUCK"
            err = r.get("error")
            # Print only failed/STUCK runs to keep output manageable.
            if not r.get("terminal") or err:
                print(f"  {sc:32s} seed={seed} steps={r.get('steps_taken', 0):5d} "
                      f"box={r.get('box', '?'):>3} "
                      f"T_vp={r.get('teutonic_vp', 0):4.1f} R_vp={r.get('russian_vp', 0):4.1f} "
                      f"{status}")
            if err:
                reason = err.get("reason")
                # Real bugs: exceptions or unexpected illegal_action
                if reason in ("exception", "driver_exception"):
                    real_errors.append({"scenario": sc, "seed": seed, "err": err})
                    print(f"    EXCEPTION: {err.get('exception_type')}: "
                          f"{err.get('exception_msg', '')[:150]}")
                elif reason == "no_legal_moves":
                    real_errors.append({"scenario": sc, "seed": seed, "err": err})
                    print(f"    STALL: no_legal_moves at step {err.get('step')}: "
                          f"phase={err.get('phase')} levy={err.get('levy_step')} "
                          f"camp={err.get('campaign_step')} active={err.get('active_player')}")
                elif reason == "illegal_action":
                    # Agent gap — most are expected (events the agent can't fill)
                    code = err.get("error_code")
                    # Codes that signal real harness bugs vs agent gaps:
                    if code not in ("missing_arg", "bad_target", "no_cylinder",
                                    "no_service_marker", "ineligible_target",
                                    "ineligible_levyer", "too_far",
                                    "not_eligible_locale", "not_ravaged",
                                    "russian_lord_present", "no_target",
                                    "cap_limit", "duplicate_capability",
                                    "card_unavailable", "already_ravaged",
                                    "conquered", "friendly", "own_territory",
                                    "no_eligible_horse", "not_at_seat",
                                    "no_free_seat", "fealty_failed",
                                    "not_ready", "not_friendly", "besieged",
                                    "bad_card", "blocked_this_levy",
                                    "ship_unauthorized", "transport_max",
                                    "no_target", "not_adjacent",
                                    "no_service", "no_attackers",
                                    "no_storm", "not_co_located",
                                    "marshal_lieutenant", "marshal_lower_lord",
                                    "lt_full", "ll_already", "self_target",
                                    "not_mustered", "no_william",
                                    "legate_off_map", "legate_already_on_map",
                                    "bad_bishopric", "wrong_side",
                                    "bad_sub_option", "not_friendly",
                                    "no_combat", "wrong_actor",
                                    "bad_actor", "bad_grant",
                                    "wrong_step", "wrong_phase",
                                    "ravaged", "forage_seasonal",
                                    "provender_max", "coin_max",
                                    "no_location", "no_lieutenant",
                                    "veche_cannot_reach_besieged",
                                    "pay_target_not_collocated",
                                    "loot_locale_constraint",
                                    "besieged_pay_constraint",
                                    "insufficient_funds",
                                    "insufficient_actions",
                                    "no_capability", "already_used",
                                    "trackway_only", "enemy_at_target",
                                    "boat_winter", "cart_non_summer",
                                    "ship_winter", "sled_non_winter",
                                    "transport_way", "bad_route",
                                    "route_blocked", "too_many_seat_sources",
                                    "too_many_ship_sources",
                                    "insufficient_transport",
                                    "duplicate_source", "bad_source",
                                    "bad_units", "bad_source",
                                    "vassal_unready", "vassal_gated",
                                    "vassal_season", "already_mustered",
                                    "unknown_vassal",
                                    "ineligible_target", "bad_direction",
                                    "missing_target",
                                    "decline_unavailable",
                                    "insufficient_vp", "already_acted",
                                    "loot_forbidden", "no_recipients",
                                    "bad_recipients", "no_heinrich",
                                    "bad_grant_total", "bad_grant_type",
                                    "bad_concede", "bad_hold",
                                    "not_in_holds", "season_blocked",
                                    "role_blocked", "bad_mode",
                                    "approach_way_blocked",
                                    "dest_blocked", "lower_lord_required",
                                    "non_marshal_group",
                                    "bad_group", "winter",
                                    "not_seaport", "insufficient_ships",
                                    "no_siege", "no_stronghold",
                                    "not_besieged",
                                    "no_defenders",
                                    "russian_lord_present",
                                    "not_in_play",
                                    "sea_trade_blocked",
                                    "sea_trade_winter",
                                    "sea_trade_already_used",
                                    "no_stronghold",
                                    "bad_transport",
                                    "ineligible_target",
                                    "not_furthest_right",
                                    "cylinder_at_left_edge",
                                    "lord_at_edge",
                                    "bad_boxes",
                                    "no_one_to_block"):
                        real_errors.append({"scenario": sc, "seed": seed, "err": err})
                        print(f"    UNEXPECTED IllegalAction: code={code}: "
                              f"{err.get('error_msg', '')[:150]}")

    print()
    print("=" * 80)
    print(f"Total runs: {len(rows)}  Terminal: {sum(1 for r in rows if r.get('terminal'))}")
    print(f"Real errors / harness bugs: {len(real_errors)}")
    print("=" * 80)
    for re in real_errors:
        print(json.dumps(re, indent=2, default=str)[:600])
        print("---")
    return 0 if not real_errors else 1


if __name__ == "__main__":
    sys.exit(main())
