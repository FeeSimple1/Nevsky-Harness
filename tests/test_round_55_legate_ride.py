"""Round 55 — SMOKE-043 regression tests.

4.1.1 / Misc Rules: "The Legate may March (4.3) or Sail (4.7.3) along
with any Teutonic Lord he is co-located with — at the Lord's
discretion." `args.take_legate=True` opts the Lord into bringing the
Legate. Russian Lords are forbidden; the Legate must be co-located
with the active Lord at the move source.
"""

import pytest

import nevsky.actions  # noqa
from nevsky.scenarios import load_scenario
from nevsky.actions import apply_action, IllegalAction
from nevsky.static_data import load_ways


def _adj(src):
    for w in load_ways():
        if w["a"] == src: return w["b"]
        if w["b"] == src: return w["a"]
    return None


def _setup_teu_march(st, lid):
    L = st.lords[lid]
    L.in_stronghold = False
    L.assets["provender"] = 0
    st.legate.william_of_modena_in_play = True
    st.legate.location = "locale"
    st.legate.locale_id = L.location
    st.meta.phase = "campaign"
    st.meta.campaign_step = "command"
    st.campaign_turn.active_lord = lid
    st.campaign_turn.active_card = lid
    st.campaign_turn.actions_remaining = 5


def test_legate_rides_with_take_legate_true():
    st = load_scenario("pleskau", seed=1)
    _setup_teu_march(st, "hermann")
    dest = _adj(st.lords["hermann"].location)
    res = apply_action(st, {"type": "cmd_march", "side": "teutonic",
                           "args": {"lord_id": "hermann", "to": dest,
                                    "group": ["hermann"], "take_legate": True}})
    assert st.legate.locale_id == dest
    assert res.get("legate_carried", {}).get("took_legate") is True


def test_legate_stays_with_take_legate_false():
    st = load_scenario("pleskau", seed=1)
    _setup_teu_march(st, "hermann")
    src = st.lords["hermann"].location
    dest = _adj(src)
    apply_action(st, {"type": "cmd_march", "side": "teutonic",
                     "args": {"lord_id": "hermann", "to": dest, "group": ["hermann"]}})
    # Default is take_legate=False; Legate stays put
    assert st.legate.locale_id == src


def test_russian_cannot_take_legate():
    st = load_scenario("pleskau", seed=1)
    g = st.lords["gavrilo"]
    g.in_stronghold = False
    g.assets["provender"] = 0
    st.legate.william_of_modena_in_play = True
    st.legate.location = "locale"
    st.legate.locale_id = g.location
    st.meta.phase = "campaign"
    st.meta.campaign_step = "command"
    st.campaign_turn.active_lord = "gavrilo"
    st.campaign_turn.active_card = "gavrilo"
    st.campaign_turn.actions_remaining = 5
    dest = _adj(g.location)
    with pytest.raises(IllegalAction) as exc:
        apply_action(st, {"type": "cmd_march", "side": "russian",
                          "args": {"lord_id": "gavrilo", "to": dest,
                                   "group": ["gavrilo"], "take_legate": True}})
    assert exc.value.code == "not_teutonic"


def test_legate_must_be_co_located():
    st = load_scenario("pleskau", seed=1)
    h = st.lords["hermann"]
    h.in_stronghold = False
    h.assets["provender"] = 0
    st.legate.william_of_modena_in_play = True
    st.legate.location = "locale"
    # Legate at a DIFFERENT locale
    st.legate.locale_id = "reval" if h.location != "reval" else "leal"
    st.meta.phase = "campaign"
    st.meta.campaign_step = "command"
    st.campaign_turn.active_lord = "hermann"
    st.campaign_turn.active_card = "hermann"
    st.campaign_turn.actions_remaining = 5
    dest = _adj(h.location)
    with pytest.raises(IllegalAction) as exc:
        apply_action(st, {"type": "cmd_march", "side": "teutonic",
                          "args": {"lord_id": "hermann", "to": dest,
                                   "group": ["hermann"], "take_legate": True}})
    assert exc.value.code == "legate_not_co_located"


def test_legate_not_in_play_rejected():
    st = load_scenario("pleskau", seed=1)
    h = st.lords["hermann"]
    h.in_stronghold = False
    h.assets["provender"] = 0
    st.legate.william_of_modena_in_play = False
    st.meta.phase = "campaign"
    st.meta.campaign_step = "command"
    st.campaign_turn.active_lord = "hermann"
    st.campaign_turn.active_card = "hermann"
    st.campaign_turn.actions_remaining = 5
    dest = _adj(h.location)
    with pytest.raises(IllegalAction) as exc:
        apply_action(st, {"type": "cmd_march", "side": "teutonic",
                          "args": {"lord_id": "hermann", "to": dest,
                                   "group": ["hermann"], "take_legate": True}})
    assert exc.value.code == "legate_not_in_play"


def test_legate_sail_ride_along():
    st = load_scenario("pleskau", seed=1)
    h = st.lords["hermann"]
    h.location = "reval"
    h.in_stronghold = False
    h.assets["provender"] = 0
    st.legate.william_of_modena_in_play = True
    st.legate.location = "locale"
    st.legate.locale_id = "reval"
    st.locales["reval"].siege_markers = 0
    st.meta.box = 8  # summer-ish
    st.meta.phase = "campaign"
    st.meta.campaign_step = "command"
    st.campaign_turn.active_lord = "hermann"
    st.campaign_turn.active_card = "hermann"
    st.campaign_turn.actions_remaining = 5
    res = apply_action(st, {"type": "cmd_sail", "side": "teutonic",
                           "args": {"lord_id": "hermann", "destination": "narwia",
                                    "group": ["hermann"], "take_legate": True}})
    assert st.legate.locale_id == "narwia"
    assert res.get("legate_carried", {}).get("took_legate") is True
