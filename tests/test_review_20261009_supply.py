"""Supply regressions from the October 2026 review (rules 4.6.1-3)."""
import pytest

from nevsky.actions import IllegalAction, apply_action
from nevsky.scenarios import load_scenario


def _command(lord_id="hermann", location="odenpah", assets=None):
    state = load_scenario("watland", seed=1)
    # Isolate transport and route blockers from unrelated scenario pieces.
    for lord in state.lords.values():
        lord.state = "on_calendar"
        lord.location = None
        lord.in_stronghold = False
        lord.assets = {}
    lord = state.lords[lord_id]
    lord.state = "mustered"
    lord.location = location
    lord.assets = dict(assets or {})
    state.meta.box = 1
    state.meta.phase = "campaign"
    state.meta.campaign_step = "command"
    state.meta.active_player = lord.side
    state.campaign_turn.active_lord = lord_id
    state.campaign_turn.active_card = lord_id
    state.campaign_turn.actions_remaining = 3
    return state


def _source(locale, route, transport="auto", **kwargs):
    return dict(locale_id=locale, route=route, transport=transport, **kwargs)


def _supply(state, *sources):
    return apply_action(state, {
        "type": "cmd_supply", "side": state.meta.active_player,
        "args": {"sources": list(sources)},
    })


@pytest.mark.parametrize("blocker", ["lord", "conquered"])
def test_supply_source_is_subject_to_blockade(blocker):
    """4.6.2: Sources, as well as intermediate Locales, cannot be blocked."""
    state = _command(assets={"cart": 1})
    if blocker == "lord":
        state.lords["domash"].state = "mustered"
        state.lords["domash"].location = "dorpat"
    else:
        state.locales["dorpat"].russian_conquered = 1
    with pytest.raises(IllegalAction, match="route_blocked"):
        _supply(state, _source("dorpat", ["dorpat", "odenpah"], "cart"))
    assert state.lords["hermann"].assets == {"cart": 1}
    assert state.campaign_turn.actions_remaining == 3


def test_native_enemy_stronghold_blocks_intermediate_locale():
    """4.6.2: empty native enemy Strongholds block without a Conquered marker."""
    state = _command(location="dubrovno", assets={"boat": 2, "cart": 1})
    state.locales["pskov"].teutonic_conquered = 0
    source = _source("dorpat", ["dorpat", "uzmen", "pskov", "dubrovno"])
    with pytest.raises(IllegalAction, match="route_blocked"):
        _supply(state, source)
    # Besieging the native enemy Stronghold opens the same Route.
    state.locales["pskov"].siege_markers = 1
    state.lords["andreas"].state = "mustered"
    state.lords["andreas"].location = "pskov"
    assert _supply(state, source)["added"] == 1


def test_besieged_enemy_source_is_usable_but_outside_enemy_still_blocks():
    """4.6.2: the exception covers Besieged enemies, not their relief force."""
    state = _command(assets={"cart": 1})
    state.locales["dorpat"].russian_conquered = 1
    state.locales["dorpat"].siege_markers = 1
    for lord_id in ("domash", "andreas"):
        state.lords[lord_id].state = "mustered"
        state.lords[lord_id].location = "dorpat"
    state.lords["domash"].in_stronghold = True
    assert _supply(state, _source("dorpat", ["dorpat", "odenpah"], "cart"))["added"] == 1
    state.lords["domash"].in_stronghold = False
    with pytest.raises(IllegalAction, match="route_blocked"):
        _supply(state, _source("dorpat", ["dorpat", "odenpah"], "cart"))


def test_ship_source_needs_transport_for_inland_route():
    """4.6.2-3: a Ship produces Supply at Reval; a Cart carries it to Revala."""
    state = _command(location="revala", assets={"ship": 1})
    source = _source("reval", ["reval", "revala"], "ship")
    with pytest.raises(IllegalAction, match="insufficient_transport"):
        _supply(state, source)
    state.lords["hermann"].assets["cart"] = 1
    result = _supply(state, source)
    assert result["added"] == 1
    assert result["transport_used"] == {"cart": 1, "ship": 1}


def test_two_ship_provender_cannot_reuse_one_cart():
    """4.6.2 Second Edition: each Provender uses its own Transport per Way."""
    state = _command(location="revala", assets={"ship": 2, "cart": 1})
    source = _source("reval", ["reval", "revala"], "ship")
    with pytest.raises(IllegalAction, match="insufficient_transport"):
        _supply(state, source, source)
    state.lords["hermann"].assets["cart"] = 2
    result = _supply(state, source, source)
    assert result["added"] == 2
    assert result["transport_used"] == {"cart": 2, "ship": 2}


def test_mixed_way_seat_route_accepts_per_way_transport():
    """4.6.2: one Route can use Boats on one Way and Carts on the next."""
    state = _command(location="kirrumpah", assets={"boat": 1, "cart": 1})
    result = _supply(state, _source(
        "dorpat", ["dorpat", "odenpah", "kirrumpah"],
        route_transports=["boat", "cart"],
    ))
    assert result["added"] == 1
    assert result["transport_used"] == {"boat": 1, "cart": 1}


def test_ship_route_accepts_mixed_automatic_transport_allocation():
    """4.6.2: ship Sources can also use mixed Boat/Cart Routes inland."""
    state = _command(location="ugaunia", assets={"ship": 1, "boat": 1, "cart": 1})
    result = _supply(state, _source("narwia", ["narwia", "dorpat", "ugaunia"], "ship"))
    assert result["added"] == 1
    assert result["transport_used"] == {"boat": 1, "cart": 1, "ship": 1}


def test_parallel_way_allocation_reserves_carts_for_trackways():
    """4.6.2: parallel Ways permit an allocation satisfying all Route segments."""
    state = _command(location="kirrumpah", assets={"ship": 1, "boat": 2, "cart": 1})
    result = _supply(state, _source(
        "narwia", ["narwia", "dorpat", "odenpah", "kirrumpah"], "ship",
    ))
    assert result["transport_used"] == {"boat": 2, "cart": 1, "ship": 1}


def test_cogs_doubles_ships_for_supply():
    """T18: one Cogs Ship provides two Provender at a Seaport."""
    state = _command("andreas", "reval", {"ship": 1})
    state.lords["andreas"].this_lord_capabilities = ["T18"]
    source = _source("reval", ["reval"], "ship")
    assert _supply(state, source, source)["added"] == 2
    assert state.lords["andreas"].assets["ship"] == 1  # use, not transfer/spend


def test_cogs_ships_share_anywhere_and_still_require_route_transport():
    """T18 Tips: remote Cogs Ships are shared, but the Supply Route is required."""
    state = _command(location="revala", assets={"cart": 2})
    donor = state.lords["andreas"]
    donor.state = "mustered"
    donor.location = "riga"
    donor.assets = {"ship": 1}
    source = _source("reval", ["reval", "revala"], "ship")
    with pytest.raises(IllegalAction, match="insufficient_transport"):
        _supply(state, source, source)  # ordinary remote Ships cannot be shared
    donor.this_lord_capabilities = ["T18"]
    assert _supply(state, source, source)["added"] == 2
    assert state.lords["andreas"].assets == {"ship": 1}


@pytest.mark.parametrize("lord_id,location,cap", [
    ("domash", "novgorod", "R15"),
    ("andreas", "wenden", "T12"),
])
def test_capability_adds_second_seat_at_printed_seat(lord_id, location, cap):
    """R15/T12 Tips explicitly identify two Seats at Novgorod/Wenden."""
    state = _command(lord_id, location)
    source = _source(location, [location])
    with pytest.raises(IllegalAction, match="duplicate_source"):
        _supply(state, source, source)
    deck = state.decks.russian if state.lords[lord_id].side == "russian" else state.decks.teutonic
    deck.capabilities_in_play = [cap]
    assert _supply(state, source, source)["added"] == 2
    with pytest.raises(IllegalAction, match="duplicate_source|too_many_seat_sources"):
        _supply(state, source, source, source)


def test_two_seats_at_one_source_require_separate_route_transport():
    """4.6.2/R15: double Seats do not let a Transport serve two Provender."""
    state = _command("domash", "tesovo", {"cart": 1})
    state.decks.russian.capabilities_in_play = ["R15"]
    source = _source("novgorod", ["novgorod", "tesovo"], "cart")
    with pytest.raises(IllegalAction, match="insufficient_transport"):
        _supply(state, source, source)
    state.lords["domash"].assets["cart"] = 2
    assert _supply(state, source, source)["added"] == 2


def test_two_local_seats_and_two_ship_sources_stack():
    """4.6.3: up to two Seat Provender plus up to two Ship Provender."""
    state = _command("domash", "novgorod", {"ship": 2})
    state.decks.russian.capabilities_in_play = ["R15"]
    seat = _source("novgorod", ["novgorod"])
    ship = _source("novgorod", ["novgorod"], "ship")
    result = _supply(state, seat, seat, ship, ship)
    assert result["added"] == 4
    assert result["transport_used"] == {"ship": 2}


@pytest.mark.parametrize("transports", [["ship"], [], ["boat"]])
def test_explicit_route_transports_must_fit_the_ways(transports):
    """1.7.4/4.6.2: Ships/Boats cannot replace Carts on a trackway."""
    state = _command(location="revala", assets={"ship": 1, "boat": 1, "cart": 1})
    with pytest.raises(IllegalAction, match="bad_route_transport|transport_way"):
        _supply(state, _source("reval", ["reval", "revala"], "ship", route_transports=transports))


def test_lodya_doubles_boats_or_converts_without_reusing_markers():
    """R16 Tips: doubled Boats and up-to-two conversions are exclusive modes."""
    state = _command("domash", "ladoga", {"boat": 1})
    state.lords["domash"].this_lord_capabilities = ["R16"]
    source = _source("novgorod", ["novgorod", "volkhov", "ladoga"], "boat")
    assert _supply(state, source)["transport_used"] == {"boat": 2}

    state = _command("domash", "volkhov", {"boat": 1})
    state.lords["domash"].this_lord_capabilities = ["R16"]
    action = {"type": "cmd_supply", "side": "russian", "args": {
        "sources": [_source("novgorod", ["novgorod", "volkhov"], "ship")],
        "lodya_conversions": {"domash": {"boats_as_ships": 1}},
    }}
    with pytest.raises(IllegalAction, match="insufficient_transport"):
        apply_action(state, action)  # converted Boat cannot also carry the Provender
    state.lords["domash"].assets["boat"] = 2
    result = apply_action(state, action)
    assert result["added"] == 1
    assert result["transport_used"] == {"boat": 1, "ship": 1}
    assert state.lords["domash"].assets["boat"] == 2
    assert state.lords["domash"].assets.get("ship", 0) == 0


def test_lodya_ship_as_boat_and_conversion_limit():
    """R16: an available Ship can substitute for a Boat, with a two-marker cap."""
    state = _command("domash", "volkhov", {"ship": 3})
    state.lords["domash"].this_lord_capabilities = ["R16"]
    action = {"type": "cmd_supply", "side": "russian", "args": {
        "sources": [_source("novgorod", ["novgorod", "volkhov"], "boat")],
        "lodya_conversions": {"domash": {"ships_as_boats": 3}},
    }}
    with pytest.raises(IllegalAction, match="bad_lodya_conversion"):
        apply_action(state, action)
    action["args"]["lodya_conversions"]["domash"]["ships_as_boats"] = 1
    assert apply_action(state, action)["transport_used"] == {"boat": 1}


@pytest.mark.parametrize("lord_id,location,cap,assets,expected", [
    ("domash", "novgorod", "R15", {}, 2),
    ("andreas", "wenden", "T12", {}, 2),
    ("andreas", "reval", "T18", {"ship": 1}, 2),
    ("domash", "novgorod", "R15", {"ship": 2}, 4),
    ("domash", "novgorod", "R16", {"boat": 2}, 3),
])
def test_legal_moves_exposes_usable_boosted_local_supply(lord_id, location, cap, assets, expected):
    """4.6/R15/T12/T18/R16: consumers can select the corrected local Supply."""
    from copy import deepcopy

    from nevsky.legal_moves import legal_moves

    state = _command(lord_id, location, assets)
    if cap in ("R15", "T12"):
        deck = (state.decks.russian if state.lords[lord_id].side == "russian"
                else state.decks.teutonic)
        deck.capabilities_in_play = [cap]
    else:
        state.lords[lord_id].this_lord_capabilities = [cap]
    moves = [move for move in legal_moves(state, with_previews=False)
             if move["type"] == "cmd_supply" and "args" in move]
    assert moves
    results = [apply_action(deepcopy(state), move) for move in moves]
    assert max(result["added"] for result in results) == expected
