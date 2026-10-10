"""Play-interface diagnostics; intentionally does not change engine behavior."""
from __future__ import annotations
import contextlib
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


def test_helper_diagnostic_evidence(capsys):
    import chatgpt_play_helper as nv
    from strategic_agent import _action_score

    original = dict(nv._S)
    evidence = {}
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            nv.start("pleskau", seed=20261009)
            for _ in range(60):
                if nv._terminal():
                    break
                state = nv._S["state"]
                side = nv._active()
                menu = nv._validated(state, side)
                if len(menu) == 1 and isinstance(menu[0].get("args"), dict):
                    before_turn = nv._S["turn"]
                    before_history = len(nv._S["history"])
                    expected_action = menu[0]
                    nv.auto(max_steps=1)
                    evidence["forced_action_logging"] = {
                        "action": expected_action,
                        "steps_advanced": nv._S["turn"] - before_turn,
                        "actions_logged": len(nv._S["history"]) - before_history,
                        "saved_log_complete": len(nv._S["history"]) - before_history == nv._S["turn"] - before_turn,
                    }
                    break
                concrete = [a for a in menu if isinstance(a.get("args"), dict)]
                if not concrete:
                    break
                nv.apply(max(concrete, key=lambda a: _action_score(state, a, side)))

        # A unit-test fixture tests reporting only; it is NOT represented as
        # an actual engine rejection from the played game.
        fixture = {"kind": "over_enum_filtered", "turn": 0, "side": "teutonic", "action": {"type": "diagnostic_fixture", "args": {}}, "code": "fixture_rejection"}
        nv._S["findings"] = [fixture]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            returned = nv.findings_report()
        evidence["filtered_rejection_summary_fixture"] = {
            "fixture_only": True,
            "findings_returned": len(returned),
            "printed_summary": output.getvalue(),
            "claims_no_engine_anomalies": "no engine anomalies" in output.getvalue(),
        }
    finally:
        nv._S.clear()
        nv._S.update(original)
    with capsys.disabled():
        print("\nNEVSKY_HELPER_DIAGNOSTIC " + json.dumps(evidence, default=str) + "\n")
    assert "forced_action_logging" in evidence, "No forced step reached; logging check was inconclusive"
