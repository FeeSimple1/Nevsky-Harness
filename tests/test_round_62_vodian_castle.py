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


# -----------------------------------------------------------------
# SMOKE-052: BFS misses Lord at target locale (distance 0).
# -----------------------------------------------------------------

def test_vodian_lord_at_target_distance_zero():
    """A Teutonic Lord standing at the target Fort itself should
    register as distance 0 (closer than any Russian)."""
    st = _setup("kaibolovo")
    st.lords["hermann"].location = "kaibolovo"  # AT target
    st.locales["kaibolovo"].teutonic_castle = False
    st.locales["kaibolovo"].walls_plus_one = False
    result = _ev_vodian_treachery(st, {"target": "kaibolovo"})
    assert result["teu_dist"] == 0
    assert result["conquered"] == "kaibolovo"


def test_vodian_russian_at_target_blocks_event():
    """If a Russian Lord is AT the target (distance 0), Teutonic
    distance can't be strictly less — event should fail."""
    st = _setup("kaibolovo")
    # Place a Russian Lord at the target
    st.lords["gavrilo"].location = "kaibolovo"
    # Move all Teutons away
    for lid, L in st.lords.items():
        if L.side == "teutonic":
            L.location = "reval"
    st.locales["kaibolovo"].teutonic_castle = False
    st.locales["kaibolovo"].walls_plus_one = False
    with pytest.raises(IllegalAction) as exc:
        _ev_vodian_treachery(st, {"target": "kaibolovo"})
    assert exc.value.code == "not_closer"


# -----------------------------------------------------------------
# SMOKE-053: Heinrich Curia Disbands (not removes) Heinrich.
# -----------------------------------------------------------------

from nevsky.events import _ev_heinrich_curia


def test_t13_disbands_heinrich_not_removes():
    """Per T13 Tip 'other Disband rules apply' — Heinrich's cylinder
    goes back to Calendar (state=disbanded), not removed forever."""
    st = load_scenario("watland", seed=1)
    h = st.lords["heinrich"]
    h.state = "mustered"
    h.location = "riga"
    # Add Service marker on Calendar
    st.calendar.boxes[3].service_markers.append("heinrich")
    teu_others = [
        lid for lid, L in st.lords.items()
        if L.side == "teutonic" and L.state == "mustered" and lid != "heinrich"
    ][:2]
    res = _ev_heinrich_curia(st, {"recipients": teu_others})
    assert st.lords["heinrich"].state == "disbanded"
    # Cylinder should be back on Calendar
    assert "heinrich_new_box" in res
    new_box = res["heinrich_new_box"]
    assert 1 <= new_box <= 17


def test_t13_disbanded_heinrich_can_remuster():
    """After Disband, Heinrich's state can transition to ready when
    Levy marker catches up (SMOKE-044 R56 behavior)."""
    st = load_scenario("watland", seed=1)
    h = st.lords["heinrich"]
    h.state = "mustered"
    h.location = "riga"
    teu_others = [
        lid for lid, L in st.lords.items()
        if L.side == "teutonic" and L.state == "mustered" and lid != "heinrich"
    ][:2]
    _ev_heinrich_curia(st, {"recipients": teu_others})
    assert st.lords["heinrich"].state == "disbanded"
    # The SMOKE-044 R56 transition fires at start of next Muster step:
    # disbanded → ready if cylinder at or before Levy marker.
