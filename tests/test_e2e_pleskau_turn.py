"""End-to-end smoke test: one full Levy + Campaign turn of Pleskau.

Per BRIEF: end-to-end scenario tests exist for at least one full Levy +
Campaign turn of Pleskau by end of Phase 3a.

This test exercises the full action pipeline in sequence: it does not
verify rule details (those are covered by unit tests). It just runs all
the required step transitions and confirms state advances cleanly into
the next 40-Days Levy.
"""

from __future__ import annotations

from nevsky.actions import apply_action
from nevsky.campaign import _plan_target_size
from nevsky.scenarios import load_scenario


def test_pleskau_full_levy_and_campaign_turn() -> None:
    s = load_scenario("pleskau", seed=1)

    # Setup: clear Q-001 transport-choice pendings.
    apply_action(s, {"type": "system_setup_complete", "side": "system", "args": {}})
    pre_box = s.meta.box

    # ---- LEVY ----
    # 3.1 Arts of War: each side shuffles, draws 2, implements 2 (capabilities
    # on first Levy; no this-lord lord_id required for side-wide cards).
    # We auto-implement: simply call advance_step after drawing -- but the
    # implementer rejects unfinished pending_draw. So implement.
    for sd in ("teutonic", "russian"):
        apply_action(s, {"type": "aow_shuffle", "side": sd, "args": {}})
        apply_action(s, {"type": "aow_draw", "side": sd, "args": {}})
        # Implement each pending card. For this_lord scope cards we provide
        # a Mustered own-side Lord; for side-wide nothing extra needed.
        deck = s.decks.teutonic if sd == "teutonic" else s.decks.russian
        for _ in range(len(deck.pending_draw)):
            from nevsky.static_data import load_cards
            cid = deck.pending_draw[0]
            card = load_cards()[cid]
            args: dict = {}
            if not card["no_event"] and card["capability_scope"] == "this_lord":
                lid = next(
                    l for l, lord in s.lords.items()
                    if lord.side == sd and lord.state == "mustered"
                )
                args["lord_id"] = lid
            apply_action(s, {"type": "aow_implement_card", "side": sd, "args": args})
        apply_action(s, {"type": "advance_step", "side": sd, "args": {}})

    assert s.meta.levy_step == "pay"

    # 3.2 Pay (skip -- nothing to pay)
    apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "advance_step", "side": "russian", "args": {}})
    assert s.meta.levy_step == "disband"

    # 3.3 Disband (auto-resolve)
    apply_action(s, {"type": "disband_resolve", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "disband_resolve", "side": "russian", "args": {}})
    apply_action(s, {"type": "advance_step", "side": "russian", "args": {}})
    assert s.meta.levy_step == "muster"

    # 3.4 Muster (skip -- pleskau opening Lords already on map)
    apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "advance_step", "side": "russian", "args": {}})
    assert s.meta.levy_step == "call_to_arms"

    # 3.5 Call to Arms (skip both)
    apply_action(s, {"type": "legate_skip", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "aow_discard_this_levy", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "veche_action", "side": "russian", "args": {"option": "skip"}})
    apply_action(s, {"type": "aow_discard_this_levy", "side": "russian", "args": {}})
    apply_action(s, {"type": "advance_step", "side": "russian", "args": {}})

    # ---- CAMPAIGN ----
    assert s.meta.phase == "campaign"
    assert s.meta.campaign_step == "plan"

    # 4.1 Plan: fill with Pass cards on both sides.
    target = _plan_target_size(s.meta.box)
    for sd in ("teutonic", "russian"):
        for _ in range(target):
            apply_action(s, {"type": "plan_add_card", "side": sd, "args": {"card": "pass"}})
        apply_action(s, {"type": "finalize_plan", "side": sd, "args": {}})
    assert s.meta.campaign_step == "command"

    # 4.2 Activation: alternate reveals; each Pass card auto-enters 4.8.
    # Loop until both Plans empty.
    safety = 50
    while s.meta.campaign_step == "command" and safety > 0:
        side = s.campaign_turn.next_to_reveal
        if not s.campaign_turn.in_feed_pay_disband:
            apply_action(s, {"type": "command_reveal", "side": side, "args": {}})
        # 4.8 T-then-R fpd_resolve
        apply_action(s, {"type": "fpd_resolve", "side": "teutonic", "args": {}})
        apply_action(s, {"type": "fpd_resolve", "side": "russian", "args": {}})
        safety -= 1
    assert safety > 0, "Activation loop exceeded safety bound"
    assert s.meta.campaign_step == "end_campaign"

    # 4.9 End Campaign
    apply_action(s, {"type": "end_campaign_resolve", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "end_campaign_resolve", "side": "russian", "args": {}})

    # We should have advanced to the next 40-Days box, back in Levy.
    assert s.meta.box == pre_box + 1
    assert s.meta.phase == "levy"
    assert s.meta.levy_step == "arts_of_war"
