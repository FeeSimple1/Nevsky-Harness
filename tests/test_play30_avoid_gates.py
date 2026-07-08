"""PLAY-30 (4.3.4): Avoid destination gates + enumerator/handler parity.

4.3.4: "Lords may not Avoid Battle to any Locale with an UNBESIEGED enemy
Lord or Stronghold" and "may not Avoid ... across any part of the Way the
enemy used to Approach" (a PARALLEL Way of another type is allowed). The
Avoid handler over-restricted (Besieged strongholds, enemy-Conquered
markers); the enumerator diverged. Both now share `_legal_retreat_dests`.
"""

from __future__ import annotations

import pytest

from nevsky.actions import IllegalAction, apply_action
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import load_scenario
from nevsky.state import CombatPending


def _combat(defender_side, attacker, defender, from_loc, to_loc, way="trackway"):
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = defender_side
    atk_side = "russian" if defender_side == "teutonic" else "teutonic"
    for lid, o in s.lords.items():
        if o.location == to_loc:
            o.location = None  # clear the Battle Locale of stray lords
    s.lords[attacker].state = "mustered"
    s.lords[attacker].location = to_loc
    s.lords[defender].state = "mustered"
    s.lords[defender].location = to_loc
    s.lords[defender].in_stronghold = False
    s.lords[defender].assets = {}
    s.combat_pending = CombatPending(
        attacker_side=atk_side, attacker_group=[attacker],
        from_locale=from_loc, to_locale=to_loc, way_type=way,
        defender_side=defender_side, defender_lords=[defender],
        pending_response_by=defender_side, laden=False,
    )
    return s


def _avoid_opts(s, side):
    return [m for m in legal_moves(s, with_previews=False)
            if m["type"] == "avoid_battle" and m.get("side") == side]


def test_besieged_enemy_stronghold_does_not_block_avoid():
    # Teutonic defender at pskov; Russian attacker approached from dubrovno.
    # izborsk (Russian Fort) is an adjacent enemy Stronghold to the Teuton.
    s = _combat("teutonic", "aleksandr", "hermann", "dubrovno", "pskov")
    for o in s.lords.values():
        if o.location == "izborsk":
            o.location = None  # no garrison
    # Unbesieged Russian Stronghold at izborsk blocks the Teuton's Avoid.
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {"type": "avoid_battle", "side": "teutonic",
                         "args": {"to": "izborsk", "way_type": "trackway"}})
    assert exc.value.code == "dest_blocked"
    # Besiege izborsk -> it no longer blocks the Avoid there.
    s2 = _combat("teutonic", "aleksandr", "hermann", "dubrovno", "pskov")
    for o in s2.lords.values():
        if o.location == "izborsk":
            o.location = None
    s2.locales["izborsk"].siege_markers = 1
    res = apply_action(s2, {"type": "avoid_battle", "side": "teutonic",
                            "args": {"to": "izborsk", "way_type": "trackway"}})
    assert res.get("avoided_to") == "izborsk"


def test_parallel_way_avoid_back_along_other_way():
    # Russian approached dorpat from odenpah via TRACKWAY. The Teutonic
    # defender may Avoid back to odenpah via the parallel WATERWAY, but not
    # the trackway the enemy used.
    s = _combat("teutonic", "aleksandr", "hermann", "odenpah", "dorpat",
                way="trackway")
    opts = _avoid_opts(s, "teutonic")
    to_odenpah = {(o["args"]["to"], o["args"].get("way_type"))
                  for o in opts if o["args"]["to"] == "odenpah"}
    assert ("odenpah", "waterway") in to_odenpah, "parallel Way avoid-back must be offered"
    assert ("odenpah", "trackway") not in to_odenpah, "approach Way must be excluded"


def test_enumerator_handler_parity_for_avoid():
    # Every enumerated Avoid option must be accepted by the handler.
    s = _combat("teutonic", "aleksandr", "hermann", "odenpah", "dorpat")
    opts = _avoid_opts(s, "teutonic")
    assert opts, "expected some Avoid options"
    for o in opts:
        s_copy = s.model_copy(deep=True)
        # Should not raise IllegalAction (enumerator/handler parity).
        apply_action(s_copy, {"type": o["type"], "side": o["side"],
                              "args": dict(o["args"])})
