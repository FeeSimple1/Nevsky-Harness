"""Round 21 regressions through the player menu and saved sessions."""
from __future__ import annotations

import pytest

from nevsky.actions import IllegalAction, _place_lord_on_map
from nevsky.llm.session import LLMSession
from nevsky.llm.tools import legal_actions_for_side
from nevsky.scenarios import load_scenario
from nevsky.static_data import load_lords


def _offered(session, kind, **args):
    state = session.state
    return any(m["type"] == kind and all(m.get("args", {}).get(k) == v for k, v in args.items())
               for m in legal_actions_for_side(state, state.meta.active_player))


def _apply(session, kind, **args):
    side = session.state.meta.active_player
    return session.apply({"type": kind, "side": side, "args": args},
                         who="llm" if side == session.llm_side else "human")


def _choose(session, kind, **args):
    assert _offered(session, kind, **args)
    return _apply(session, kind, **args)


def _reject(session, kind, code, **args):
    before = session.state.model_dump_json()
    count = len(session.history)
    with pytest.raises(IllegalAction) as error:
        _apply(session, kind, **args)
    assert error.value.code == code
    assert session.state.model_dump_json() == before
    assert len(session.history) == count


def _save_load(session, tmp_path, *, identical=True):
    path = tmp_path / "nevsky.json"
    session.save(path)
    loaded = LLMSession.load(path)
    if identical:
        assert loaded.state.model_dump_json() == session.state.model_dump_json()
    assert loaded.history == session.history
    return loaded


def _native_muster(seed, box, side):
    session = LLMSession.start_new("watland", llm_side=side, seed=seed,
                                   confirm_transports=True)
    _play_to_muster(session, box, side)
    return session


def _play_to_muster(session, box, side):
    priority = ("aow_draw", "aow_implement_card", "advance_step", "finalize_plan",
                "plan_add_card", "command_reveal", "fpd_resolve", "end_campaign_resolve",
                "disband_resolve")
    for _ in range(100):
        state = session.state
        if (state.meta.box == box and state.meta.phase == "levy"
                and state.meta.levy_step == "muster" and state.meta.active_player == side):
            return
        menu = legal_actions_for_side(state, state.meta.active_player)
        move = next(m for kind in priority for m in menu if m["type"] == kind
                    and (kind != "plan_add_card" or m["args"]["card"] == "pass"))
        args = dict(move.get("args", {}))
        if move["type"] == "fpd_resolve":
            args["decline_pay"] = True
        _apply(session, move["type"], **args)
    raise AssertionError("Native Muster checkpoint was not reached")


def _advance(session, count=1):
    for _ in range(count):
        _choose(session, "advance_step")


def _hold(session, card, lord):
    return _choose(session, "aow_lordship_plus_2", card_id=card, lord_id=lord, mode="lordship")


def _transport(session, lord, count, kind):
    for _ in range(count):
        _choose(session, "levy_transport", by_lord=lord, transport_type=kind)


def _assert_exhausted(session, lord, kind):
    assert not _offered(session, "levy_transport", by_lord=lord)
    _reject(session, "levy_transport", "lordship_exhausted",
            by_lord=lord, transport_type=kind)


@pytest.mark.parametrize("timing,ordinary,extra", [("muster", 4, 2), ("extra", 2, 4), (None, 2, 2)])
def test_native_veche_extra_muster_has_its_own_budget(timing, ordinary, extra, tmp_path):
    session = _native_muster(1, 5, "russian")
    assets_before = dict(session.state.lords["domash"].assets)
    assert session.state.decks.russian.holds == ["R8", "R5"]
    _transport(session, "domash", 2, "boat")
    if timing == "muster":
        _hold(session, "R8", "domash")
        _transport(session, "domash", 2, "boat")
    _assert_exhausted(session, "domash", "boat")
    session = _save_load(session, tmp_path)
    _advance(session, 2)
    assert session.state.meta.lordship_bonus == {}
    _choose(session, "veche_action", option="C", target_lord="domash")
    if timing == "extra":
        _hold(session, "R8", "domash")
    session = _save_load(session, tmp_path)
    _transport(session, "domash", extra, "cart")
    _assert_exhausted(session, "domash", "cart")
    assert session.state.lords["domash"].assets == {**assets_before, "boat": ordinary, "cart": extra}
    assert session.state.veche.vp_markers == 0
    assert session.state.decks.russian.discard.count("R8") == int(timing is not None)


def test_legacy_call_to_arms_save_keeps_assets_and_expires_ordinary_hold(tmp_path):
    session = _native_muster(1, 5, "russian")
    assets_before = dict(session.state.lords["domash"].assets)
    _hold(session, "R8", "domash")
    _transport(session, "domash", 4, "boat")
    _advance(session, 2)
    _choose(session, "veche_action", option="C", target_lord="domash")
    _transport(session, "domash", 1, "cart")
    # Old saves still carried the ordinary +2 after the new grant.
    session.state.meta.lordship_bonus["domash"] = 2
    session = _save_load(session, tmp_path, identical=False)
    assert session.state.meta.lordship_bonus == {}
    assert session.state.lords["domash"].lordship_used == 1
    _transport(session, "domash", 1, "cart")
    _assert_exhausted(session, "domash", "cart")
    assert session.state.lords["domash"].assets == {**assets_before, "boat": 4, "cart": 2}


@pytest.mark.parametrize("card,lord,side,locale", [
    ("T7", "hermann", "teutonic", "dorpat"),
    ("T8", "rudolf", "teutonic", "dorpat"),
    ("T17", "rudolf", "teutonic", "dorpat"),
    ("R13", "vladislav", "russian", "neva"),
])
def test_each_other_hold_expires_before_the_granted_extra_muster(card, lord, side, locale):
    state = load_scenario("crusade_on_novgorod", seed=3)
    if state.lords[lord].state != "mustered":
        # Stage an earlier Muster and travel to a friendly locale.
        _place_lord_on_map(state, lord, locale, state.meta.box)
        state.lords[lord].just_arrived_this_levy = False
    state.meta.levy_step = "muster"
    state.meta.active_player = side
    state.meta.levy_step_completed_t = side == "russian"
    deck = getattr(state.decks, side)
    deck.deck.remove(card)
    deck.holds.append(card)
    session = LLMSession(state, side, "crusade_on_novgorod")
    if side == "teutonic":
        _choose(session, "levy_capability", by_lord="knud_and_abel", card_id="T13")
    base = load_lords()[lord]["ratings"]["lordship"]
    _hold(session, card, lord)
    _transport(session, lord, base + 2, "boat")
    _assert_exhausted(session, lord, "cart")
    _advance(session, 2)
    assert state.meta.lordship_bonus == {}
    if side == "teutonic":
        _choose(session, "legate_arrives", bishopric="dorpat")
        _choose(session, "legate_use", sub_option="2c", target_lord=lord)
    else:
        _choose(session, "veche_action", option="C", target_lord=lord)
    _transport(session, lord, base, "cart")
    _assert_exhausted(session, lord, "cart")
    assert deck.discard.count(card) == 1


@pytest.mark.parametrize("seed", [1, 5])
def test_native_william_acquisition_and_arrival_survive_save_load(seed, tmp_path):
    session = _native_muster(seed, 4, "teutonic")
    s = session.state
    assert s.lords["heinrich"].state == "ready" and s.lords["heinrich"].location is None
    if seed == 1:
        _choose(session, "levy_capability", by_lord="andreas", card_id="T13")
        assert s.lords["andreas"].lordship_used == 1
    else:
        assert any(h.action["type"] == "aow_implement_card" and h.result.get("card") == "T13"
                   for h in s.history)
    assert s.decks.teutonic.capabilities_in_play.count("T13") == 1
    assert s.legate.william_of_modena_in_play and s.legate.location == "card"
    _advance(session, 2)
    session = _save_load(session, tmp_path)
    if seed == 5:
        # A legacy save already had the Capability but left the flag false.
        session.state.legate.william_of_modena_in_play = False
        session = _save_load(session, tmp_path, identical=False)
    _choose(session, "legate_arrives", bishopric="leal")
    _reject(session, "legate_arrives", "legate_already_on_map", bishopric="dorpat")
    if seed == 5:
        # Legacy arrival incorrectly consumed the once-per-segment choice.
        session.state.legate.acted_this_call_to_arms = True
        session = _save_load(session, tmp_path, identical=False)
    assert session.state.legate.locale_id == "leal"
    _choose(session, "legate_use", sub_option="2a", target_lord="heinrich")
    assert session.state.lords["heinrich"].location == "leal"
    assert session.state.legate.location == "card"
    assert not _offered(session, "legate_arrives")
    _reject(session, "legate_arrives", "already_acted", bishopric="dorpat")
    _save_load(session, tmp_path)


def test_native_held_t13_preserves_curia_prerequisite():
    session = _native_muster(7, 5, "teutonic")
    assert "T13" in session.state.decks.teutonic.holds
    assert not _offered(session, "levy_capability", card_id="T13")
    _reject(session, "levy_capability", "card_unavailable", by_lord="andreas", card_id="T13")
    _reject(session, "aow_play_hold", "heinrich_off_map", card_id="T13",
            recipients=["andreas", "knud_and_abel"])


def test_death_of_pope_removes_the_acquired_pawn_and_blocks_same_levy(tmp_path):
    session = _native_muster(14, 4, "teutonic")
    _choose(session, "levy_capability", by_lord="andreas", card_id="T13")
    _advance(session, 2)
    _choose(session, "legate_arrives", bishopric="dorpat")
    _choose(session, "legate_move", locale_id="fellin")
    _reject(session, "legate_move", "already_acted", locale_id="reval")
    _advance(session, 2)
    session = _save_load(session, tmp_path)
    assert session.state.legate.locale_id == "fellin"
    _play_to_muster(session, 5, "teutonic")
    state = session.state
    assert "R15" in state.decks.russian.this_levy_events
    assert state.decks.teutonic.discard.count("T13") == 1
    assert "T13" not in state.decks.teutonic.capabilities_in_play
    assert not state.legate.william_of_modena_in_play and state.legate.locale_id is None
    assert not _offered(session, "levy_capability", card_id="T13")
    _reject(session, "levy_capability", "capability_blocked", by_lord="andreas", card_id="T13")
    _advance(session, 2)
    assert not _offered(session, "legate_arrives")
    _reject(session, "legate_arrives", "no_william", bishopric="dorpat")


def test_teutonic_holds_stack_only_inside_legate_extra_muster(tmp_path):
    state = load_scenario("crusade_on_novgorod", seed=3)
    _place_lord_on_map(state, "rudolf", "dorpat", state.meta.box)
    state.lords["rudolf"].just_arrived_this_levy = False
    state.meta.levy_step = "muster"
    deck = state.decks.teutonic
    for card in ("T8", "T17"):
        deck.deck.remove(card)
        deck.holds.append(card)
    session = LLMSession(state, "teutonic", "crusade_on_novgorod")
    _choose(session, "levy_capability", by_lord="knud_and_abel", card_id="T13")
    base = load_lords()["rudolf"]["ratings"]["lordship"]
    _transport(session, "rudolf", base, "boat")
    _advance(session, 2)
    _reject(session, "aow_lordship_plus_2", "wrong_step",
            card_id="T17", lord_id="rudolf", mode="lordship")
    _choose(session, "legate_arrives", bishopric="dorpat")
    _choose(session, "legate_use", sub_option="2c", target_lord="rudolf")
    _hold(session, "T8", "rudolf")
    _hold(session, "T17", "rudolf")
    session = _save_load(session, tmp_path)
    _transport(session, "rudolf", base + 4, "cart")
    _assert_exhausted(session, "rudolf", "cart")
