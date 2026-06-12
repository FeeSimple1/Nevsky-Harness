"""PLAY-4/5/6 (Fable playtest follow-up): palette and choice fidelity
items resolved against the 2E rulebook and Playbook.

PLAY-4 — pay_with_coin / pay_with_loot candidates advertised every own
Mustered Lord as a target for every payer; 3.2.1/3.2.2 restrict Pay to
own Service or a co-located Lord's (Besieged target: only a payer
Besieged with him). Candidates now include a per-payer
`targets_by_payer` map and the `targets` union contains only targets
legal for at least one payer.

PLAY-5 — 4.3.1 Marshal group March was never enumerated. "A Marshal
may at the player's discretion bring along any or all of his side's
Unbesieged Lords at his Locale." The handler accepted args.group but
legal_actions() never offered it, so a palette-restricted agent
(LLM_PLAY_GUIDE principle 3) could never March an army. The enumerator
now emits a full-group variant per destination when the active Lord is
currently a Marshal with co-located Unbesieged friends.

PLAY-6 — 4.9.4 Wastage auto-picked the discard. Rule + example: the
owning player "must select and discard any one Asset or 'This Lord'
Capability card" from each qualifying Lord (two Boats + one Provender
+ one card: may discard a Boat, the Provender, OR the card).
end_campaign_resolve now accepts args.wastage per-Lord choices
(deterministic fallback otherwise) and the enumerator surfaces the
qualifying Lords and their discardable items.

Item NOT changed, resolved as correct from the Playbook (Watland
playthrough, Arts of War: Capabilities): a non-"This Lord" Capability
drawn at first Levy (e.g. R10 Steppe Warriors) is KEPT even when no
Lord matching its coats of arms is Mustered.
"""
from __future__ import annotations

import nevsky.actions  # noqa: F401 — register handlers
from nevsky.actions import apply_action
from nevsky.legal_moves import legal_moves
from nevsky.scenarios import load_scenario


# ----- PLAY-4: pay candidates ----------------------------------------------


def _pay_state():
    s = load_scenario("crusade_on_novgorod", seed=21)
    s.meta.phase = "levy"
    s.meta.levy_step = "pay"
    s.meta.active_player = "teutonic"
    # hermann (dorpat) and knud_and_abel (reval) both hold Coin and are
    # NOT co-located; yaroslav (odenpah) holds none.
    s.lords["hermann"].assets["coin"] = 1
    s.lords["knud_and_abel"].assets["coin"] = 1
    return s


def test_play4_coin_targets_only_collocated():
    s = _pay_state()
    moves = [m for m in legal_moves(s, with_previews=False)
             if m["type"] == "pay_with_coin"]
    assert len(moves) == 1
    cands = moves[0]["candidates"]
    tbp = cands["targets_by_payer"]
    assert tbp["hermann"] == ["hermann"]
    assert tbp["knud_and_abel"] == ["knud_and_abel"]
    # Union no longer advertises yaroslav (no payer can reach him).
    assert "yaroslav" not in cands["targets"]


def test_play4_coin_targets_include_collocated_friend():
    s = _pay_state()
    s.lords["yaroslav"].location = "dorpat"  # join hermann
    moves = [m for m in legal_moves(s, with_previews=False)
             if m["type"] == "pay_with_coin"]
    tbp = moves[0]["candidates"]["targets_by_payer"]
    assert sorted(tbp["hermann"]) == ["hermann", "yaroslav"]
    assert tbp["knud_and_abel"] == ["knud_and_abel"]
    # And the advertised pair is actually accepted by the handler.
    res = apply_action(s, {"type": "pay_with_coin", "side": "teutonic",
                           "args": {"from": "lord:hermann",
                                    "target_lord": "yaroslav", "units": 1}})
    assert res["target_lord"] == "yaroslav"


# ----- PLAY-5: Marshal group March enumeration ------------------------------


def _marshal_state():
    s = load_scenario("crusade_on_novgorod", seed=22)
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.first_levy_done = True
    s.meta.active_player = "teutonic"
    # Hermann is a secondary Marshal; Andreas (permanent) is off-map.
    s.lords["hermann"].location = "dorpat"
    s.lords["yaroslav"].location = "dorpat"
    s.campaign_turn.active_card = "hermann"
    s.campaign_turn.active_lord = "hermann"
    s.campaign_turn.actions_remaining = 3
    return s


def test_play5_marshal_group_march_enumerated():
    s = _marshal_state()
    marches = [m for m in legal_moves(s, with_previews=False)
               if m["type"] == "cmd_march"]
    groups = [m for m in marches if len(m["args"].get("group", [])) > 1]
    assert groups, "no group March enumerated for a Marshal with a co-located friend"
    g = groups[0]["args"]["group"]
    assert set(g) == {"hermann", "yaroslav"}
    # The enumerated group move must be accepted by the handler.
    mv = next(m for m in groups if m["args"]["to"] == "odenpah")
    res = apply_action(s, {"type": "cmd_march", "side": "teutonic",
                           "args": mv["args"]})
    assert res["group"] == mv["args"]["group"]
    assert s.lords["yaroslav"].location == "odenpah"


def test_play5_non_marshal_gets_no_group_variant():
    s = _marshal_state()
    # Make yaroslav the active lord: never a Marshal.
    s.campaign_turn.active_card = "yaroslav"
    s.campaign_turn.active_lord = "yaroslav"
    s.campaign_turn.actions_remaining = 2
    marches = [m for m in legal_moves(s, with_previews=False)
               if m["type"] == "cmd_march"]
    assert all(len(m["args"].get("group", [m["args"]["lord_id"]])) <= 1
               for m in marches)


def test_play5_andreas_on_map_demotes_hermann():
    s = _marshal_state()
    s.lords["andreas"].state = "mustered"
    s.lords["andreas"].location = "riga"
    marches = [m for m in legal_moves(s, with_previews=False)
               if m["type"] == "cmd_march"]
    assert all(len(m["args"].get("group", [])) <= 1 for m in marches), (
        "Hermann is not a Marshal while Andreas is on the map (1.5.1)")


# ----- PLAY-6: Wastage owner choice -----------------------------------------


def _end_campaign_state():
    s = load_scenario("crusade_on_novgorod", seed=23)
    s.meta.phase = "campaign"
    s.meta.campaign_step = "end_campaign"
    s.meta.first_levy_done = True
    s.meta.active_player = "teutonic"
    # Hermann qualifies via two boats; also holds one provender and one
    # This Lord Capability (the rulebook's 4.9.4 example shape).
    s.lords["hermann"].assets = {"boat": 2, "provender": 1}
    s.lords["hermann"].this_lord_capabilities = ["T10"]
    if "T10" in s.decks.teutonic.deck:
        s.decks.teutonic.deck.remove("T10")
    # Make sure no other Teuton owes Wastage.
    for lid in ("yaroslav", "knud_and_abel"):
        s.lords[lid].assets = {"provender": 1}
    return s


def test_play6_enumerator_surfaces_wastage_choice():
    s = _end_campaign_state()
    mv = [m for m in legal_moves(s, with_previews=False)
          if m["type"] == "end_campaign_resolve"][0]
    cands = mv["candidates"]["wastage"]
    assert set(cands) == {"hermann"}
    assert set(cands["hermann"]) == {"boat", "provender", "capability:T10"}


def test_play6_owner_may_discard_singleton_provender():
    """Rule example: two Boats trigger; owner may discard the Provender."""
    s = _end_campaign_state()
    apply_action(s, {"type": "end_campaign_resolve", "side": "teutonic",
                     "args": {"wastage": {"hermann": "provender"}}})
    assert s.lords["hermann"].assets == {"boat": 2}
    assert s.lords["hermann"].this_lord_capabilities == ["T10"]


def test_play6_owner_may_discard_the_card():
    s = _end_campaign_state()
    apply_action(s, {"type": "end_campaign_resolve", "side": "teutonic",
                     "args": {"wastage": {"hermann": "capability:T10"}}})
    assert s.lords["hermann"].this_lord_capabilities == []
    assert "T10" in s.decks.teutonic.deck
    assert s.lords["hermann"].assets == {"boat": 2, "provender": 1}


def test_play6_default_fallback_unchanged():
    s = _end_campaign_state()
    res = apply_action(s, {"type": "end_campaign_resolve",
                           "side": "teutonic", "args": {}})
    assert res["wastage"] == [{"lord_id": "hermann", "discarded": "boat"}]
    assert s.lords["hermann"].assets == {"boat": 1, "provender": 1}


def test_play6_rejects_choice_for_lord_owing_nothing():
    import pytest
    from nevsky.actions import IllegalAction
    s = _end_campaign_state()
    with pytest.raises(IllegalAction) as e:
        apply_action(s, {"type": "end_campaign_resolve", "side": "teutonic",
                         "args": {"wastage": {"yaroslav": "provender"}}})
    assert e.value.code == "bad_wastage"
