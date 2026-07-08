"""PLAY-29 (4.4.3): Retreat destination CHOICE + Unbesieged qualifier.

4.4.3: losing Lords "Retreat to a single adjacent Locale that has no
Unbesieged enemy Lords or Strongholds ... The owning player chooses each
Lord's fate." args.retreat_to = {lord_id: locale_id} directs a losing
Defender's Retreat; unspecified -> first legal (backward-compatible).
"""

from __future__ import annotations

import pytest

from nevsky.actions import IllegalAction, apply_action
from nevsky.scenarios import load_scenario
from nevsky.state import CombatPending


def _combat_defender_loses(retreat_args=None):
    s = load_scenario("pleskau", seed=1)
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "russian"
    teu = "hermann"
    rus = "domash"
    s.lords[teu].state = "mustered"
    s.lords[teu].location = "pskov"
    s.lords[teu].forces = {"knights": 6}      # overwhelming
    s.lords[rus].state = "mustered"
    s.lords[rus].location = "pskov"
    s.lords[rus].forces = {"serfs": 2}        # Routs fast -> loses
    s.combat_pending = CombatPending(
        attacker_side="teutonic", attacker_group=[teu],
        from_locale="izborsk", to_locale="pskov", way_type="trackway",
        defender_side="russian", defender_lords=[rus],
        pending_response_by="russian", laden=False,
    )
    args = {"absorption_policy": "weakest_first"}
    if retreat_args is not None:
        args.update(retreat_args)
    res = apply_action(s, {"type": "stand_battle", "side": "russian", "args": args})
    return s, res, rus


def test_retreat_to_directs_the_destination():
    s, res, rus = _combat_defender_loses(
        retreat_args={"retreat_to": {"domash": "ostrov"}})
    assert res["loser"] == "russian"
    tos = [r["to"] for r in res["retreats"]]
    assert "ostrov" in tos, f"expected Retreat directed to ostrov, got {tos}"


def test_retreat_to_illegal_destination_rejected():
    # izborsk is the Approach Way (izborsk/trackway) -> not a legal Retreat.
    with pytest.raises(IllegalAction) as exc:
        _combat_defender_loses(retreat_args={"retreat_to": {"domash": "izborsk"}})
    assert exc.value.code == "bad_retreat_dest"


def test_default_auto_pick_still_works():
    s, res, rus = _combat_defender_loses()  # no retreat_to
    assert res["loser"] == "russian"
    assert res["retreats"], "loser should Retreat by default"
    # Auto-picked destination is a legal adjacent Locale (not the Approach).
    assert res["retreats"][0]["to"] != "izborsk"


def test_retreat_to_non_losing_lord_rejected():
    with pytest.raises(IllegalAction) as exc:
        _combat_defender_loses(retreat_args={"retreat_to": {"hermann": "ostrov"}})
    assert exc.value.code == "bad_retreat_to"
