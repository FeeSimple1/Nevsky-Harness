"""Player-owned Battle order and seeded replay through March and Stand."""

import pytest

from nevsky.actions import IllegalAction, apply_action
from nevsky.llm.session import LLMSession
from nevsky.llm.view import view_for_side
from nevsky.state import GameState
from tests.test_cross_game_relief_retreat import place, position


def _approach(*, mounted=False, order=None):
    state = position(seed=1, box=9)
    unit = "knights" if mounted else "men_at_arms"
    for lid in ("andreas", "hermann"):
        place(state, lid, {unit: 1}).location = "ostrov"
    for lid in ("aleksandr", "gavrilo"):
        place(state, lid, {"men_at_arms": 1})
    state.campaign_turn.active_card = state.campaign_turn.active_lord = "andreas"
    session = LLMSession(state, "teutonic", "crusade_on_novgorod")
    march = {"lord_id": "andreas", "to": "pskov", "way_type": "waterway", "group": ["hermann"]}
    if order is not None:
        march["strike_order"] = order
    session.apply({"type": "cmd_march", "args": march})
    return session


def _stand(session, **args):
    action = next(move for move in session.legal_actions_for_human()
                  if move["type"] == "stand_battle" and move["args"].get("concede") == "defender")
    assert "strike_order_template" in action
    return session.apply({**action, "args": {**action["args"], **args}}, who="human")["battle"]


def test_defender_reverses_foot_strikes_without_changing_the_array():
    checkpoint = _approach().state.model_dump_json()

    def resolve(args):
        session = LLMSession(GameState.model_validate_json(checkpoint), "teutonic", "crusade_on_novgorod")
        return _stand(session, **args), session.state.model_dump_json()

    ordinary, _ = resolve({})
    plan = {"strike_order": {"1:melee_foot": ["hermann", "andreas"]}}
    reverse, final = resolve(plan)
    assert (reverse, final) == resolve(plan)
    forward_step, reverse_step = [battle["log"][0]["steps"][0] for battle in (ordinary, reverse)]
    assert forward_step["per_striker"] == reverse_step["per_striker"]
    assert [row["lord"] for row in forward_step["distribution"]] == ["andreas", "hermann"]
    assert [row["lord"] for row in reverse_step["distribution"]] == ["hermann", "andreas"]
    assert [row["routed"] for row in forward_step["distribution"]] == [
        row["routed"] for row in reverse_step["distribution"]]
    decision = next(d for d in reverse["decisions"] if d["type"] == "strike_order")
    assert (decision["side"], decision["options"], decision["chosen"]) == (
        "defender", ["andreas", "hermann"], "hermann")


def test_attacker_order_survives_save_and_is_private_until_resolution(tmp_path):
    order = {"1:melee_horse": ["gavrilo", "aleksandr"]}
    session = _approach(mounted=True, order=order)
    path = tmp_path / "approach.json"
    session.save(path)
    restored = LLMSession.load(path)
    assert restored.state.combat_pending.attacker_strike_order == order
    view = view_for_side(restored.state, "russian")
    assert "attacker_strike_order" not in view["combat_pending"]
    assert "strike_order" not in view["history"][-1]["action"]["args"]

    before = restored.state.model_dump_json()
    with pytest.raises(IllegalAction) as exc:
        _stand(restored, strike_order=order)  # Defender cannot order its own Lords as targets.
    assert exc.value.code == "bad_strike_order"
    assert restored.state.model_dump_json() == before
    result = _stand(restored)
    assert _stand(session) == result
    assert session.state.model_dump_json() == restored.state.model_dump_json()
    first = result["log"][0]["steps"][0]
    assert first["step"] == "melee_horse_attacker"
    assert [row["lord"] for row in first["distribution"]] == ["gavrilo", "aleksandr"]


def test_referee_script_can_choose_the_next_strike_group():
    session = _approach()
    result = apply_action(session.state, {"type": "stand_battle", "side": "russian", "args": {
        "concede": "defender", "scripted_decisions": [
            {"type": "initial_placement_attacker", "chosen": "left"},
            {"type": "initial_placement_defender", "chosen": "gavrilo"},
            {"type": "strike_order", "side": "defender", "chosen": "hermann"},
        ],
    }})["battle"]
    step = result["log"][0]["steps"][0]
    assert [row["lord"] for row in step["distribution"]] == ["hermann", "andreas"]
