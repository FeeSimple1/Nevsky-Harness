"""Round 47 — SMOKE-035 regression tests.

just_arrived_this_levy is a 3.4 Muster flag set when a Lord is newly
Mustered THIS Levy. It blocks that Lord from acting as a Lordship
source in the same Muster step (a just-arrived Lord can't immediately
turn around and spend Lordship). The flag must reset between Levies;
otherwise a Lord who Mustered in Levy N still counts as "just arrived"
in Levy N+1, blocking legitimate Lordship use in subsequent Levies.
"""

from nevsky.scenarios import load_scenario


def test_just_arrived_resets_at_campaign_to_levy_transition():
    """End-Campaign transition (4.9) must clear just_arrived_this_levy
    for all Lords so the next Levy's Muster step sees fresh flags."""
    st = load_scenario("pleskau", seed=1)
    # Simulate post-Muster state: hermann is just-arrived
    st.lords["hermann"].just_arrived_this_levy = True
    st.lords["yaroslav"].just_arrived_this_levy = True

    # Drive end_campaign_resolve for both sides to trigger the transition.
    from nevsky.actions import apply_action
    # Force into the right phase/step.
    st.meta.phase = "campaign"
    st.meta.campaign_step = "end_campaign"
    st.meta.active_player = "teutonic"
    # Both sides must call end_campaign_resolve.
    apply_action(st, {"type": "end_campaign_resolve", "side": "teutonic", "args": {}})
    apply_action(st, {"type": "end_campaign_resolve", "side": "russian", "args": {}})

    # After the transition, phase should be "levy" and flags should be clear.
    assert st.meta.phase == "levy"
    assert st.lords["hermann"].just_arrived_this_levy is False
    assert st.lords["yaroslav"].just_arrived_this_levy is False


def test_just_arrived_cleared_for_disbanded_lords_too():
    """Even Lords no longer Mustered should have their flag cleared.

    The flag is per-Levy and not state-conditional; clearing for all
    Lords is the simpler invariant and avoids edge cases where a Lord
    is Disbanded and later re-Mustered with stale True.
    """
    st = load_scenario("pleskau", seed=1)
    st.lords["hermann"].just_arrived_this_levy = True
    st.lords["hermann"].state = "disbanded"

    from nevsky.actions import apply_action
    st.meta.phase = "campaign"
    st.meta.campaign_step = "end_campaign"
    st.meta.active_player = "teutonic"
    apply_action(st, {"type": "end_campaign_resolve", "side": "teutonic", "args": {}})
    apply_action(st, {"type": "end_campaign_resolve", "side": "russian", "args": {}})

    assert st.lords["hermann"].just_arrived_this_levy is False


def test_just_arrived_not_touched_on_only_one_side_done():
    """If only one side has called end_campaign_resolve, the transition
    has not occurred; flags should remain unchanged."""
    st = load_scenario("pleskau", seed=1)
    st.lords["hermann"].just_arrived_this_levy = True

    from nevsky.actions import apply_action
    st.meta.phase = "campaign"
    st.meta.campaign_step = "end_campaign"
    st.meta.active_player = "teutonic"
    apply_action(st, {"type": "end_campaign_resolve", "side": "teutonic", "args": {}})

    # Russian hasn't called yet — transition not complete
    assert st.meta.phase == "campaign"
    # Flag preserved
    assert st.lords["hermann"].just_arrived_this_levy is True


# -----------------------------------------------------------------
# SMOKE-036: in_stronghold flag must clear on movement.
# -----------------------------------------------------------------

from nevsky.actions import apply_action
from nevsky.static_data import load_ways


def _adj(src):
    for w in load_ways():
        if w["a"] == src:
            return w["b"]
        if w["b"] == src:
            return w["a"]
    return None


def test_in_stronghold_cleared_on_march():
    """Marching from a Locale where in_stronghold=True clears the flag."""
    st = load_scenario("pleskau", seed=1)
    h = st.lords["hermann"]
    h.in_stronghold = True
    st.locales[h.location].siege_markers = 0  # no actual siege so March allowed
    dest = _adj(h.location)
    st.meta.phase = "campaign"
    st.meta.campaign_step = "command"
    st.campaign_turn.active_lord = "hermann"
    st.campaign_turn.active_card = "hermann"
    st.campaign_turn.actions_remaining = 5
    apply_action(st, {"type": "cmd_march", "side": "teutonic",
                     "args": {"lord_id": "hermann", "to": dest, "group": ["hermann"]}})
    assert h.location == dest
    assert h.in_stronghold is False


def test_in_stronghold_cleared_on_avoid_battle():
    """Avoiding Battle to a new Locale clears in_stronghold."""
    from nevsky.state import CombatPending
    st = load_scenario("pleskau", seed=1)
    # Place gavrilo with in_stronghold=True at pskov, attacker approaching from neva
    g = st.lords["gavrilo"]
    g.in_stronghold = True
    # Find a destination adjacent to pskov but free of enemies/strongholds
    adj_dests = []
    for w in load_ways():
        if w["a"] == "pskov":
            adj_dests.append((w["b"], w["type"]))
        elif w["b"] == "pskov":
            adj_dests.append((w["a"], w["type"]))
    # Find a free dest
    dest = None
    for cand, wt in adj_dests:
        loc = st.locales[cand]
        if loc.teutonic_conquered > 0:
            continue
        # not enemy stronghold
        from nevsky.static_data import load_locales
        sl = load_locales().get(cand, {})
        if sl.get("territory") == "teutonic":
            continue
        # No enemy Lord at dest
        if any(L.side == "teutonic" and L.state == "mustered" and L.location == cand
               for L in st.lords.values()):
            continue
        dest = cand
        break
    assert dest, "no free dest"
    # Set up combat_pending
    st.combat_pending = CombatPending(
        attacker_side="teutonic", attacker_group=["hermann"],
        from_locale="neva", to_locale="pskov", way_type="trackway",
        defender_side="russian", defender_lords=["gavrilo"],
        pending_response_by="russian", laden=False,
    )
    apply_action(st, {"type": "avoid_battle", "side": "russian", "args": {"to": dest}})
    assert g.location == dest
    assert g.in_stronghold is False


# -----------------------------------------------------------------
# SMOKE-037: re-Mustered Lord must clear stale in_stronghold and
# per-card flags (3.4.1).
# -----------------------------------------------------------------

from nevsky.actions import _disband_at_limit, _place_lord_on_map
from nevsky.static_data import load_lords as _load_lords


def test_remuster_clears_in_stronghold():
    """A Lord who Disbanded while in_stronghold=True must come back
    in_stronghold=False on the next Muster (placed at a Seat in open)."""
    st = load_scenario("pleskau", seed=1)
    h = st.lords["hermann"]
    h.in_stronghold = True
    _disband_at_limit(st, "hermann", 4)
    assert h.state == "disbanded"
    # Re-Muster: _place_lord_on_map at a Seat
    static = _load_lords()
    sl = static["hermann"]
    seat = sl.get("primary_seat", sl["seats"][0] if "seats" in sl else "reval")
    _place_lord_on_map(st, "hermann", seat, levy_box=1)
    assert h.state == "mustered"
    assert h.in_stronghold is False


def test_remuster_clears_per_card_flags():
    """Per-card flags (first_march_used_this_card, raiders_used_this_card)
    must reset on Muster — they're per-card and a fresh Mustered Lord
    has not yet had any card revealed."""
    st = load_scenario("pleskau", seed=1)
    h = st.lords["hermann"]
    h.first_march_used_this_card = True
    h.raiders_used_this_card = True
    _disband_at_limit(st, "hermann", 4)
    static = _load_lords()
    sl = static["hermann"]
    seat = sl.get("primary_seat", sl["seats"][0] if "seats" in sl else "reval")
    _place_lord_on_map(st, "hermann", seat, levy_box=1)
    assert h.first_march_used_this_card is False
    assert h.raiders_used_this_card is False
