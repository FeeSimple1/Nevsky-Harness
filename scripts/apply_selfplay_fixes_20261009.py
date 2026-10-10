"""One-shot, pinned-source repair; run by the isolated repair workflow."""
from pathlib import Path
import ast
import hashlib

ROOT = Path(__file__).resolve().parents[1]


def load(path, expected_blob):
    raw = (ROOT / path).read_bytes()
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    if blob != expected_blob:
        raise RuntimeError(f"{path}: unexpected source {blob}; refusing to overwrite")
    return raw.decode("utf-8")


def once(text, before, after):
    if text.count(before) != 1:
        raise RuntimeError(f"Expected one replacement site: {before[:100]!r}")
    return text.replace(before, after, 1)


path = "src/nevsky/legal_moves.py"
text = load(path, "9215399066d77d169aa1228c9b66675ce88723e5")
text = once(text,
            'if lid not in deck.plan:  # cannot plan same Lord twice in one stack',
            'if deck.plan.count(lid) < 3:  # 1.9.2: three Command cards per Lord')
updates = {path: text}

path = "src/nevsky/actions.py"
text = load(path, "7d25857891a6b85d65e2685f4062599defb0bffd")
helper = '''def _award_lord_departure_vp(state: GameState, lord_id: str) -> None:
    """Pleskau (6.0): +1 VP whenever an enemy Lord leaves the map.

    Call before either Disband/removal path changes the Lord's state or
    location. Only a Mustered, on-map Lord qualifies: repeated cleanup,
    off-map Calendar removals, and scenario-excluded Lords award nothing.
    Re-Mustering restores eligibility for a subsequent, distinct departure.
    The counter, live VP, and Calendar marker must all advance together.
    """
    lord = state.lords[lord_id]
    if (not state.meta.special_rules.get("victory_lord_removed_bonus", False)
            or lord.state != "mustered" or lord.location is None):
        return
    if lord.side == "russian":
        state.calendar.pleskau_lords_removed_russian += 1
        state.calendar.teutonic_vp += 1.0
    else:
        state.calendar.pleskau_lords_removed_teutonic += 1
        state.calendar.russian_vp += 1.0
    from nevsky.scenarios import refresh_victory_markers
    refresh_victory_markers(state)  # Includes the 17.5-VP cap.


'''
text = once(text,
            'def _remove_lord_permanently(state: GameState, lord_id: str, sl: dict[str, Any]) -> None:',
            helper + 'def _remove_lord_permanently(state: GameState, lord_id: str, sl: dict[str, Any]) -> None:')
old_bonus = '''    # Pleskau bonus: increment counter for the OTHER side.
    # SMOKE-024 (Round 36): also mirror the bonus into the
    # calendar.<other_side>_vp incremental float, since
    # determine_scenario_winner reads that float (not _compute_vp from
    # markers). Without this mirror, the Pleskau "+1 VP per enemy Lord
    # removed" rule didn't reach the winner determination at all.
    if state.meta.special_rules.get("victory_lord_removed_bonus", False):
        if side == "russian":
            state.calendar.pleskau_lords_removed_russian += 1
            state.calendar.teutonic_vp += 1.0
        else:
            state.calendar.pleskau_lords_removed_teutonic += 1
            state.calendar.russian_vp += 1.0
        from nevsky.scenarios import refresh_victory_markers
        refresh_victory_markers(state)
'''
text = once(text, old_bonus, '    _award_lord_departure_vp(state, lord_id)\n')
text = once(text,
            '    side: Side = lord.side\n    # SMOKE-088 (Round 92): capture pre-disband location for the',
            '    side: Side = lord.side\n    _award_lord_departure_vp(state, lord_id)\n    # SMOKE-088 (Round 92): capture pre-disband location for the')
updates[path] = text

path = "scripts/chatgpt_play_helper.py"
text = load(path, "a91e8663dd726573afd8e38bae70450638fcec2a")
text = once(text, 'from collections import Counter, defaultdict\n',
            'from collections import defaultdict\nfrom copy import deepcopy\n')
text = once(text, 'def apply(choice):\n', '''def _record_action(side, action):
    """Record each successful manual or forced move once, before advancing."""
    _S["history"].append({"turn": _S["turn"], "side": side,
                          "action": deepcopy(action)})
    _S["turn"] += 1


def apply(choice):
''')
text = once(text,
            '    _S["history"].append({"turn": _S["turn"], "side": side, "action": action})\n    _S["turn"] += 1\n',
            '    _record_action(side, action)\n')
text = once(text, '        _S["turn"] += 1\n        n += 1\n',
            '        _record_action(side, action)\n        n += 1\n')
text = once(text, '                                "no_legal_moves", "invariant")]\n',
            '                                "no_legal_moves", "invariant",\n                                "over_enum_filtered")]\n')
text = once(text,
            '    for f in notable:\n        print("  ", json.dumps(f, default=str)[:240])\n    if not notable:\n',
            '    for f in _S["findings"]:\n        print("  ", json.dumps(f, default=str))\n    if not _S["findings"]:\n')
updates[path] = text

# Validate every edited module before writing any of them.
for path, text in updates.items():
    ast.parse(text, filename=path)
for path, text in updates.items():
    (ROOT / path).write_text(text, encoding="utf-8")
    print(f"Patched {path}")
