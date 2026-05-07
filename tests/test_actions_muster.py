"""Tests for 3.4 Muster."""

from __future__ import annotations

import pytest

from nevsky.actions import IllegalAction, apply_action
from nevsky.scenarios import load_scenario
from nevsky.state import GameState


def _to_muster_step(s: GameState, side: str = "teutonic") -> None:
    s.meta.levy_step = "muster"
    s.meta.active_player = side
    s.meta.levy_step_completed_t = side == "russian"
    s.meta.levy_step_completed_r = False
    for l in s.lords.values():
        l.lordship_used = 0
        l.just_arrived_this_levy = False


def _find_levy_box(s: GameState) -> int:
    for cb in s.calendar.boxes:
        if cb.has_levy_campaign_marker:
            return cb.box
    raise AssertionError("no Levy marker")


def _put_cylinder_at(s: GameState, lid: str, box: int) -> None:
    for cb in s.calendar.boxes:
        if lid in cb.cylinders:
            cb.cylinders.remove(lid)
    if lid in s.calendar.off_left:
        s.calendar.off_left.remove(lid)
    if lid in s.calendar.off_right:
        s.calendar.off_right.remove(lid)
    s.calendar.boxes[box - 1].cylinders.append(lid)


def test_aleksandr_cannot_be_mustered_by_lord() -> None:
    """3.4.1: Aleksandr is NEVER Mustered by any Lord (Veche-only)."""
    s = load_scenario("return_of_the_prince", seed=42)
    _to_muster_step(s, side="russian")
    by_id = next(
        lid for lid, l in s.lords.items()
        if l.side == "russian" and l.state == "mustered"
    )
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {
            "type": "muster_lord", "side": "russian",
            "args": {"by_lord": by_id, "target_lord": "aleksandr", "seat": "novgorod"},
        })
    assert exc.value.code == "aleksandr_veche_only"


def test_muster_lord_success_deploys_forces_and_service_marker() -> None:
    """3.4.1: success places cylinder, forces/assets, Service = SERVICE_RATING boxes right."""
    s = load_scenario("watland", seed=42)
    _to_muster_step(s, side="teutonic")
    by_id = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    target = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "ready")
    levy_box = _find_levy_box(s)
    _put_cylinder_at(s, target, levy_box)  # ensure ready
    # Force a successful roll: lower the levy box / target's fealty boundary by retrying
    # Instead: construct a deterministic scenario by setting seed; we accept whatever roll occurs.
    from nevsky.static_data import load_lords
    fealty = int(load_lords()[target]["ratings"]["fealty"])
    # try multiple seeds until success or fail recorded
    seed = 42
    while True:
        s = load_scenario("watland", seed=seed)
        _to_muster_step(s, side="teutonic")
        by_id = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
        target = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "ready")
        _put_cylinder_at(s, target, levy_box)
        # Find a free seat:
        from nevsky.actions import _free_seats_for
        seats = _free_seats_for(s, target)
        if not seats:
            seed += 1
            continue
        seat = seats[0]
        from nevsky.rng import _make_rng
        rng = _make_rng(seed, s.meta.rng_state)
        roll = rng.randint(1, 6)
        if roll <= fealty:
            break
        seed += 1
        if seed > 200:
            pytest.skip("could not find a successful Muster seed for this fealty/scenario")
    res = apply_action(s, {
        "type": "muster_lord", "side": "teutonic",
        "args": {"by_lord": by_id, "target_lord": target, "seat": seat},
    })
    assert res["outcome"] == "mustered"
    assert s.lords[target].state == "mustered"
    assert s.lords[target].location == seat
    # Service marker placed SERVICE_RATING boxes right of Levy.
    srating = int(load_lords()[target]["ratings"]["service"])
    expected = levy_box + srating
    if expected <= 16:
        assert target in s.calendar.boxes[expected - 1].service_markers
    else:
        assert target in s.calendar.off_right


def test_muster_costs_lordship() -> None:
    """3.4: each Muster option spends 1 Lordship; budget = LORDSHIP_RATING."""
    s = load_scenario("watland", seed=42)
    _to_muster_step(s, side="teutonic")
    by_id = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    from nevsky.static_data import load_lords
    sl = load_lords()[by_id]
    if sl.get("ships_authorized"):
        ttype = "boat"
    else:
        ttype = "boat"
    # Spend until budget exhausts.
    budget = int(sl["ratings"]["lordship"])
    for _ in range(budget):
        apply_action(s, {
            "type": "levy_transport", "side": "teutonic",
            "args": {"by_lord": by_id, "transport_type": ttype},
        })
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {
            "type": "levy_transport", "side": "teutonic",
            "args": {"by_lord": by_id, "transport_type": ttype},
        })
    assert exc.value.code == "lordship_exhausted"


def test_levy_transport_ship_requires_authorization() -> None:
    """3.4.3: Ship requires lord.ships_authorized=True."""
    s = load_scenario("watland", seed=42)
    _to_muster_step(s, side="teutonic")
    from nevsky.static_data import load_lords
    static = load_lords()
    not_auth = next(
        lid for lid, l in s.lords.items()
        if l.side == "teutonic" and l.state == "mustered"
        and not static[lid].get("ships_authorized", False)
    )
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {
            "type": "levy_transport", "side": "teutonic",
            "args": {"by_lord": not_auth, "transport_type": "ship"},
        })
    assert exc.value.code == "ship_unauthorized"


def test_levy_transport_max_eight_per_type() -> None:
    s = load_scenario("watland", seed=42)
    _to_muster_step(s, side="teutonic")
    by_id = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    s.lords[by_id].assets["cart"] = 8
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {
            "type": "levy_transport", "side": "teutonic",
            "args": {"by_lord": by_id, "transport_type": "cart"},
        })
    assert exc.value.code == "transport_max"


def test_levy_capability_this_lord_max_two() -> None:
    """3.4.4: max 2 this-lord capabilities per Lord."""
    s = load_scenario("watland", seed=42)
    _to_muster_step(s, side="teutonic")
    by_id = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    # T2, T3, T9 are this-lord capabilities; pre-fill with two.
    s.lords[by_id].this_lord_capabilities = ["T2", "T3"]
    if "T2" in s.decks.teutonic.deck:
        s.decks.teutonic.deck.remove("T2")
    if "T3" in s.decks.teutonic.deck:
        s.decks.teutonic.deck.remove("T3")
    # Now try to Levy a third (T9 -- this_lord per cards.json).
    if "T9" not in s.decks.teutonic.deck:
        s.decks.teutonic.deck.append("T9")
    with pytest.raises(IllegalAction) as exc:
        apply_action(s, {
            "type": "levy_capability", "side": "teutonic",
            "args": {"by_lord": by_id, "card_id": "T9", "lord_id": by_id},
        })
    assert exc.value.code == "cap_limit"


def test_levy_capability_side_wide_goes_to_capabilities_in_play() -> None:
    """3.4.4: side-wide capability tucks at side board edge."""
    s = load_scenario("watland", seed=42)
    _to_muster_step(s, side="teutonic")
    by_id = next(lid for lid, l in s.lords.items() if l.side == "teutonic" and l.state == "mustered")
    if "T11" not in s.decks.teutonic.deck:
        s.decks.teutonic.deck.append("T11")
    apply_action(s, {
        "type": "levy_capability", "side": "teutonic",
        "args": {"by_lord": by_id, "card_id": "T11"},
    })
    assert "T11" in s.decks.teutonic.capabilities_in_play


def test_muster_vassal_basic_adds_forces() -> None:
    """3.4.2: Muster Vassal slides Vassal Service marker into Forces; adds units."""
    s = load_scenario("watland", seed=42)
    _to_muster_step(s, side="teutonic")
    # Find a Lord with a non-special vassal.
    from nevsky.static_data import load_lords
    static = load_lords()
    by_id = None
    vid = None
    for lid, l in s.lords.items():
        if l.side != "teutonic" or l.state != "mustered":
            continue
        for v in static[lid].get("vassals", []):
            if v.get("special") is None:
                by_id = lid
                vid = v["vassal_id"]
                break
        if by_id:
            break
    if by_id is None:
        pytest.skip("no eligible Vassal to Muster in watland Teutonic mustered set")
    pre_forces = sum(s.lords[by_id].forces.values())
    apply_action(s, {
        "type": "muster_vassal", "side": "teutonic",
        "args": {"by_lord": by_id, "vassal_id": vid},
    })
    assert s.lords[by_id].vassals[vid].mustered is True
    assert sum(s.lords[by_id].forces.values()) > pre_forces
