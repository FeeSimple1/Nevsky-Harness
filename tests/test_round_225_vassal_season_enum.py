"""Round 225 — SMOKE-162: muster_vassal enumeration mirrors special gates.

GPT-5.5 self-play (turn 297/298) was offered a `muster_vassal` for
andreas' Summer Crusaders outside Summer; _h_muster_vassal then rejected
it with `vassal_season` (T11 Tip / SMOKE-059). The handler was correct;
the ENUMERATOR over-enumerated. R225 mirrors both special-Vassal gates in
legal_moves so the bad Muster is never offered.
"""
import nevsky.actions  # noqa: F401
from nevsky.scenarios import load_scenario
from nevsky.static_data import load_lords
from nevsky.legal_moves import legal_moves


def _setup(season_box, with_t11=True):
    st = load_scenario("watland", seed=1)
    st.meta.box = season_box
    if with_t11:
        st.decks.teutonic.capabilities_in_play.append("T11")
    sl = load_lords()["andreas"]
    vid = next(v["vassal_id"] for v in sl.get("vassals", [])
               if v.get("special") == "summer_crusaders")
    a = st.lords["andreas"]
    a.vassals[vid].ready = True
    a.vassals[vid].mustered = False
    st.meta.phase = "levy"
    st.meta.levy_step = "muster"
    st.meta.active_player = "teutonic"
    for L in st.lords.values():
        L.just_arrived_this_levy = False
    return st, vid


def _vassal_musters(st, vid):
    return [m for m in legal_moves(st, with_previews=False)
            if m["type"] == "muster_vassal" and m["args"].get("vassal_id") == vid]


def test_summer_crusaders_not_enumerated_in_winter():
    st, vid = _setup(season_box=4)  # early_winter
    assert _vassal_musters(st, vid) == [], \
        "Summer Crusaders must not be offered outside Summer"


def test_summer_crusaders_not_enumerated_in_rasputitsa():
    st, vid = _setup(season_box=7)
    assert _vassal_musters(st, vid) == []


def test_summer_crusaders_enumerated_in_summer():
    st, vid = _setup(season_box=1)  # summer
    assert _vassal_musters(st, vid), \
        "Summer Crusaders SHOULD be offered in Summer with T11 in play"


def test_summer_crusaders_not_enumerated_without_t11():
    st, vid = _setup(season_box=1, with_t11=False)  # summer but no T11
    assert _vassal_musters(st, vid) == [], \
        "Summer Crusaders require T11 Crusade in play"


def test_steppe_warriors_require_r10_in_enumeration():
    st = load_scenario("crusade_on_novgorod", seed=1)
    st.meta.phase = "levy"
    st.meta.levy_step = "muster"
    st.meta.active_player = "russian"
    sl_all = load_lords()
    # find a russian lord with a steppe_warriors vassal present in-state
    target = None
    for lid, lord in st.lords.items():
        if lord.side != "russian" or lid == "aleksandr":
            continue  # aleksandr has special Ready/Veche muster mechanics
        for v in sl_all[lid].get("vassals", []):
            if v.get("special") == "steppe_warriors" and v["vassal_id"] in lord.vassals:
                target = (lid, v["vassal_id"])
                break
        if target:
            break
    assert target, "fixture: expected a russian steppe_warriors vassal"
    lid, vid = target
    lord = st.lords[lid]
    lord.vassals[vid].ready = True
    lord.vassals[vid].mustered = False
    # make the parent Lord muster-eligible: on map at a Friendly Locale
    # with Lordship budget free (own_mustered also requires location/Friendly).
    lord.state = "mustered"
    lord.lordship_used = 0
    donor = next(o for l, o in st.lords.items()
                 if o.side == "russian" and l != lid and o.location is not None)
    lord.location = donor.location
    for L in st.lords.values():
        L.just_arrived_this_levy = False
    # Without R10: not offered
    if "R10" in st.decks.russian.capabilities_in_play:
        st.decks.russian.capabilities_in_play.remove("R10")
    offered = [m for m in legal_moves(st, with_previews=False)
               if m["type"] == "muster_vassal" and m["args"].get("vassal_id") == vid]
    assert offered == [], "Steppe Warriors must not be offered without R10"
    # With R10: offered (if the lord can muster this levy)
    st.decks.russian.capabilities_in_play.append("R10")
    offered2 = [m for m in legal_moves(st, with_previews=False)
                if m["type"] == "muster_vassal" and m["args"].get("vassal_id") == vid]
    assert offered2, "Steppe Warriors SHOULD be offered with R10 in play"
