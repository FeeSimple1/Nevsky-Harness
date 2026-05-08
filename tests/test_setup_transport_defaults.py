"""Q-001 verification: per-scenario Transport-(any) defaults, overrides,
and auto-confirm flow.

See RULES_DECISIONS.md Q-001 for the canonical default table.
"""

from __future__ import annotations

import pytest

from nevsky.actions import IllegalAction, apply_action
from nevsky.scenarios import load_scenario


# Canonical table per RULES_DECISIONS.md Q-001 + Q-002.
# 16 (any) slot rows + 8 (no Ship) slot rows = 24 total.
EXPECTED_DEFAULTS: list[tuple[str, str, list[str]]] = [
    # Q-001 (any) slots:
    ("pleskau", "gavrilo",   ["cart"]),
    ("pleskau", "vladislav", ["boat"]),
    ("watland", "andreas",   ["sled", "sled"]),
    ("watland", "domash",    ["sled"]),
    ("watland", "vladislav", ["sled"]),
    ("return_of_the_prince", "andreas",   ["ship", "cart"]),
    ("return_of_the_prince", "aleksandr", ["boat", "cart"]),
    ("return_of_the_prince_nicolle", "andreas",   ["ship", "cart"]),
    ("return_of_the_prince_nicolle", "aleksandr", ["boat", "cart"]),
    ("return_of_the_prince_nicolle", "gavrilo",   ["cart"]),
    ("peipus", "aleksandr", ["sled", "sled"]),
    ("peipus", "andrey",    ["sled", "sled"]),
    ("peipus", "domash",    ["sled"]),
    ("peipus", "karelians", ["sled"]),
    ("crusade_on_novgorod", "gavrilo",   ["cart"]),
    ("crusade_on_novgorod", "vladislav", ["boat"]),
    # Q-002 (no Ship) slots:
    ("pleskau", "hermann",  ["cart"]),
    ("pleskau", "yaroslav", ["cart"]),
    ("watland", "yaroslav", ["sled"]),
    ("return_of_the_prince_nicolle", "hermann", ["cart"]),
    ("peipus", "hermann",   ["sled"]),
    ("peipus", "yaroslav",  ["sled"]),
    ("crusade_on_novgorod", "hermann",  ["cart"]),
    ("crusade_on_novgorod", "yaroslav", ["cart"]),
]


@pytest.mark.parametrize("scenario_id,lord_id,defaults", EXPECTED_DEFAULTS,
                         ids=[f"{s}-{l}" for s, l, _ in EXPECTED_DEFAULTS])
def test_q_001_default_values_per_scenario(scenario_id: str, lord_id: str, defaults: list[str]) -> None:
    """Q-001: each scenario / lord / slot defaults to the canonical table value.

    Verified two ways: (a) Lord.assets reflects the chosen Transport pieces
    summed across all slots, and (b) PendingDecisions exist with
    default_value/current_value matching the table.
    """
    s = load_scenario(scenario_id, seed=0)
    # Defaults summed.
    expected_counts: dict[str, int] = {}
    for v in defaults:
        expected_counts[v] = expected_counts.get(v, 0) + 1
    # Read Lord.assets and subtract the static-data starting_assets to
    # isolate the contribution of the (any) slots.
    from nevsky.static_data import load_lords as _ll
    sl = _ll()[lord_id]
    base = {k: int(v) for k, v in sl["starting_assets"].items() if int(v) != 0}
    actual = dict(s.lords[lord_id].assets)
    delta: dict[str, int] = {}
    for k, n in actual.items():
        d = n - base.get(k, 0)
        if d > 0:
            delta[k] = d
    assert delta == expected_counts, f"{scenario_id}/{lord_id} default delta mismatch"

    # PendingDecisions match.
    pds = [pd for pd in s.pending_decisions
           if pd.kind == "setup_transport_choice"
           and pd.context.get("lord_id") == lord_id]
    assert len(pds) == len(defaults)
    for i, expected in enumerate(defaults):
        match = next(pd for pd in pds if pd.context.get("slot_index") == i)
        assert match.context.get("default_value") == expected
        assert match.context.get("current_value") == expected


def test_q_001_player_prompt_hotspots_have_auto_confirm_false() -> None:
    """Q-001 hotspots: Vladislav at Neva (Pleskau, Crusade on Novgorod);
    Aleksandr at Novgorod in Summer scenarios (Return of the Prince,
    Nicolle). These should have auto_confirm_on_levy=False so the
    auto-confirm hook does NOT silently resolve them."""
    for scenario_id, lord_id in [
        ("pleskau", "vladislav"),
        ("crusade_on_novgorod", "vladislav"),
        ("return_of_the_prince", "aleksandr"),
        ("return_of_the_prince_nicolle", "aleksandr"),
    ]:
        s = load_scenario(scenario_id, seed=0)
        pds = [pd for pd in s.pending_decisions
               if pd.kind == "setup_transport_choice"
               and pd.context.get("lord_id") == lord_id]
        assert pds, f"no PendingDecisions for {scenario_id}/{lord_id}"
        for pd in pds:
            assert pd.context.get("auto_confirm_on_levy") is False, \
                f"{scenario_id}/{lord_id} should not auto-confirm"


def test_q_001_other_decisions_have_auto_confirm_true() -> None:
    """Non-hotspot decisions must auto-confirm at first Levy action."""
    s = load_scenario("watland", seed=0)
    for pd in s.pending_decisions:
        if pd.kind != "setup_transport_choice":
            continue
        # Watland has no hotspots.
        assert pd.context.get("auto_confirm_on_levy") is True


def test_q_001_confirm_setup_transport_resolves_pd() -> None:
    """confirm_setup_transport accepts the default; PD removed."""
    s = load_scenario("watland", seed=0)
    pd = next(pd for pd in s.pending_decisions
              if pd.kind == "setup_transport_choice"
              and pd.context.get("lord_id") == "andreas"
              and pd.context.get("slot_index") == 0)
    res = apply_action(s, {
        "type": "confirm_setup_transport", "side": "teutonic",
        "args": {"lord_id": "andreas", "slot_index": 0},
    })
    assert res["value"] == "sled"
    # PD removed.
    assert not any(
        pd.kind == "setup_transport_choice"
        and pd.context.get("lord_id") == "andreas"
        and pd.context.get("slot_index") == 0
        for pd in s.pending_decisions
    )


def test_q_001_set_setup_transport_overrides_default_and_updates_assets() -> None:
    """set_setup_transport replaces a Transport choice; Lord.assets reflect it."""
    s = load_scenario("return_of_the_prince", seed=0)
    # Aleksandr default is [boat, cart]. Override slot 0 from boat to ship.
    pre_boat = s.lords["aleksandr"].assets.get("boat", 0)
    pre_ship = s.lords["aleksandr"].assets.get("ship", 0)
    apply_action(s, {
        "type": "set_setup_transport", "side": "russian",
        "args": {"lord_id": "aleksandr", "slot_index": 0, "value": "ship"},
    })
    assert s.lords["aleksandr"].assets.get("boat", 0) == pre_boat - 1
    assert s.lords["aleksandr"].assets.get("ship", 0) == pre_ship + 1


def test_q_001_set_setup_transport_rejects_invalid_value() -> None:
    s = load_scenario("watland", seed=0)
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {
            "type": "set_setup_transport", "side": "teutonic",
            "args": {"lord_id": "andreas", "slot_index": 0, "value": "horse"},
        })
    assert exc.value.code == "bad_value"


def test_q_001_confirm_all_setup_transports_bulk_resolves_side() -> None:
    """confirm_all_setup_transports clears all PDs for one side."""
    s = load_scenario("watland", seed=0)
    apply_action(s, {
        "type": "confirm_all_setup_transports", "side": "teutonic",
        "args": {},
    })
    # Teutonic decisions cleared.
    assert all(pd.owed_by != "teutonic" for pd in s.pending_decisions
               if pd.kind == "setup_transport_choice")
    # Russian decisions still there.
    assert any(pd.owed_by == "russian" for pd in s.pending_decisions
               if pd.kind == "setup_transport_choice")


def test_q_001_auto_confirm_at_first_levy_action_clears_default_pds() -> None:
    """First Levy action by a side auto-confirms its
    auto_confirm_on_levy=True PDs. Hotspot PDs persist."""
    s = load_scenario("pleskau", seed=0)
    # Pleskau hotspot is vladislav.
    pre = [pd for pd in s.pending_decisions
           if pd.kind == "setup_transport_choice"]
    assert pre, "scenario should have setup PDs"
    # First Levy action: aow_shuffle by teutonic.
    apply_action(s, {"type": "aow_shuffle", "side": "teutonic", "args": {}})
    # Teutonic auto-confirm PDs cleared.
    teu_default = [pd for pd in s.pending_decisions
                    if pd.kind == "setup_transport_choice"
                    and pd.owed_by == "teutonic"
                    and pd.context.get("auto_confirm_on_levy", True)]
    assert teu_default == []
    # Hotspot vladislav (russian) still there until russian acts.
    rus_left = [pd for pd in s.pending_decisions
                if pd.kind == "setup_transport_choice"
                and pd.owed_by == "russian"]
    assert any(pd.context.get("lord_id") == "vladislav" for pd in rus_left)


def test_q_001_hotspot_does_not_auto_confirm() -> None:
    """auto_confirm_on_levy=False decisions persist past the first
    Levy action by that side."""
    s = load_scenario("pleskau", seed=0)
    apply_action(s, {"type": "aow_shuffle", "side": "teutonic", "args": {}})
    # russian's first Levy action.
    apply_action(s, {"type": "advance_step", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "aow_shuffle", "side": "russian", "args": {}})
    # vladislav decision persists (hotspot).
    rus_left = [pd for pd in s.pending_decisions
                if pd.kind == "setup_transport_choice"
                and pd.owed_by == "russian"]
    assert any(pd.context.get("lord_id") == "vladislav" for pd in rus_left)


# --- Q-002 additions -------------------------------------------------------


def test_q_002_rudolf_no_setup_transport_pd_at_load() -> None:
    """Q-002 carve-out: Rudolf is on the Calendar at scenario start in
    every scenario; no setup_transport_choice PendingDecision is
    emitted at load."""
    for scenario in [
        "pleskau", "watland", "return_of_the_prince",
        "return_of_the_prince_nicolle", "peipus", "crusade_on_novgorod",
    ]:
        s = load_scenario(scenario, seed=0)
        rudolf_pds = [
            pd for pd in s.pending_decisions
            if pd.kind == "setup_transport_choice"
            and pd.context.get("lord_id") == "rudolf"
        ]
        assert rudolf_pds == [], f"{scenario}: rudolf has setup PDs at load"


def test_q_002_heuristic_matches_table_for_every_row() -> None:
    """Q-002: the heuristic decision tree must produce the same defaults
    the canonical table does for every (scenario, lord) row. This
    prevents the table and heuristic from drifting."""
    from nevsky.scenarios import (
        _heuristic_setup_transport_default,
        _season_for_box,
        load_scenario_raw,
    )
    from nevsky.static_data import load_lords as _ll
    static = _ll()
    for scenario_id, lord_id, expected in EXPECTED_DEFAULTS:
        raw = load_scenario_raw(scenario_id)
        # Look up the Lord's start locale from setup.mustered_lords.
        mreq = next(
            m for m in raw["setup"]["mustered_lords"]
            if m["lord_id"] == lord_id
        )
        locale = mreq["locale_id"]
        season = _season_for_box(int(raw["span"]["start_box"]))
        slot_count = sum(int(s["count"]) for s in static[lord_id].get("starting_transport_choice", []))
        if slot_count == 0:
            continue
        first_allowed = list(static[lord_id]["starting_transport_choice"][0]["options"])
        actual = _heuristic_setup_transport_default(
            scenario_id, lord_id, locale, season, slot_count, first_allowed,
        )
        # Replace any "ship" the heuristic produced for a non-Ship slot
        # with allowed[0] (the loader's fallback rule).
        actual_clamped = [v if v in first_allowed else first_allowed[0] for v in actual]
        assert actual_clamped == expected, (
            f"{scenario_id}/{lord_id}: heuristic {actual_clamped} != table {expected}"
        )


def test_q_002_no_ship_slots_have_three_value_allowed() -> None:
    """(no Ship) slots emit allowed_values = [boat, cart, sled] (no ship)."""
    s = load_scenario("pleskau", seed=0)
    pds = [pd for pd in s.pending_decisions
           if pd.kind == "setup_transport_choice"
           and pd.context.get("lord_id") in ("hermann", "yaroslav")]
    assert pds, "pleskau should have hermann + yaroslav setup PDs"
    for pd in pds:
        assert "ship" not in pd.context.get("allowed_values", [])
        assert set(pd.context.get("allowed_values", [])) == {"boat", "cart", "sled"}


def test_q_002_any_slots_have_four_value_allowed() -> None:
    """(any) slots emit allowed_values = [boat, cart, sled, ship]."""
    s = load_scenario("watland", seed=0)
    pds = [pd for pd in s.pending_decisions
           if pd.kind == "setup_transport_choice"
           and pd.context.get("lord_id") == "andreas"]
    assert pds
    for pd in pds:
        assert set(pd.context.get("allowed_values", [])) == {"boat", "cart", "sled", "ship"}


def test_q_002_rudolf_emits_pd_when_mustered() -> None:
    """Q-002: when Rudolf is Mustered (Phase 2 path), the harness
    emits a setup_transport_choice PendingDecision and applies the
    heuristic default."""
    from nevsky.actions import _place_lord_on_map, _find_levy_marker_box
    s = load_scenario("pleskau", seed=0)
    levy_box = _find_levy_marker_box(s)
    # Rudolf is "ready" at load.
    assert s.lords["rudolf"].state == "ready"
    # Bring him on at riga (Bishopric, Seaport, Crusader Livonia).
    _place_lord_on_map(s, "rudolf", "riga", levy_box)
    rudolf_pds = [
        pd for pd in s.pending_decisions
        if pd.kind == "setup_transport_choice"
        and pd.context.get("lord_id") == "rudolf"
    ]
    assert rudolf_pds, "rudolf should have a setup PD after Muster"
    # rudolf is (no Ship); allowed must exclude ship.
    pd = rudolf_pds[0]
    assert "ship" not in pd.context["allowed_values"]
    assert pd.context.get("emitted_at_muster") is True
