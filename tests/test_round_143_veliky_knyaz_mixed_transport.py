"""SMOKE-104 (Round 143): R17 Veliky Knyaz Tax restricted Transport
to a single type; per AoW Reference Tip "any two Transport (up to the
maximum of eight per type)" the player may pick mixed types.

Pre-fix the harness accepted `transport_type` (single string) and
added 2 of that type. Mixed picks (e.g. 1 Cart + 1 Boat) were not
expressible. Same audit pattern as SMOKE-046/048/067/102 (rule-cite-
but-no-enforce, relaxation direction).

Fix adds backward-compatible `transport_choices` arg (dict
{type: count} summing to 2). Legacy `transport_type` still works.
Ship still requires ships_authorized. 8-cap-per-type honored.
"""
from __future__ import annotations

import inspect

import nevsky.actions  # noqa: F401
import nevsky.campaign as camp
import pytest
from nevsky.actions import IllegalAction, apply_action
from nevsky.scenarios import load_scenario


def _setup_tax_state(scenario="watland", seed=1, lord_caps=("R17",)):
    s = load_scenario(scenario, seed=seed)
    s.meta.phase = "campaign"
    s.meta.campaign_step = "command"
    s.meta.active_player = "russian"
    rus = next(lid for lid, l in s.lords.items()
               if l.side == "russian" and l.state == "mustered")
    s.lords[rus].this_lord_capabilities = list(lord_caps)
    # Move to own seat.
    from nevsky.static_data import load_lords
    seat = load_lords()[rus]["primary_seats"][0]
    s.lords[rus].location = seat
    s.campaign_turn.active_card = rus
    s.campaign_turn.active_lord = rus
    # Tax is an entire-card Command (R203): requires a pristine full
    # Command card, so set the budget to the Lord's full command rating.
    import nevsky.campaign as _camp
    s.campaign_turn.actions_remaining = _camp._effective_command_rating(s, rus)
    s.lords[rus].assets["coin"] = 0  # ensure room
    s.lords[rus].assets["cart"] = 0
    s.lords[rus].assets["boat"] = 0
    return s, rus


def test_smoke_104_marker_present():
    src = inspect.getsource(camp._h_cmd_tax_veliky_knyaz_aware)
    assert "SMOKE-104" in src
    assert "transport_choices" in src


def test_smoke_104_legacy_single_type_still_works():
    s, rus = _setup_tax_state()
    res = apply_action(s, {"type": "cmd_tax", "side": "russian",
                            "args": {"lord_id": rus, "transport_type": "cart"}})
    assert s.lords[rus].assets["cart"] == 2
    assert "veliky_knyaz_transport_added" in res
    # Legacy summary shape preserved when single type.
    info = res["veliky_knyaz_transport_added"]
    assert info["type"] == "cart"
    assert info["count"] == 2


def test_smoke_104_mixed_types_allowed():
    s, rus = _setup_tax_state()
    res = apply_action(s, {"type": "cmd_tax", "side": "russian",
                            "args": {"lord_id": rus,
                                     "transport_choices": {"cart": 1, "boat": 1}}})
    assert s.lords[rus].assets["cart"] == 1
    assert s.lords[rus].assets["boat"] == 1
    info = res["veliky_knyaz_transport_added"]
    assert info["count"] == 2
    assert "by_type" in info
    assert info["by_type"] == {"cart": 1, "boat": 1}


def test_smoke_104_total_must_equal_2():
    s, rus = _setup_tax_state()
    # Total 3 -> rejected.
    with pytest.raises(IllegalAction):
        apply_action(s, {"type": "cmd_tax", "side": "russian",
                          "args": {"lord_id": rus,
                                   "transport_choices": {"cart": 2, "boat": 1}}})


def test_smoke_104_total_zero_rejected():
    s, rus = _setup_tax_state()
    with pytest.raises(IllegalAction):
        apply_action(s, {"type": "cmd_tax", "side": "russian",
                          "args": {"lord_id": rus,
                                   "transport_choices": {"cart": 0, "boat": 0}}})


def test_smoke_104_invalid_type_rejected():
    s, rus = _setup_tax_state()
    with pytest.raises(IllegalAction):
        apply_action(s, {"type": "cmd_tax", "side": "russian",
                          "args": {"lord_id": rus,
                                   "transport_choices": {"cart": 1, "horse": 1}}})


def test_smoke_104_ship_requires_authorization(monkeypatch):
    s, rus = _setup_tax_state()
    # R205: every Russian Lord is ships_authorized, so this guard's
    # rejection path was unreachable for any real Lord and the test
    # always skipped. Force this Lord non-authorized (auto-restored by
    # monkeypatch) to deterministically exercise the ship_unauthorized
    # guard in _h_cmd_tax_veliky_knyaz_aware.
    from nevsky.static_data import load_lords
    monkeypatch.setitem(load_lords()[rus], "ships_authorized", False)
    with pytest.raises(IllegalAction):
        apply_action(s, {"type": "cmd_tax", "side": "russian",
                          "args": {"lord_id": rus,
                                   "transport_choices": {"ship": 1, "cart": 1}}})


def test_smoke_104_per_type_cap_at_8():
    s, rus = _setup_tax_state()
    s.lords[rus].assets["cart"] = 7
    s.lords[rus].assets["boat"] = 8
    # Trying 1 cart + 1 boat: cart caps at +1 (7->8), boat at +0 (already 8).
    res = apply_action(s, {"type": "cmd_tax", "side": "russian",
                            "args": {"lord_id": rus,
                                     "transport_choices": {"cart": 1, "boat": 1}}})
    assert s.lords[rus].assets["cart"] == 8
    assert s.lords[rus].assets["boat"] == 8


def test_smoke_104_without_veliky_knyaz_choices_ignored():
    """Without R17, the choices arg path doesn't fire (no transport added)."""
    s, rus = _setup_tax_state(lord_caps=())
    res = apply_action(s, {"type": "cmd_tax", "side": "russian",
                            "args": {"lord_id": rus,
                                     "transport_choices": {"cart": 1, "boat": 1}}})
    # No transport added (R17 not in capabilities).
    assert s.lords[rus].assets.get("cart", 0) == 0
    assert s.lords[rus].assets.get("boat", 0) == 0
    assert "veliky_knyaz_transport_added" not in res
