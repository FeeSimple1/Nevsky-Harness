"""Round 51 — SMOKE-039 regression tests.

3.5.3 ("both sides discard This-Levy events") is mandatory per rules.
If the agent skips the explicit aow_discard_this_levy action, the
harness must still ensure those events leave the persistence bucket
before the Levy → Campaign transition; otherwise events leak into
the Campaign decks and the next Levy's shuffle is wrong.
"""

from nevsky.scenarios import load_scenario
from nevsky.actions import apply_action


def _drive_call_to_arms_no_explicit_discard(st):
    """Advance both sides through call_to_arms WITHOUT calling
    aow_discard_this_levy. Lands in Campaign / plan step."""
    st.meta.phase = "levy"
    st.meta.levy_step = "call_to_arms"
    st.meta.active_player = "teutonic"
    st.meta.levy_step_completed_t = False
    st.meta.levy_step_completed_r = False
    st.legate.acted_this_call_to_arms = False
    st.veche.acted_this_call_to_arms = False
    apply_action(st, {"type": "legate_skip", "side": "teutonic", "args": {}})
    apply_action(st, {"type": "advance_step", "side": "teutonic", "args": {}})
    apply_action(st, {"type": "veche_action", "side": "russian", "args": {"option": "skip"}})
    apply_action(st, {"type": "advance_step", "side": "russian", "args": {}})


def test_auto_discard_3_5_3_on_transition():
    """If the agent forgets 3.5.3, the harness still discards this_levy_events."""
    st = load_scenario("pleskau", seed=1)
    st.decks.teutonic.this_levy_events = ["T2"]
    st.decks.russian.this_levy_events = ["R5"]
    _drive_call_to_arms_no_explicit_discard(st)
    assert st.meta.phase == "campaign"
    assert st.decks.teutonic.this_levy_events == []
    assert st.decks.russian.this_levy_events == []
    # Events should be in discard now
    assert "T2" in st.decks.teutonic.discard
    assert "R5" in st.decks.russian.discard


def test_explicit_discard_then_advance_idempotent():
    """If the agent does call aow_discard_this_levy first, advance_step's
    auto-fire is idempotent (list is already empty)."""
    st = load_scenario("pleskau", seed=1)
    st.decks.teutonic.this_levy_events = ["T2"]
    st.decks.russian.this_levy_events = ["R5"]
    st.meta.phase = "levy"
    st.meta.levy_step = "call_to_arms"
    st.meta.active_player = "teutonic"
    st.legate.acted_this_call_to_arms = False
    st.veche.acted_this_call_to_arms = False
    apply_action(st, {"type": "legate_skip", "side": "teutonic", "args": {}})
    apply_action(st, {"type": "aow_discard_this_levy", "side": "teutonic", "args": {}})
    apply_action(st, {"type": "advance_step", "side": "teutonic", "args": {}})
    apply_action(st, {"type": "veche_action", "side": "russian", "args": {"option": "skip"}})
    apply_action(st, {"type": "aow_discard_this_levy", "side": "russian", "args": {}})
    apply_action(st, {"type": "advance_step", "side": "russian", "args": {}})
    # Lists are still empty; discard has events once
    assert st.decks.teutonic.this_levy_events == []
    assert st.decks.russian.this_levy_events == []
    assert st.decks.teutonic.discard.count("T2") == 1
    assert st.decks.russian.discard.count("R5") == 1


def test_no_events_to_discard_still_transitions():
    """No this_levy_events case: transition is unaffected."""
    st = load_scenario("pleskau", seed=1)
    st.decks.teutonic.this_levy_events = []
    st.decks.russian.this_levy_events = []
    _drive_call_to_arms_no_explicit_discard(st)
    assert st.meta.phase == "campaign"
