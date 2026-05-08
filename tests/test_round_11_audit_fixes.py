"""Round 11 audit-fix regression tests.

SMOKE-012: _is_laden was checking the can't-move threshold
(prov > 2*usable) instead of the Laden threshold (prov > usable).
Lords with prov in (usable, 2*usable] were incorrectly Unladen.

Also covers _must_discard_to_move_excess (4.3.2 bullet 1) and the new
cmd_march excess-Provender gate.
"""

from __future__ import annotations

import pytest

from nevsky.actions import IllegalAction, apply_action
from nevsky.scenarios import load_scenario


def _summer_sled_only_lord():
    """Construct a Lord in Summer with 2 Provender + 2 Sleds (Sleds
    not usable in Summer -> usable=0, excess=2)."""
    s = load_scenario("watland", seed=1)
    s.meta.box = 1  # Summer
    teu = next(lid for lid, l in s.lords.items()
               if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].assets = {"provender": 2, "sled": 2}
    return s, teu


def test_smoke_012_is_laden_returns_true_for_provender_over_usable() -> None:
    """4.3.2: a Lord with prov in (usable, 2*usable] is Laden."""
    import nevsky.actions  # full init
    from nevsky.campaign import _is_laden

    s = load_scenario("watland", seed=1)
    s.meta.box = 1  # Summer
    teu = next(lid for lid, l in s.lords.items()
               if l.side == "teutonic" and l.state == "mustered")
    # 3 Provender, 2 Carts -> usable=2 (Summer), prov(3) > usable(2) -> Laden.
    s.lords[teu].assets = {"provender": 3, "cart": 2}
    assert _is_laden(s, teu) is True


def test_smoke_012_is_laden_returns_true_for_loot_only() -> None:
    """4.3.2: any Loot makes the Lord Laden."""
    import nevsky.actions
    from nevsky.campaign import _is_laden

    s = load_scenario("watland", seed=1)
    s.meta.box = 1
    teu = next(lid for lid, l in s.lords.items()
               if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].assets = {"loot": 1}
    assert _is_laden(s, teu) is True


def test_smoke_012_is_laden_returns_false_for_unladen_lord() -> None:
    """A Lord with prov <= usable and no Loot is Unladen."""
    import nevsky.actions
    from nevsky.campaign import _is_laden

    s = load_scenario("watland", seed=1)
    s.meta.box = 1
    teu = next(lid for lid, l in s.lords.items()
               if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].assets = {"provender": 2, "cart": 2}
    assert _is_laden(s, teu) is False


def test_smoke_012_must_discard_to_move_excess_returns_amount() -> None:
    """_must_discard_to_move_excess returns max(0, prov - 2*usable)."""
    import nevsky.actions
    from nevsky.campaign import _must_discard_to_move_excess

    s = load_scenario("watland", seed=1)
    s.meta.box = 1
    teu = next(lid for lid, l in s.lords.items()
               if l.side == "teutonic" and l.state == "mustered")
    s.lords[teu].assets = {"provender": 5, "cart": 2}  # 2*usable=4, excess=1
    assert _must_discard_to_move_excess(s, teu) == 1
    s.lords[teu].assets = {"provender": 4, "cart": 2}  # within Laden boundary
    assert _must_discard_to_move_excess(s, teu) == 0
    s.lords[teu].assets = {"provender": 0, "cart": 2}
    assert _must_discard_to_move_excess(s, teu) == 0


def test_smoke_012_cmd_march_rejects_excess_provender_without_discard() -> None:
    """cmd_march raises 'excess_provender' when prov > 2*usable and no
    discard_excess_provender flag."""
    s, teu = _summer_sled_only_lord()
    # Set up active card.
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "teutonic"
    s.campaign_turn.active_lord = teu
    s.campaign_turn.actions_remaining = 3
    s.campaign_turn.active_card = teu
    # Find an adjacent locale.
    from nevsky.static_data import load_ways
    src = s.lords[teu].location
    dest = next(
        (w["b"] if w["a"] == src else w["a"])
        for w in load_ways()
        if (w["a"] == src or w["b"] == src)
    )
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "cmd_march", "side": "teutonic",
                          "args": {"lord_id": teu, "to": dest}})
    assert exc.value.code == "excess_provender"


def test_smoke_012_cmd_march_with_discard_flag_succeeds() -> None:
    """Passing discard_excess_provender: True auto-discards and the
    March proceeds."""
    s, teu = _summer_sled_only_lord()
    pre_prov = s.lords[teu].assets["provender"]
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "teutonic"
    s.campaign_turn.active_lord = teu
    s.campaign_turn.actions_remaining = 3
    s.campaign_turn.active_card = teu
    from nevsky.static_data import load_ways
    src = s.lords[teu].location
    # Find a destination locale that's empty (no Lords / strongholds).
    dest = None
    for w in load_ways():
        if w["a"] == src:
            cand = w["b"]
        elif w["b"] == src:
            cand = w["a"]
        else:
            continue
        if not any(l.location == cand for l in s.lords.values()):
            dest = cand
            break
    if dest is None:
        pytest.skip("no clear adjacent locale")
    apply_action(s, {"type": "cmd_march", "side": "teutonic",
                     "args": {"lord_id": teu, "to": dest,
                              "discard_excess_provender": True}})
    # Provender should have been discarded.
    assert s.lords[teu].assets.get("provender", 0) < pre_prov


def test_smoke_013_sally_lords_actually_strike() -> None:
    """SMOKE-013: pre-fix, Sally Lords were skipped by the resolve_battle
    striker filter (`if pos not in ("left","center","right"): continue`).
    Sally row contributed 0 strikes; Battles ran to max rounds with no
    progress. Post-fix, Sally Lords appear in per_striker logs with
    striker_slot starting "sally_".
    """
    from nevsky.battle import BattleDecisionContext, resolve_battle
    from nevsky.scenarios import load_scenario

    s = load_scenario("watland", seed=1)
    teus = [lid for lid, l in s.lords.items() if l.side == "teutonic"][:2]
    rus_lords = [lid for lid, l in s.lords.items() if l.side == "russian"][:2]
    for t in teus:
        s.lords[t].state = "mustered"
        s.lords[t].location = "pskov"
        s.lords[t].forces = {"knights": 4, "sergeants": 4}
    s.lords[rus_lords[0]].state = "mustered"
    s.lords[rus_lords[0]].location = "pskov"
    s.lords[rus_lords[0]].in_stronghold = True
    s.lords[rus_lords[0]].forces = {"knights": 4, "men_at_arms": 4, "militia": 4}
    s.lords[rus_lords[1]].state = "mustered"
    s.lords[rus_lords[1]].location = "pskov"
    s.lords[rus_lords[1]].forces = {"knights": 6, "men_at_arms": 4}
    s.locales["pskov"].siege_markers = 2

    res = resolve_battle(
        s, attacker_side="russian",
        attacker_lords=[rus_lords[1], rus_lords[0]],
        defender_lords=teus,
        active_attacker=rus_lords[1],
        decision_ctx=BattleDecisionContext(),
        sallying_lords=[rus_lords[0]],
        siegeworks_for_sally=2,
    )
    sally_strikes = []
    for rd in res["log"]:
        for step in rd["steps"]:
            for ps in step.get("per_striker", []):
                if ps["striker_slot"].startswith("sally_"):
                    sally_strikes.append(ps)
    assert sally_strikes, (
        f"Sally Lords should produce strikes. log: {res['log']}"
    )


def test_smoke_013_rearguard_lords_actually_strike() -> None:
    """Rearguard row should also strike. Set up so a Rearguard Lord
    has Forces and strikes a Sally row Lord."""
    from nevsky.battle import BattleDecisionContext, resolve_battle
    from nevsky.scenarios import load_scenario

    s = load_scenario("watland", seed=1)
    teus = [lid for lid, l in s.lords.items() if l.side == "teutonic"][:2]
    rus_lords = [lid for lid, l in s.lords.items() if l.side == "russian"][:2]
    for t in teus:
        s.lords[t].state = "mustered"
        s.lords[t].location = "pskov"
        s.lords[t].forces = {"knights": 4, "sergeants": 4}
    s.lords[rus_lords[0]].state = "mustered"
    s.lords[rus_lords[0]].location = "pskov"
    s.lords[rus_lords[0]].in_stronghold = True
    s.lords[rus_lords[0]].forces = {"knights": 4, "men_at_arms": 4, "militia": 4}
    s.lords[rus_lords[1]].state = "mustered"
    s.lords[rus_lords[1]].location = "pskov"
    s.lords[rus_lords[1]].forces = {"knights": 6, "men_at_arms": 4}

    res = resolve_battle(
        s, attacker_side="russian",
        attacker_lords=[rus_lords[1], rus_lords[0]],
        defender_lords=teus,
        active_attacker=rus_lords[1],
        decision_ctx=BattleDecisionContext(),
        sallying_lords=[rus_lords[0]],
        siegeworks_for_sally=0,
    )
    rg_strikes = []
    for rd in res["log"]:
        for step in rd["steps"]:
            for ps in step.get("per_striker", []):
                if ps["striker_slot"].startswith("rearguard_"):
                    rg_strikes.append(ps)
    assert rg_strikes, (
        f"Rearguard Lords should produce strikes. log: {res['log']}"
    )
