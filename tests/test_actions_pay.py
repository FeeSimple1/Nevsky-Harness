"""Tests for 3.2 Pay handlers."""

from __future__ import annotations

import pytest

from nevsky.actions import IllegalAction, _find_service_marker_box, apply_action
from nevsky.llm.session import LLMSession
from nevsky.scenarios import load_scenario
from nevsky.state import GameState, vassal_marker_box


def _to_pay_step(s: GameState) -> None:
    """Advance state from arts_of_war to pay (test helper)."""
    s.meta.levy_step = "pay"
    s.meta.active_player = "teutonic"
    s.meta.levy_step_completed_t = False
    s.meta.levy_step_completed_r = False


def _give_lord_coin(s: GameState, lid: str, n: int = 3) -> None:
    s.lords[lid].assets["coin"] = n


def _give_lord_loot(s: GameState, lid: str, n: int = 3) -> None:
    s.lords[lid].assets["loot"] = n


def _service_box(s: GameState, lid: str) -> int | None:
    if lid in s.calendar.off_right:
        return 17
    for cb in s.calendar.boxes:
        if lid in cb.service_markers:
            return cb.box
    return None


def test_pay_with_coin_own_service_shifts_one_box(tmp_path) -> None:
    """3.2.1: Lord pays own Coin to shift own Service marker right."""
    s = load_scenario("watland", seed=42)
    _to_pay_step(s)
    teu_mustered = [lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered"]
    payer = teu_mustered[0]
    pre = _service_box(s, payer)
    assert pre is not None
    _give_lord_coin(s, payer, 2)
    apply_action(s, {
        "type": "pay_with_coin", "side": "teutonic",
        "args": {"from": f"lord:{payer}", "target_lord": payer, "units": 1},
    })
    assert _service_box(s, payer) == min(pre + 1, 17)
    assert s.lords[payer].assets.get("coin", 0) == 1


def test_pay_with_coin_insufficient_funds_raises() -> None:
    s = load_scenario("watland", seed=42)
    _to_pay_step(s)
    payer = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[payer].assets.pop("coin", None)
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {
            "type": "pay_with_coin", "side": "teutonic",
            "args": {"from": f"lord:{payer}", "target_lord": payer, "units": 1},
        })
    assert exc.value.code == "insufficient_funds"


def test_pay_with_veche_coin_blocked_for_besieged_lord() -> None:
    """3.2.1: Veche Coin cannot reach a Besieged Russian Lord."""
    s = load_scenario("watland", seed=42)
    _to_pay_step(s)
    s.meta.active_player = "russian"
    s.meta.levy_step_completed_t = True
    s.veche.coin = 4
    target = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    # Besiege the target Lord inside his Stronghold.
    s.locales[s.lords[target].location].siege_markers = 1
    s.lords[target].in_stronghold = True
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {
            "type": "pay_with_coin", "side": "russian",
            "args": {"from": "veche", "target_lord": target, "units": 1},
        })
    assert exc.value.code == "veche_cannot_reach_besieged"


def test_pay_with_veche_coin_consumes_and_shifts() -> None:
    s = load_scenario("watland", seed=42)
    _to_pay_step(s)
    s.meta.active_player = "russian"
    s.meta.levy_step_completed_t = True
    s.veche.coin = 4
    target = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    pre = _service_box(s, target)
    apply_action(s, {
        "type": "pay_with_coin", "side": "russian",
        "args": {"from": "veche", "target_lord": target, "units": 2},
    })
    assert s.veche.coin == 2
    assert _service_box(s, target) == min(pre + 2, 17)


def test_pay_with_loot_requires_friendly_locale() -> None:
    """3.2.2: Loot may only be spent at a Friendly Locale."""
    s = load_scenario("watland", seed=42)
    _to_pay_step(s)
    payer = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    _give_lord_loot(s, payer, 3)
    # Place a Russian Lord at the same locale to make the locale unfriendly.
    rus_lord = next(lid for lid, l in s.lords.items() if l.side == "russian" and l.state == "mustered")
    s.lords[rus_lord].location = s.lords[payer].location
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {
            "type": "pay_with_loot", "side": "teutonic",
            "args": {"from_lord": payer, "target_lord": payer, "units": 1},
        })
    assert exc.value.code == "loot_locale_constraint"


def test_pay_co_located_other_lord_allowed() -> None:
    """3.2.1: Lord-Coin can pay co-located own-side Lord's Service."""
    s = load_scenario("watland", seed=42)
    _to_pay_step(s)
    teu = [lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered"]
    payer, target = teu[0], teu[1]
    _give_lord_coin(s, payer, 3)
    s.lords[target].location = s.lords[payer].location  # co-locate
    pre = _service_box(s, target)
    apply_action(s, {
        "type": "pay_with_coin", "side": "teutonic",
        "args": {"from": f"lord:{payer}", "target_lord": target, "units": 1},
    })
    assert _service_box(s, target) == min(pre + 1, 17)


def test_pay_lord_coin_different_locale_rejected() -> None:
    """3.2.1: cannot Pay another Lord's Service from a different Locale."""
    s = load_scenario("watland", seed=42)
    _to_pay_step(s)
    teu = [lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered"]
    if len(teu) < 2:
        pytest.skip("watland mustered Teuton lord count < 2")
    payer, target = teu[0], teu[1]
    _give_lord_coin(s, payer, 3)
    # Ensure they are at different locations.
    if s.lords[payer].location == s.lords[target].location:
        # Put target somewhere else; pick any locale id.
        s.lords[target].location = "novgorod"
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {
            "type": "pay_with_coin", "side": "teutonic",
            "args": {"from": f"lord:{payer}", "target_lord": target, "units": 1},
        })
    assert exc.value.code == "pay_target_not_collocated"


def _peipus_pay(advanced: bool = False) -> LLMSession:
    session = LLMSession.start_new("peipus", llm_side="russian", seed=1, confirm_transports=True)
    if advanced:
        session.state.meta.optional_rules["advanced_vassal_service"] = True
    for who, menu in (("human", session.legal_actions_for_human), ("llm", session.legal_actions)):
        session.apply({"type": "aow_draw"}, who=who)
        for _ in range(2):
            session.apply(next(m for m in menu() if m["type"] == "aow_implement_card"), who=who)
        session.apply({"type": "advance_step"}, who=who)
    session.apply({"type": "advance_step"}, who="human")
    assert session.state.meta.levy_step == "pay"
    assert session.state.meta.active_player == "russian"
    return session


def _veche_pay(units=1, target="aleksandr"):
    return {
        "type": "pay_with_coin",
        "args": {"from": "veche", "target_lord": target, "units": units},
    }


def _pay_candidates(session, payer):
    return next(m["candidates"] for m in session.legal_actions()
                if m["type"] in ("pay_with_coin", "pay_with_loot")
                and payer in m["candidates"]["payers"])


def _assert_pay_rejected(session, action, code="pay_exceeds_service_limit"):
    before = session.state.model_dump_json()
    history_length = len(session.history)
    with pytest.raises(IllegalAction) as exc:
        session.apply(action)
    assert exc.value.code == code
    assert session.state.model_dump_json() == before
    assert len(session.history) == history_length


def test_veche_pay_stops_at_calendar_edge():
    session = _peipus_pay()
    state = session.state
    assert _find_service_marker_box(state, "aleksandr") == 16
    assert state.veche.coin == 3
    _assert_pay_rejected(session, _veche_pay(4), "insufficient_funds")
    _assert_pay_rejected(session, _veche_pay(2))
    assert _pay_candidates(session, "veche")["service_steps"]["aleksandr"] == 1

    assert session.apply(_veche_pay())["new_box"] == 17
    assert state.veche.coin == 2
    assert "aleksandr" not in _pay_candidates(session, "veche")["targets"]
    _assert_pay_rejected(session, _veche_pay())
    assert session.apply(_veche_pay(2, "karelians"))["new_box"] == 16
    assert state.veche.coin == 0


@pytest.mark.parametrize("resource", ["coin", "loot"])
def test_off_right_lord_can_pay_for_colocated_service(resource):
    session = _peipus_pay()
    assert session.apply(_veche_pay(target="domash"))["new_box"] == 17
    payer = session.state.lords["domash"]
    payer.assets[resource] = 2
    kind, source = (
        ("pay_with_coin", {"from": "lord:domash"})
        if resource == "coin" else ("pay_with_loot", {"from_lord": "domash"})
    )
    action = {"type": kind, "args": {**source, "target_lord": "aleksandr", "units": 2}}
    targets = _pay_candidates(session, "domash")["targets_by_payer"]["domash"]
    assert "aleksandr" in targets and "domash" not in targets
    _assert_pay_rejected(session, action)

    action["args"]["units"] = 1
    assert session.apply(action)["new_box"] == 17
    assert payer.assets[resource] == 1
    assert "aleksandr" not in _pay_candidates(session, "domash")["targets"]
    _assert_pay_rejected(session, action)


def test_campaign_pay_for_off_right_lord_advances_vassals_after_reload(tmp_path):
    session = _peipus_pay(advanced=True)
    session.apply(_veche_pay())
    for who in ("llm", "human", "llm", "human"):
        session.apply({"type": "advance_step"}, who=who)
    assert session.state.meta.levy_step == "muster"
    vassals = ("aleksandr_rostov", "aleksandr_yaroslavl")
    for vid in vassals:
        session.apply({"type": "muster_vassal", "args": {"by_lord": "aleksandr", "vassal_id": vid}})
    for who in ("llm", "human", "llm"):
        session.apply({"type": "advance_step"}, who=who)
    for who in ("human", "llm"):
        for _ in range(4):
            session.apply({"type": "plan_add_card", "args": {"card": "pass"}}, who=who)
        session.apply({"type": "finalize_plan"}, who=who)
    session.apply({"type": "command_reveal"}, who="human")
    session.apply({"type": "fpd_resolve", "args": {"decline_pay": True}}, who="human")
    assert session.apply({"type": "fpd_resolve"})["pay_window"]

    path = tmp_path / "campaign_pay.json"
    session.save(path)
    restored = LLMSession.load(path)
    for position in (session, restored):
        state = position.state
        aleksandr = state.lords["aleksandr"]
        assert _find_service_marker_box(state, "aleksandr") == 17
        assert state.veche.coin == 2
        for vid in vassals:
            assert vassal_marker_box(state.calendar, vid, aleksandr.vassals[vid]) == 16
        _assert_pay_rejected(position, _veche_pay(2))
        assert _pay_candidates(position, "veche")["service_steps"]["aleksandr"] == 1
        assert position.apply(_veche_pay())["new_box"] == 17
        assert state.veche.coin == 1
        for vid in vassals:
            assert vassal_marker_box(state.calendar, vid, aleksandr.vassals[vid]) == 17
        assert "aleksandr" not in _pay_candidates(position, "veche")["targets"]
        _assert_pay_rejected(position, _veche_pay())
    assert restored.state.model_dump() == session.state.model_dump()
    assert restored.history == session.history
