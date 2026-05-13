"""Round 62 — SMOKE-051 regression tests.

T3 Vodian Treachery Tip (Arts of War Reference): "If Stonemasons
converted both Forts to Castles, this Event cannot be played,
because neither Locale has a Fort." The Locale's static type stays
"fort" after a Castle marker is placed by Stonemasons, so the check
must consult the dynamic teutonic_castle / russian_castle bools.
"""

import pytest

import nevsky.actions  # noqa
from nevsky.scenarios import load_scenario
from nevsky.actions import IllegalAction
from nevsky.events import _ev_vodian_treachery
from nevsky.static_data import load_ways


def _adj(loc):
    for w in load_ways():
        if w["a"] == loc:
            return w["b"]
        if w["b"] == loc:
            return w["a"]
    return None


def _setup(target):
    st = load_scenario("pleskau", seed=1)
    h = st.lords["hermann"]
    nbr = _adj(target)
    h.location = nbr
    for lid, L in st.lords.items():
        if L.side == "russian":
            L.location = "novgorod"
        elif L.side == "teutonic" and lid != "hermann":
            L.location = "reval"
    return st


def test_vodian_blocked_by_teutonic_castle():
    st = _setup("kaibolovo")
    st.locales["kaibolovo"].teutonic_castle = True
    with pytest.raises(IllegalAction) as exc:
        _ev_vodian_treachery(st, {"target": "kaibolovo"})
    assert exc.value.code == "castle_marker"


def test_vodian_blocked_by_russian_castle():
    st = _setup("kaibolovo")
    st.locales["kaibolovo"].russian_castle = True
    with pytest.raises(IllegalAction) as exc:
        _ev_vodian_treachery(st, {"target": "kaibolovo"})
    assert exc.value.code == "castle_marker"


def test_vodian_allowed_when_no_castle_marker():
    """Sanity baseline: without a Castle marker the event proceeds."""
    st = _setup("kaibolovo")
    st.locales["kaibolovo"].teutonic_castle = False
    st.locales["kaibolovo"].russian_castle = False
    result = _ev_vodian_treachery(st, {"target": "kaibolovo"})
    assert result["event"] == "T3"
    assert result["conquered"] == "kaibolovo"


def test_vodian_blocked_castle_takes_precedence_over_walls_plus_one():
    """Both Castle and Walls+1 markers: Castle check fires first."""
    st = _setup("kaibolovo")
    st.locales["kaibolovo"].teutonic_castle = True
    st.locales["kaibolovo"].walls_plus_one = True
    with pytest.raises(IllegalAction) as exc:
        _ev_vodian_treachery(st, {"target": "kaibolovo"})
    assert exc.value.code == "castle_marker"
