"""Round 223 — LLM-play interface fixes (GPT-5.5 Crusade self-play).

Three issues surfaced by an index-driven LLM driver:
  A. cmd_sail was emitted as a TEMPLATE (args_template, no concrete args).
     An index-driven model picked it, apply() got no args -> missing_arg
     IllegalAction (turn 82). Fix: enumerate one concrete Sail per legal
     destination Seaport.
  B. aow_shuffle stayed available even when the deck already had cards,
     and aow_discard_this_levy stayed available with nothing to discard --
     both repeatable no-ops that trap naive drivers in an infinite spin.
"""

import nevsky.actions  # noqa: F401  (registers handlers; import order)
import nevsky.campaign  # noqa: F401
from nevsky.scenarios import load_scenario
from nevsky.legal_moves import legal_moves
from nevsky.actions import apply_action


def _setup_sail(st, lid, src="reval"):
    L = st.lords[lid]
    L.location = src
    L.in_stronghold = False
    L.forces = {"knights": 1}
    L.assets["provender"] = 0
    L.assets["loot"] = 0
    L.assets["ship"] = 9  # plenty
    st.locales[src].siege_markers = 0
    st.meta.box = 8  # summer
    st.meta.phase = "campaign"
    st.meta.campaign_step = "command"
    st.meta.active_player = L.side
    st.campaign_turn.active_lord = lid
    st.campaign_turn.active_card = lid
    st.campaign_turn.actions_remaining = 9  # pristine card


# ---- A: cmd_sail concretization -------------------------------------------

def test_sail_enumerated_with_concrete_args_not_template():
    st = load_scenario("pleskau", seed=1)
    _setup_sail(st, "hermann")
    sail = [m for m in legal_moves(st, with_previews=False) if m["type"] == "cmd_sail"]
    assert sail, "expected at least one concrete Sail move from a Seaport"
    for m in sail:
        assert "args_template" not in m, "Sail must not be a template move"
        a = m["args"]
        assert a["lord_id"] == "hermann"
        assert isinstance(a["destination"], str) and a["destination"] != "reval"
        assert a["group"] == ["hermann"]


def test_every_enumerated_sail_is_applyable():
    """The whole point: an index-driven driver can apply any offered Sail
    verbatim without hitting missing_arg / IllegalAction."""
    st = load_scenario("pleskau", seed=1)
    _setup_sail(st, "hermann")
    sail = [m for m in legal_moves(st, with_previews=False) if m["type"] == "cmd_sail"]
    assert sail
    for m in sail:
        probe = st.model_copy(deep=True)
        # must not raise
        apply_action(probe, {"type": "cmd_sail", "side": "teutonic", "args": m["args"]})


def test_no_sail_offered_when_lord_not_at_seaport():
    st = load_scenario("pleskau", seed=1)
    _setup_sail(st, "hermann")
    # move the Lord to a non-seaport Locale
    inland = next(lid for lid, v in
                  __import__("nevsky.static_data", fromlist=["load_locales"])
                  .load_locales().items() if v.get("seaport") is not True)
    st.lords["hermann"].location = inland
    st.locales[inland].siege_markers = 0
    sail = [m for m in legal_moves(st, with_previews=False) if m["type"] == "cmd_sail"]
    assert sail == [], f"no Sail should be offered from inland {inland}"


# ---- B: AoW no-op suppression ---------------------------------------------

def _aow_setup(st, side="teutonic"):
    st.meta.phase = "levy"
    st.meta.levy_step = "arts_of_war"
    st.meta.active_player = side
    return st


def test_aow_shuffle_not_offered_when_deck_has_cards():
    st = load_scenario("pleskau", seed=1)
    _aow_setup(st, "teutonic")
    d = st.decks.teutonic
    assert d.deck, "fixture expects a non-empty deck"
    moves = legal_moves(st, with_previews=False)
    assert not any(m["type"] == "aow_shuffle" for m in moves), \
        "shuffle is a no-op when the deck already has cards"
    assert any(m["type"] == "aow_draw" for m in moves)


def test_aow_shuffle_offered_only_when_deck_empty_and_discard_present():
    st = load_scenario("pleskau", seed=1)
    _aow_setup(st, "teutonic")
    d = st.decks.teutonic
    d.discard = list(d.deck)
    d.deck = []
    moves = legal_moves(st, with_previews=False)
    assert any(m["type"] == "aow_shuffle" for m in moves), \
        "shuffle should be offered to reconstitute an empty deck from discards"


def test_aow_discard_this_levy_not_offered_when_nothing_to_discard():
    st = load_scenario("crusade_on_novgorod", seed=1)
    st.meta.phase = "levy"
    st.meta.levy_step = "call_to_arms"
    for side in ("teutonic", "russian"):
        st.meta.active_player = side
        deck = getattr(st.decks, side)
        deck.this_levy_events = []
        moves = legal_moves(st, with_previews=False)
        assert not any(m["type"] == "aow_discard_this_levy" for m in moves), \
            f"{side}: discard is a no-op with no This-Levy events"
