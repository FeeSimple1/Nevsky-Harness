"""Follow the completed game with independent rule-level diagnostics.

These tests report the baseline's behavior; they do not fix it or alter the
legal-move generator. The original full game is replayed through apply_action.
"""
from __future__ import annotations
import contextlib
import importlib.util
import inspect
import io
import json
from pathlib import Path


def test_rule_diagnostics_from_completed_game(capsys):
    import nevsky.actions as actions
    from nevsky.actions import apply_action, IllegalAction
    from nevsky.legal_moves import legal_moves
    from nevsky.scenarios import load_scenario, determine_scenario_winner

    path = Path(__file__).with_name("test_playthrough_20261009.py")
    spec = importlib.util.spec_from_file_location("diagnostic_game", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class LocalCapture:
        def disabled(self):
            return contextlib.nullcontext()

    capture = io.StringIO()
    with contextlib.redirect_stdout(capture):
        module.test_diagnostic_pleskau_game(LocalCapture())
    raw = capture.getvalue().split("NEVSKY_PLAYTEST_REPORT_BEGIN", 1)[1].split("NEVSKY_PLAYTEST_REPORT_END", 1)[0]
    original_report = json.loads(raw)
    state = load_scenario("pleskau", seed=20261009)
    repeat_checks, removals = [], []
    tested_sides = set()

    def vp(s, side):
        return s.calendar.teutonic_vp if side == "teutonic" else s.calendar.russian_vp

    for entry in original_report["transcript"]:
        action = entry.get("action") or entry.get("setup")
        side = action["side"]
        if action["type"] == "plan_add_card" and side not in tested_sides:
            deck = state.decks.teutonic if side == "teutonic" else state.decks.russian
            existing = next((card for card in deck.plan if card != "pass"), None)
            if existing is not None:
                probe = state.model_copy(deep=True)
                candidate = {"type": "plan_add_card", "side": side, "args": {"card": existing}}
                offered = any(a.get("type") == candidate["type"] and a.get("side") == side and a.get("args") == candidate["args"] for a in legal_moves(state, with_previews=False))
                accepted_counts, fourth_rejection = [], None
                while (probe.decks.teutonic if side == "teutonic" else probe.decks.russian).plan.count(existing) < 3:
                    apply_action(probe, candidate)
                    pd = probe.decks.teutonic if side == "teutonic" else probe.decks.russian
                    accepted_counts.append(pd.plan.count(existing))
                try:
                    apply_action(probe, candidate)
                except IllegalAction as exc:
                    fourth_rejection = str(exc.args[0])
                repeat_checks.append({"side": side, "step": entry.get("step"), "lord": existing, "plan_before": list(deck.plan), "repeat_offered": offered, "handler_accepted_copy_numbers": accepted_counts, "fourth_copy_rejection": fourth_rejection})
                tested_sides.add(side)
        before = {lid: lord.side for lid, lord in state.lords.items() if lord.state == "mustered" and lord.location is not None}
        before_vp = {sd: vp(state, sd) for sd in ("teutonic", "russian")}
        result = apply_action(state, action)
        after = {lid for lid, lord in state.lords.items() if lord.state == "mustered" and lord.location is not None}
        departed = set(before) - after
        for departing_side in ("teutonic", "russian"):
            lords = sorted(lid for lid in departed if before[lid] == departing_side)
            if not lords:
                continue
            beneficiary = "russian" if departing_side == "teutonic" else "teutonic"
            actual = vp(state, beneficiary) - before_vp[beneficiary]
            removals.append({"step": entry.get("step"), "box": entry.get("box"), "action": action, "departed_lords": lords, "states_after": {lid: state.lords[lid].state for lid in lords}, "beneficiary": beneficiary, "expected_bonus": len(lords), "actual_vp_change": actual, "result": result})
    sources = {}
    for name in ("_disband_at_limit", "_remove_lord_permanently"):
        fn = getattr(actions, name)
        text, first_line = inspect.getsourcelines(fn)
        sources[name] = {"file": "src/nevsky/actions.py", "first_line": first_line, "last_line": first_line + len(text) - 1, "source": "".join(text)}
    evidence = {"repeat_command_cards": repeat_checks, "map_departures": removals, "replayed_winner": determine_scenario_winner(state), "source_locations": {name: {k: v for k, v in data.items() if k != "source"} for name, data in sources.items()}}
    with capsys.disabled():
        print("\nNEVSKY_RULE_DIAGNOSTIC_BEGIN")
        print(json.dumps(evidence, indent=2, default=str))
        print("NEVSKY_RULE_DIAGNOSTIC_END")
        for name, data in sources.items():
            print("NEVSKY_FUNCTION_SOURCE " + name)
            print(data["source"])
    assert tested_sides == {"teutonic", "russian"}, "Both sides must reach repeat-card probe"
    assert len(removals) == 3, "Expected Gavrilo, Yaroslav, and Knud & Abel to leave the map"
