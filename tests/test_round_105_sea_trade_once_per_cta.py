"""SMOKE-092 (Round 105): R8/R9 sea_trade allows multiple fires per
Call to Arms.

Per AoW Reference:
  R8 Black Sea Trade: "Each Call to Arms, add 1 Coin to Veche..."
  R9 Baltic Sea Trade: "Each non-Winter Call to Arms, add 2 Coin..."

"Each" means once per CtA. The harness's `_veche_sea_trade` didn't
track per-card usage, allowing repeated invocations to add multiple
Coin in a single CtA.

Fix uses `state.meta.special_rules["sea_trade_<cid>_used_this_cta"]`
flags, gated and cleared at the CtA boundary in `_h_advance_step`.
"""
from __future__ import annotations

import pytest

import nevsky.actions  # noqa: F401
from nevsky.actions import IllegalAction, _veche_sea_trade
from nevsky.scenarios import load_scenario


def test_r8_rejects_second_invocation_in_same_cta():
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.decks.russian.capabilities_in_play.append("R8")
    s.meta.phase = "levy"
    s.meta.levy_step = "call_to_arms"
    s.meta.active_player = "russian"
    s.veche.coin = 0
    s.locales["novgorod"].teutonic_conquered = 0
    s.locales["lovat"].teutonic_conquered = 0
    r1, _ = _veche_sea_trade(s, {"card_id": "R8"})
    assert r1["added"] == 1
    with pytest.raises(IllegalAction) as e:
        _veche_sea_trade(s, {"card_id": "R8"})
    assert e.value.code == "sea_trade_already_used"


def test_r9_rejects_second_invocation_in_same_cta():
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.decks.russian.capabilities_in_play.append("R9")
    s.meta.phase = "levy"
    s.meta.levy_step = "call_to_arms"
    s.meta.active_player = "russian"
    s.meta.box = 1  # Summer (non-Winter)
    s.veche.coin = 0
    s.locales["novgorod"].teutonic_conquered = 0
    s.locales["neva"].teutonic_conquered = 0
    # Ensure Russians have >= Teutonic ships (R9 check)
    for tlord in s.lords.values():
        if tlord.side == "teutonic":
            tlord.assets.pop("ship", None)
    aleksandr = s.lords.get("aleksandr")
    if aleksandr:
        aleksandr.state = "mustered"
        aleksandr.location = "novgorod"
        aleksandr.assets["ship"] = 4
    r1, _ = _veche_sea_trade(s, {"card_id": "R9"})
    assert r1["added"] == 2
    with pytest.raises(IllegalAction) as e:
        _veche_sea_trade(s, {"card_id": "R9"})
    assert e.value.code == "sea_trade_already_used"


def test_r8_and_r9_independent_per_cta():
    """R8 firing once doesn't block R9 from also firing in the same CtA."""
    s = load_scenario("crusade_on_novgorod", seed=1)
    s.decks.russian.capabilities_in_play.extend(["R8", "R9"])
    s.meta.phase = "levy"
    s.meta.levy_step = "call_to_arms"
    s.meta.active_player = "russian"
    s.meta.box = 1
    s.veche.coin = 0
    s.locales["novgorod"].teutonic_conquered = 0
    s.locales["lovat"].teutonic_conquered = 0
    s.locales["neva"].teutonic_conquered = 0
    # Ensure Russians have >= Teutonic ships (R9 check)
    for tlord in s.lords.values():
        if tlord.side == "teutonic":
            tlord.assets.pop("ship", None)
    aleksandr = s.lords.get("aleksandr")
    if aleksandr:
        aleksandr.state = "mustered"
        aleksandr.location = "novgorod"
        aleksandr.assets["ship"] = 4
    r1, _ = _veche_sea_trade(s, {"card_id": "R8"})
    assert r1["added"] == 1
    r2, _ = _veche_sea_trade(s, {"card_id": "R9"})
    assert r2["added"] == 2
    assert s.veche.coin == 3
