"""R214: Ordensburgen (T12) Command +1 applies ONLY at a Commandery
(Wenden, Fellin, Adsel, Leal — the four Order-symbol Strongholds flagged
`commandery: true`, per Q-004 / AoW T12 tips / Map ref 226-236).

Regression: the prior `_effective_command_rating` granted +1 whenever a
Teutonic Lord started at one of his own primary_seats, over-granting at
non-Commandery home Seats (Dorpat, Odenpah, Reval, Riga). Surfaced in the
Crusade seed-1 LLM self-play: yaroslav started his Command card at Odenpah
(his primary Seat, NOT a Commandery) and received a 3-action card on a
Command-2 Lord.
"""
import nevsky.actions  # noqa: F401  (import order: actions before campaign)
from nevsky.scenarios import load_scenario
from nevsky.campaign import _effective_command_rating
from nevsky.static_data import load_lords, load_locales


def _force_t12(s) -> None:
    if "T12" not in s.decks.teutonic.capabilities_in_play:
        s.decks.teutonic.capabilities_in_play.append("T12")


def test_ordensburgen_no_bonus_at_non_commandery_primary_seat() -> None:
    s = load_scenario("crusade_on_novgorod", seed=1)
    _force_t12(s)
    lords = load_lords()
    # hermann's primary_seats are dorpat + odenpah, NEITHER a Commandery.
    lid = "hermann"
    base = int(lords[lid]["ratings"]["command"])
    for non_comm_seat in ("dorpat", "odenpah"):
        s.lords[lid].location = non_comm_seat
        assert _effective_command_rating(s, lid) == base, (
            f"Ordensburgen wrongly granted +1 at non-Commandery seat "
            f"{non_comm_seat}: base={base}, got={_effective_command_rating(s, lid)}"
        )


def test_ordensburgen_yaroslav_odenpah_is_command_2_not_3() -> None:
    # The exact playthrough case: yaroslav (Command 2) at Odenpah w/ T12.
    s = load_scenario("crusade_on_novgorod", seed=1)
    _force_t12(s)
    base = int(load_lords()["yaroslav"]["ratings"]["command"])
    assert base == 2
    s.lords["yaroslav"].location = "odenpah"
    assert _effective_command_rating(s, "yaroslav") == 2


def test_ordensburgen_plus1_at_every_commandery() -> None:
    s = load_scenario("crusade_on_novgorod", seed=1)
    _force_t12(s)
    base = int(load_lords()["hermann"]["ratings"]["command"])
    locs = load_locales()
    commanderies = {lid for lid, loc in locs.items() if loc.get("commandery")}
    assert commanderies == {"wenden", "fellin", "adsel", "leal"}
    for c in sorted(commanderies):
        s.lords["hermann"].location = c
        assert _effective_command_rating(s, "hermann") == base + 1, (
            f"Ordensburgen +1 missing at Commandery {c}"
        )


def test_ordensburgen_bonus_requires_capability_in_play() -> None:
    # Without T12, no +1 even at a Commandery.
    s = load_scenario("crusade_on_novgorod", seed=1)
    base = int(load_lords()["hermann"]["ratings"]["command"])
    s.lords["hermann"].location = "wenden"
    assert _effective_command_rating(s, "hermann") == base
