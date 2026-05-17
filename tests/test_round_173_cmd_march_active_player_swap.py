"""SMOKE-111 (Round 173): cmd_march set combat_pending with
pending_response_by=defender_side but did NOT switch
state.meta.active_player to the defender side. legal_moves keys off
active_player, so it kept enumerating the marching side's options
(zero, since combat_pending blocks normal commands), creating a
deadlock.

Found via scripts/self_play.py (Watland seed=3, RotP-Nicolle seed=1):
both hit `no_legal_moves` at a Russian March that triggered combat
pending on Teutonic defenders — active_player stayed on Russian, but
all moves the Russian could legally make in that state required the
combat to resolve first, which only the Teutonic defender could do.

Same audit pattern as SMOKE-106/107/109/110 (state-set-but-unreachable).

Fix: after building combat_pending, set
`state.meta.active_player = defender_side` so legal_moves enumerates
the defender's response options (stand_battle / avoid_battle /
withdraw / concede).
"""
from __future__ import annotations

import inspect

import nevsky.actions  # noqa: F401
import nevsky.campaign as camp


def test_smoke_111_marker_present():
    src = inspect.getsource(camp._h_cmd_march)
    assert "SMOKE-111" in src
    assert "state.meta.active_player = defender_side" in src


def test_smoke_111_active_player_swaps_on_approach_combat_pending():
    """Integration: Russian Andrey marches into a locale with Teutonic
    defender; active_player becomes teutonic so the defender can
    respond."""
    from nevsky.actions import apply_action
    from nevsky.scenarios import load_scenario
    s = load_scenario("watland", seed=1)
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "russian"
    # Set up Russian Lord at pskov; place a Teutonic enemy at adjacent.
    rus = next(lid for lid, l in s.lords.items()
               if l.side == "russian" and l.state == "mustered")
    teu = next(lid for lid, l in s.lords.items()
               if l.side == "teutonic" and l.state == "mustered")
    # Find an adjacent locale to the Russian Lord.
    s.lords[rus].location = "izborsk"
    s.lords[teu].location = "pskov"  # Russian seat, Teutonic invader
    s.lords[teu].in_stronghold = False
    s.campaign_turn.active_card = rus
    s.campaign_turn.active_lord = rus
    s.campaign_turn.actions_remaining = 3
    s.campaign_turn.in_feed_pay_disband = False
    s.combat_pending = None
    s.lords[rus].assets.pop("loot", None)
    s.lords[rus].assets.pop("provender", None)

    apply_action(s, {"type": "cmd_march", "side": "russian",
                      "args": {"lord_id": rus, "to": "pskov"}})
    assert s.combat_pending is not None
    assert s.combat_pending.pending_response_by == "teutonic"
    assert s.meta.active_player == "teutonic"


def test_smoke_111_legal_moves_offers_defender_response():
    """After the active_player swap, legal_moves enumerates the
    defender's combat-pending response moves."""
    from nevsky.actions import apply_action
    from nevsky.legal_moves import legal_moves
    from nevsky.scenarios import load_scenario
    s = load_scenario("watland", seed=1)
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "russian"
    rus = next(lid for lid, l in s.lords.items()
               if l.side == "russian" and l.state == "mustered")
    teu = next(lid for lid, l in s.lords.items()
               if l.side == "teutonic" and l.state == "mustered")
    s.lords[rus].location = "izborsk"
    s.lords[teu].location = "pskov"
    s.lords[teu].in_stronghold = False
    s.campaign_turn.active_card = rus
    s.campaign_turn.active_lord = rus
    s.campaign_turn.actions_remaining = 3
    s.combat_pending = None
    s.lords[rus].assets.pop("loot", None)
    s.lords[rus].assets.pop("provender", None)

    apply_action(s, {"type": "cmd_march", "side": "russian",
                      "args": {"lord_id": rus, "to": "pskov"}})
    moves = legal_moves(s, with_previews=False)
    types = {m["type"] for m in moves}
    # At minimum stand_battle must be offered.
    assert "stand_battle" in types
