"""3.1.3/4.1: private cards stay private across every filtered state view."""
from nevsky.actions import apply_action
from nevsky.llm.briefing import briefing_for_side
from nevsky.llm.review import build_review_artifact
from nevsky.llm.session import LLMSession
from nevsky.llm.view import own_decks, view_for_side
from nevsky.scenarios import load_scenario


def test_opponent_draw_history_does_not_reveal_private_cards():
    """3.1.3: filtering the card zone must also filter the draw log."""
    session = LLMSession.start_new("watland", llm_side="russian", seed=1)
    session.apply({"type": "aow_draw", "args": {}}, who="human")
    before = session.state.model_dump_json()
    view = session.full_state()
    assert view["decks"]["teutonic"]["pending_draw"] == ["<hidden>"] * 2
    assert view["history"][-1]["result"]["drawn"] == ["<hidden>"] * 2
    own = view_for_side(session.state, "teutonic")
    assert own["history"][-1]["result"]["drawn"] == session.state.decks.teutonic.pending_draw
    assert own["decks"]["teutonic"]["pending_draw"] == session.state.decks.teutonic.pending_draw
    assert session.state.model_dump_json() == before


def test_opponent_hold_implementation_is_private_but_public_capabilities_remain():
    """3.1.3: a Hold entering the hand is secret; a face-up Capability is public."""
    s = load_scenario("watland", seed=1)
    s.meta.first_levy_done = True
    s.decks.teutonic.deck.remove("T6")
    s.decks.teutonic.pending_draw = ["T6"]
    apply_action(s, {"type": "aow_implement_card", "side": "teutonic",
                     "args": {"card_id": "T6"}})
    s.decks.teutonic.capabilities_in_play = ["T12"]
    view = view_for_side(s, "russian")
    held = view["history"][-1]
    assert held["action"]["args"] == {"card_id": "<hidden>"}
    assert held["result"] == {"card": "<hidden>", "outcome": "held"}
    assert view["decks"]["teutonic"]["holds"] == ["<hidden>"]
    assert view["decks"]["teutonic"]["capabilities_in_play"] == ["T12"]
    assert view_for_side(s, "teutonic")["history"][-1]["result"]["card"] == "T6"


def test_opponent_plan_is_private_in_history_until_revealed():
    """4.1/4.2: plan construction is secret; the revealed active card is public."""
    s = load_scenario("watland", seed=1)
    s.meta.phase = "campaign"
    s.meta.campaign_step = "plan"
    apply_action(s, {"type": "plan_add_card", "side": "teutonic",
                     "args": {"card": "andreas"}})
    hidden = view_for_side(s, "russian")
    assert hidden["decks"]["teutonic"]["plan"] == ["<hidden>"]
    assert hidden["history"][-1]["action"]["args"]["card"] == "<hidden>"
    assert hidden["history"][-1]["result"]["appended"] == "<hidden>"
    assert view_for_side(s, "teutonic")["history"][-1]["result"]["appended"] == "andreas"
    s.meta.campaign_step = "command"
    apply_action(s, {"type": "command_reveal", "side": "teutonic", "args": {}})
    public = view_for_side(s, "russian")
    assert public["campaign_turn"]["active_card"] == "andreas"
    assert public["history"][-1] == s.history[-1].model_dump()


def test_draw_piles_and_rng_inputs_are_not_available_to_either_player():
    """3.1: future shuffles/dice remain unknown, including through own_decks."""
    session = LLMSession.start_new("watland", llm_side="teutonic", seed=73129)
    before = session.state.model_dump_json()
    for side in ("teutonic", "russian"):
        view = view_for_side(session.state, side)
        assert "seed" not in view["meta"] and "rng_state" not in view["meta"]
        for deck_side in ("teutonic", "russian"):
            assert set(view["decks"][deck_side]["deck"]) == {"<hidden>"}
        assert set(own_decks(session.state, side)["deck"]) == {"<hidden>"}
        assert "73129" not in briefing_for_side(session.state, side)
    assert build_review_artifact(session)["seed"] is None
    assert session.state.model_dump_json() == before


def test_midgame_review_does_not_disclose_opponent_reasoning():
    """4.1: private human plan notes must not enter the opponent's review."""
    session = LLMSession.start_new("watland", llm_side="russian", seed=1)
    session.state.meta.phase = "campaign"
    session.state.meta.campaign_step = "plan"
    secret = "My hidden plan begins with Andreas and Hold T6"
    session.apply({"type": "plan_add_card", "args": {"card": "andreas"}},
                  who="human", reasoning=secret)
    assert build_review_artifact(session)["llm_reasoning_log"] == []
    assert session.history[-1]["reasoning"] == secret
