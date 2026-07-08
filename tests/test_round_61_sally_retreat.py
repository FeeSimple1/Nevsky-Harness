"""4.4.3 Retreat gates (originally SMOKE-049; corrected by PLAY-29).

4.4.3: losing Lords "Retreat to a single adjacent Locale that has no
UNBESIEGED enemy Lords or Strongholds." The earlier Sally-retreat filter
(a) omitted the "Unbesieged" qualifier and (b) additionally blocked
enemy-Conquered Locales -- a clause 4.4.3 does not contain. Both the
Battle and Sally retreat paths now use the shared _legal_retreat_dests.
"""

import inspect

import nevsky.actions  # noqa
from nevsky.campaign import _legal_retreat_dests
from nevsky.scenarios import load_scenario
from nevsky import campaign


def test_unbesieged_enemy_stronghold_blocks_but_besieged_does_not():
    s = load_scenario("pleskau", seed=1)
    # Teutonic Lord Retreating from pskov; izborsk (Russian Fort) is an
    # adjacent enemy Stronghold.
    dests = {d for d, _ in _legal_retreat_dests(s, "pskov", "teutonic")}
    assert "izborsk" not in dests, "Unbesieged enemy Stronghold must block"
    # Now the Teutons Besiege izborsk -> it no longer blocks Retreat there.
    s.locales["izborsk"].siege_markers = 1
    dests2 = {d for d, _ in _legal_retreat_dests(s, "pskov", "teutonic")}
    assert "izborsk" in dests2, "a Besieged enemy Stronghold must NOT block"


def test_unbesieged_enemy_lord_blocks_but_besieged_does_not():
    s = load_scenario("pleskau", seed=1)
    rus = next(lid for lid, l in s.lords.items() if l.side == "russian")
    # Put an Unbesieged Russian Lord at dubrovno (a pskov neighbor).
    s.lords[rus].state = "mustered"
    s.lords[rus].location = "dubrovno"
    s.lords[rus].in_stronghold = False
    dests = {d for d, _ in _legal_retreat_dests(s, "pskov", "teutonic")}
    assert "dubrovno" not in dests
    # If that Lord is Besieged (inside a Stronghold under siege), he does
    # not block. dubrovno has no Stronghold, so simulate via izborsk.
    s.lords[rus].location = "izborsk"
    s.lords[rus].in_stronghold = True
    s.locales["izborsk"].siege_markers = 1  # -> Besieged
    dests2 = {d for d, _ in _legal_retreat_dests(s, "pskov", "teutonic")}
    assert "izborsk" in dests2


def test_excludes_the_approach_way():
    s = load_scenario("pleskau", seed=1)
    all_dests = {d for d, _ in _legal_retreat_dests(s, "pskov", "russian")}
    # Exclude the trackway back to izborsk (the Approach Way).
    excl = {d for d, _ in _legal_retreat_dests(
        s, "pskov", "russian", exclude=("izborsk", "trackway"))}
    assert "izborsk" in all_dests
    assert "izborsk" not in excl


def test_sally_retreat_uses_shared_helper_not_conquered_block():
    """The mislabeled enemy-Conquered block is gone; 4.4.3-correct
    _legal_retreat_dests is used instead."""
    src = inspect.getsource(campaign._h_cmd_sally)
    assert "_legal_retreat_dests" in src
    assert "cand_loc.russian_conquered > 0" not in src
    assert "cand_loc.teutonic_conquered > 0" not in src
