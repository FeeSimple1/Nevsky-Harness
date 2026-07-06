"""4.4.2 Concede the Field: the *attacker* may Concede a Battle.

Per the Battle & Storm Reference the concede order is
["attacker", "defender"] -- either side may Concede the Field at the
start of a Round. The harness resolves a Battle synchronously inside
the defender's stand_battle response, so the attacker (who has no later
decision point) declares any Concede when it initiates the Battle on
cmd_march; the intent is captured on combat_pending.attacker_concede
and applied in stand_battle. An attacker Concede takes precedence over
a defender Concede in the same Round (attacker is first in the order).

Before this fix only the responding defender could Concede: legal_moves
emitted concede with role derived from the responder (always
"defender") and stand_battle only consumed the defender's arg, so
attacker Concede was unreachable in normal play.
"""
from __future__ import annotations

from nevsky.actions import apply_action
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import load_scenario
from nevsky.state import CombatPending


def _setup_battle(attacker_concede_round=None):
    """Andrey (R) approaches a single Teuton defender (hermann) at pskov."""
    s = load_scenario("peipus", seed=1)
    s.meta.phase = "campaign"
    s.meta.campaign_step = "done"
    s.meta.active_player = "teutonic"
    for lid in ("hermann", "andrey"):
        s.lords[lid].state = "mustered"
        s.lords[lid].location = "pskov"
        s.lords[lid].in_stronghold = False
    s.combat_pending = CombatPending(
        attacker_side="russian", attacker_group=["andrey"],
        from_locale="dubrovno", to_locale="pskov", way_type="trackway",
        defender_side="teutonic", defender_lords=["hermann"],
        pending_response_by="teutonic", laden=False,
        attacker_concede_round=attacker_concede_round,
    )
    return s


def test_attacker_concede_makes_defender_win():
    """attacker_concede on combat_pending -> attacker loses the Battle."""
    s = _setup_battle(attacker_concede_round=1)
    res = apply_action(s, {"type": "stand_battle", "side": "teutonic", "args": {}})
    b = res["battle"]
    assert b.get("conceded") == "attacker"
    assert b["winner"] == "teutonic"
    assert b["loser"] == "russian"
    assert b["rounds"] == 1  # concede ends the Battle after this Round


def test_attacker_concede_precedence_over_defender():
    """Concede order is attacker-then-defender: if the attacker Conceded,
    a defender Concede in the same Round does not flip the result."""
    s = _setup_battle(attacker_concede_round=1)
    res = apply_action(s, {"type": "stand_battle", "side": "teutonic",
                           "args": {"concede": "defender"}})
    b = res["battle"]
    assert b.get("conceded") == "attacker"
    assert b["winner"] == "teutonic"  # attacker (russian) still loses


def test_no_concede_resolves_normally():
    """Default (no concede anywhere) does not mark a conceder."""
    s = _setup_battle(attacker_concede_round=None)
    res = apply_action(s, {"type": "stand_battle", "side": "teutonic", "args": {}})
    assert res["battle"].get("conceded") is None


def test_legal_moves_offers_attacker_march_and_concede():
    """When the attacker can March one Locale into a Locale holding an
    open (not Besieged) enemy Lord, legal_moves offers a 'March and
    Concede' variant (concede=True) alongside the plain March."""
    s = load_scenario("peipus", seed=1)
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "russian"
    # Andrey (R) at dubrovno; Hermann (T, open) at adjacent pskov.
    s.lords["andrey"].state = "mustered"
    s.lords["andrey"].location = "dubrovno"
    s.lords["andrey"].in_stronghold = False
    s.lords["andrey"].moved_fought = False
    s.lords["hermann"].state = "mustered"
    s.lords["hermann"].location = "pskov"
    s.lords["hermann"].in_stronghold = False
    s.combat_pending = None
    s.campaign_turn.active_lord = "andrey"
    s.campaign_turn.actions_remaining = 6
    s.campaign_turn.in_feed_pay_disband = False

    marches = [m for m in legal_moves(s, with_previews=False)
               if m["type"] == "cmd_march" and m.get("args", {}).get("to") == "pskov"]
    plain = [m for m in marches if "concede" not in m.get("args", {})]
    concede = [m for m in marches if m.get("args", {}).get("concede") is True]
    assert plain, "expected a plain March into pskov (open enemy present)"
    assert concede, "expected a 'March and Concede' variant into pskov"
    assert concede[0]["args"]["concede"] is True


def _command_state_andrey_at_dubrovno():
    s = load_scenario("peipus", seed=1)
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "russian"
    s.lords["andrey"].state = "mustered"
    s.lords["andrey"].location = "dubrovno"
    s.lords["andrey"].in_stronghold = False
    s.lords["andrey"].moved_fought = False
    s.combat_pending = None
    s.campaign_turn.active_lord = "andrey"
    s.campaign_turn.actions_remaining = 6
    s.campaign_turn.in_feed_pay_disband = False
    return s


def test_cmd_march_concede_captured_onto_combat_pending():
    """A combat March with concede=True records it on combat_pending."""
    s = _command_state_andrey_at_dubrovno()
    s.lords["hermann"].state = "mustered"
    s.lords["hermann"].location = "pskov"
    s.lords["hermann"].in_stronghold = False
    apply_action(s, {"type": "cmd_march", "side": "russian",
                     "args": {"lord_id": "andrey", "to": "pskov",
                              "way_type": "trackway", "concede": True}})
    assert s.combat_pending is not None
    assert s.combat_pending.attacker_concede_round == 1


def test_cmd_march_concede_without_combat_rejected():
    """concede on a March that triggers no Battle is rejected."""
    import pytest
    s = _command_state_andrey_at_dubrovno()
    # Move every Teuton away from pskov so the March triggers no Battle.
    for l in s.lords.values():
        if l.side == "teutonic":
            l.location = "dorpat"
            l.in_stronghold = False
    with pytest.raises(Exception) as e:
        apply_action(s, {"type": "cmd_march", "side": "russian",
                         "args": {"lord_id": "andrey", "to": "pskov",
                                  "way_type": "trackway", "concede": True}})
    assert getattr(e.value, "code", "") == "no_combat_to_concede"


# --- defender Concede via stand_battle args --------------------------------


def test_defender_concede_round1_via_args():
    s = _setup_battle()  # attacker russian, defender teutonic
    res = apply_action(s, {"type": "stand_battle", "side": "teutonic",
                           "args": {"concede": "defender"}})
    b = res["battle"]
    assert b.get("conceded") == "defender"
    assert b["winner"] == "russian"  # attacker wins when defender Concedes


def test_defender_concede_via_explicit_concede_decisions():
    s = _setup_battle()
    res = apply_action(s, {"type": "stand_battle", "side": "teutonic",
                           "args": {"concede_decisions": {1: "defender"}}})
    assert res["battle"].get("conceded") == "defender"
    assert res["battle"]["winner"] == "russian"


# --- Round 2+ Concede for BOTH sides (the previously-unreachable gap) -------


def _watland_two_round_combat():
    """Teutonic attacker vs Russian defender on watland seed=1 -- this
    pairing runs >= 2 Rounds, matching test_round_181's resolve_battle
    fixture, so a Round-2 Concede is genuinely exercised."""
    s = load_scenario("watland", seed=1)
    s.meta.phase = "campaign"
    s.meta.campaign_step = "done"
    s.meta.active_player = "russian"
    teu = next(lid for lid, l in s.lords.items()
               if l.side == "teutonic" and l.state == "mustered")
    rus = next(lid for lid, l in s.lords.items()
               if l.side == "russian" and l.state == "mustered")
    for lid in (teu, rus):
        s.lords[lid].location = "pskov"
        s.lords[lid].in_stronghold = False
    return s, teu, rus


def test_attacker_concede_round2_via_combat_pending():
    """Attacker (declared on cmd_march) Concedes at the start of Round 2."""
    s, teu, rus = _watland_two_round_combat()
    s.combat_pending = CombatPending(
        attacker_side="teutonic", attacker_group=[teu],
        from_locale="dorpat", to_locale="pskov", way_type="trackway",
        defender_side="russian", defender_lords=[rus],
        pending_response_by="russian", laden=False,
        attacker_concede_round=2,
    )
    b = apply_action(s, {"type": "stand_battle", "side": "russian", "args": {}})["battle"]
    assert b.get("conceded") == "attacker"
    assert b["winner"] == "russian"
    assert b["rounds"] == 2


def test_defender_concede_round2_via_args():
    """Defender Concedes at the start of Round 2 via concede_decisions."""
    s, teu, rus = _watland_two_round_combat()
    s.combat_pending = CombatPending(
        attacker_side="teutonic", attacker_group=[teu],
        from_locale="dorpat", to_locale="pskov", way_type="trackway",
        defender_side="russian", defender_lords=[rus],
        pending_response_by="russian", laden=False,
    )
    b = apply_action(s, {"type": "stand_battle", "side": "russian",
                         "args": {"concede_decisions": {2: "defender"}}})["battle"]
    assert b.get("conceded") == "defender"
    assert b["winner"] == "teutonic"
    assert b["rounds"] == 2


# --- Relief Sally Concede (sallying side is the attacker) ------------------


def test_sally_attacker_concede():
    from nevsky.static_data import load_lords
    s = load_scenario("pleskau", seed=1)
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    teu = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[rus].location = "pskov"; s.lords[rus].in_stronghold = True
    s.lords[teu].location = "pskov"
    s.lords[rus].forces = {"knights": 5, "men_at_arms": 3}  # strong, but Concedes
    s.lords[teu].forces = {"militia": 1}
    s.locales["pskov"].siege_markers = 2
    s.meta.phase = "campaign"; s.meta.campaign_step = "command"
    s.meta.active_player = "russian"
    s.campaign_turn.next_to_reveal = "russian"
    s.campaign_turn.active_card = rus
    s.campaign_turn.active_lord = rus
    s.campaign_turn.actions_remaining = int(load_lords()[rus]["ratings"]["command"])
    s.campaign_turn.in_feed_pay_disband = False
    s.lords[rus].moved_fought = False
    res = apply_action(s, {"type": "cmd_sally", "side": "russian",
                           "args": {"lord_id": rus, "concede": "attacker"}})
    assert res["battle"].get("conceded") == "attacker"
    assert res["battle"]["winner"] == "teutonic"  # sallying side Conceded -> loses
    # RAID fired (markers reduced to 1) ...
    assert res.get("raid_siege_to_1") is True
    # ... but PLAY-11 (4.4.4 both-sides Losses) means the winning
    # besieger's lone militia -- Routed by the Pursuit strikes -- may
    # fail its Protection roll: a winner Lord with zero units left is
    # permanently removed, and the Siege then lifts (4.3.5).
    if teu in s.lords and s.lords[teu].state == "mustered":
        assert s.locales["pskov"].siege_markers == 1   # RAID holds
    else:
        assert res.get("winner_removed_by_losses") == [teu]
        assert s.locales["pskov"].siege_markers == 0   # besieger gone


# --- merge / parse helper units --------------------------------------------


def test_concede_helpers():
    from nevsky.campaign import (
        _concede_decisions_from_args,
        _merge_concede_decisions,
        _parse_concede_round,
    )
    # _parse_concede_round
    assert _parse_concede_round(None, who="attacker") is None
    assert _parse_concede_round(False, who="attacker") is None
    assert _parse_concede_round(True, who="attacker") == 1
    assert _parse_concede_round("attacker", who="attacker") == 1
    assert _parse_concede_round(3, who="attacker") == 3
    # attacker wins same-Round ties (4.4.2 order), regardless of order
    assert _merge_concede_decisions([(2, "defender"), (2, "attacker")]) == {2: "attacker"}
    assert _merge_concede_decisions([(2, "attacker"), (2, "defender")]) == {2: "attacker"}
    assert _merge_concede_decisions([(1, "attacker"), (3, "defender")]) == {1: "attacker", 3: "defender"}
    # _concede_decisions_from_args: attacker pre-declaration + defender arg
    cd = _concede_decisions_from_args({"concede": "defender"}, attacker_round=2)
    assert cd == {2: "attacker", 1: "defender"}
    cd2 = _concede_decisions_from_args({"concede_decisions": {2: "defender", 4: "attacker"}})
    assert cd2 == {2: "defender", 4: "attacker"}


def test_concede_args_validation():
    import pytest
    from nevsky.actions import IllegalAction
    from nevsky.campaign import _concede_decisions_from_args
    with pytest.raises(IllegalAction) as e1:
        _concede_decisions_from_args({"concede": "sideways"})
    assert e1.value.code == "bad_concede"
    with pytest.raises(IllegalAction):
        _concede_decisions_from_args({"concede": "defender", "concede_round": 0})
    with pytest.raises(IllegalAction):
        _concede_decisions_from_args({"concede_decisions": {1: "nope"}})
    with pytest.raises(IllegalAction):
        _concede_decisions_from_args({"concede_decisions": [1, 2]})
