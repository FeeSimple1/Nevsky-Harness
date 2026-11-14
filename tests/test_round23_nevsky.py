"""Rule 3.5.3 and the T3/T13 Hold Events through native Watland play."""

import pytest

from nevsky.actions import IllegalAction
from nevsky.llm.session import LLMSession
from nevsky.state import HistoryEntry
from tests.test_round21_nevsky import (
    _advance,
    _apply,
    _choose,
    _native_muster,
    _offered,
    _play_to_muster,
    _reject,
    _save_load,
)


def _fortified_fort_session():
    session = _native_muster(8, 4, "teutonic")
    for _ in range(2):
        _choose(session, "levy_transport", by_lord="knud_and_abel", transport_type="sled")
    _advance(session)
    for card in ("R18", "R15"):
        _choose(session, "levy_capability", by_lord="domash", card_id=card)
    _advance(session, 3)

    for plan in (
        ("knud_and_abel", "pass", "pass", "pass"),
        ("domash", "domash", "domash", "pass"),
    ):
        for card in plan:
            _choose(session, "plan_add_card", card=card)
        _choose(session, "finalize_plan")

    # Take Kaibolovo's nearest Russian Lord away after he builds the walls.
    for lord, destinations in (
        ("knud_and_abel", ("wierland", "narwia")),
        ("domash", ("sablia", "zheltsy", "kaibolovo")),
        (None, ()),
        ("domash", ()),
        (None, ()),
        ("domash", ("zheltsy", "sablia")),
        (None, ()),
        (None, ()),
    ):
        _choose(session, "command_reveal")
        assert session.state.campaign_turn.active_lord == lord
        for destination in destinations:
            _choose(session, "cmd_march", lord_id=lord, to=destination)
        if lord == "domash" and not destinations:
            _choose(session, "cmd_stone_kremlin", lord_id=lord)
        for _ in range(2):
            _apply(session, "fpd_resolve", decline_pay=True)

    _apply(session, "end_campaign_resolve",
           wastage={"andreas": "provender", "knud_and_abel": "ship"})
    _apply(session, "end_campaign_resolve", wastage={"domash": "provender"})
    _choose(session, "aow_draw")
    _choose(session, "aow_implement_card", card_id="T3")
    return session


def test_vodian_treachery_conquers_fortified_fort_without_spoils(tmp_path):
    session = _save_load(_fortified_fort_session(), tmp_path)
    args = {"card_id": "T3", "target": "kaibolovo"}
    fort = session.state.locales["kaibolovo"]
    assert fort.walls_plus_one
    assert _offered(session, "aow_play_hold", card_id="T3", target="koporye")
    assert _offered(session, "aow_play_hold", **args)

    with pytest.raises(IllegalAction, match="not in your holds"):
        session.apply({"type": "aow_play_hold", "args": args}, who="human")

    castle = _save_load(session, tmp_path)
    castle.state.locales["kaibolovo"].teutonic_castle = True
    castle.state.locales["kaibolovo"].walls_plus_one = False
    assert not _offered(castle, "aow_play_hold", **args)
    _reject(castle, "aow_play_hold", "castle_marker", **args)

    vp = session.state.calendar.teutonic_vp
    assets = {lid: dict(lord.assets) for lid, lord in session.state.lords.items()}
    result = _choose(session, "aow_play_hold", **args)["result"]
    assert (result["teu_dist"], result["rus_dist"]) == (1, 2)
    assert session.state.calendar.teutonic_vp == vp + 1
    assert fort.teutonic_conquered == 1
    assert fort.walls_plus_one
    assert all(lord.assets == assets[lid] for lid, lord in session.state.lords.items())
    assert session.state.decks.teutonic.discard.count("T3") == 1
    _save_load(session, tmp_path)


@pytest.mark.parametrize("legacy", [False, True])
def test_death_of_the_pope_stays_unavailable_through_veche_muster(tmp_path, legacy):
    # Watland seed 14 draws Death of the Pope in its second Levy.
    session = _native_muster(14, 5, "teutonic")
    _advance(session, 3)
    assert session.state.decks.russian.this_levy_events == ["R15"]
    if legacy:
        # Recreate the old save made after an explicit early discard.
        state = session.state
        state.decks.russian.this_levy_events.clear()
        state.decks.russian.discard.append("R15")
        state.meta.sequence += 1
        state.history.append(HistoryEntry(
            sequence=state.meta.sequence,
            actor="russian",
            action={"type": "aow_discard_this_levy", "side": "russian", "args": {}},
            result={"discarded": ["R15"]},
        ))
    session = _save_load(session, tmp_path, identical=not legacy)

    deck = session.state.decks.russian
    assert deck.this_levy_events == ["R15"]
    assert "R15" not in deck.discard
    assert not _offered(session, "aow_discard_this_levy")
    _reject(session, "aow_discard_this_levy", "unknown_action")
    _choose(session, "veche_action", option="C", target_lord="domash")
    assert not _offered(session, "levy_capability", by_lord="domash", card_id="R15")
    _reject(session, "levy_capability", "card_unavailable", by_lord="domash", card_id="R15")
    _choose(session, "levy_capability", by_lord="domash", card_id="R8")
    _advance(session)
    assert not deck.this_levy_events
    assert deck.discard.count("R15") == 1

    _play_to_muster(session, 6, "russian")
    _choose(session, "levy_capability", by_lord="domash", card_id="R15")
    assert deck.capabilities_in_play.count("R15") == 1


def test_heinrich_curia_rejects_invalid_grants_and_adds_mixed_assets(tmp_path):
    session = _native_muster(7, 5, "teutonic")
    result = _choose(session, "muster_lord", by_lord="andreas", target_lord="heinrich", seat="leal")
    assert result["outcome"] == "mustered"
    session = _save_load(session, tmp_path)
    recipients = ["andreas", "knud_and_abel"]
    assert _offered(session, "aow_play_hold", card_id="T13", recipients=recipients)

    for grant, code in (
        ({"coin": 6, "ship": -2}, "bad_grant_count"),
        ({"coin": 3, "boat": True}, "bad_grant_count"),
        ({"coin": 3.5, "ship": 1}, "bad_grant_count"),
        ({"coin": "4"}, "bad_grant_count"),
        ({"coin": 5}, "bad_grant_total"),
        ({"loot": 4}, "loot_forbidden"),
        ({"knights": 4}, "bad_grant_type"),
        ([4], "bad_grant"),
    ):
        _reject(session, "aow_play_hold", code, card_id="T13", recipients=recipients,
                assets={"andreas": {"coin": 4}, "knud_and_abel": grant})
    for assets in (["coin"], {}, {"andreas": {"coin": 4}}):
        _reject(session, "aow_play_hold", "bad_grant", card_id="T13", recipients=recipients,
                assets=assets)
    for bad_recipients in (["andreas", "andreas"], ["andreas", "heinrich"], ["andreas", {}]):
        _reject(session, "aow_play_hold", "bad_recipients",
                card_id="T13", recipients=bad_recipients)

    knud = session.state.lords["knud_and_abel"]
    andreas = session.state.lords["andreas"]
    knud_before, andreas_before = dict(knud.assets), dict(andreas.assets)
    assert knud_before["ship"] == 2
    default = _save_load(session, tmp_path)
    _choose(default, "aow_play_hold", card_id="T13", recipients=recipients)
    assert default.state.lords["knud_and_abel"].assets == {
        **knud_before, "coin": knud_before.get("coin", 0) + 4,
    }

    grants = {"andreas": {"coin": 3, "provender": 1}, "knud_and_abel": {"cart": 2, "boat": 2}}
    result = _apply(session, "aow_play_hold", card_id="T13", recipients=recipients, assets=grants)
    assert result["result"]["distributed"] == grants
    # Callers can clear their nested input buffers after a successful action.
    for grant in grants.values():
        grant.clear()
    grants.clear()
    recipients.clear()
    recorded = session.state.history[-1]
    expected_assets = {
        "andreas": {"coin": 3, "provender": 1},
        "knud_and_abel": {"cart": 2, "boat": 2},
    }
    assert recorded.action["args"]["assets"] == expected_assets
    assert recorded.result["result"]["recipients"] == ["andreas", "knud_and_abel"]
    assert session.history[-1]["action"]["args"] == recorded.action["args"]
    for lord, before in ((knud, knud_before), (andreas, andreas_before)):
        assert lord.assets == {
            **before, **{asset: before.get(asset, 0) + count
                         for asset, count in expected_assets[lord.lord_id].items()},
        }
    assert session.state.lords["heinrich"].state == "disbanded"
    assert "T13" not in session.state.decks.teutonic.holds
    assert session.state.decks.teutonic.discard.count("T13") == 1
    loaded = _save_load(session, tmp_path)

    replay = LLMSession.start_new("watland", llm_side="teutonic", seed=7, confirm_transports=True)
    for item in loaded.history:
        replay.apply(item["action"], who=item["who"])
    assert replay.state.model_dump() == loaded.state.model_dump()
    assert replay.history == loaded.history
