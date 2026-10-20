"""In-process play helper for GPT-5.5 (or any ChatGPT) running this repo in
its own Python sandbox -- NO API key, NO network. ChatGPT IS the player:
it runs the harness here and decides each move itself.

Setup (paste once in ChatGPT's python tool after uploading/unzipping the repo):
    import sys
    sys.path.insert(0, "src"); sys.path.insert(0, "scripts")
    import chatgpt_play_helper as nv
    nv.start("crusade_on_novgorod", seed=1)

Then loop:
    nv.show()        # fresh compact position + action-category counts
    page = nv.actions("cmd_march", lord="hermann")
    nv.action(page["items"][0]["id"])  # full arguments/metadata, when needed
    nv.apply(page["items"][0]["id"])   # state-bound selection; never substitutes a fallback
    nv.auto()        # auto-advance forced/boilerplate turns; stops at next real choice
    ...
    nv.findings_report()   # the bug triage queue (illegal/exception/stall/invariant)

Only dependency is pydantic (already in the sandbox). Goal: a different
model walks different trajectories and surfaces different engine bugs;
every anomaly is captured automatically.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import traceback
from collections import defaultdict
from copy import deepcopy
from pathlib import Path

if "src" not in sys.path:
    sys.path.insert(0, "src")

import nevsky.actions  # noqa: F401
from nevsky.actions import IllegalAction, apply_action
from nevsky.llm.action_browser import ActionBrowser, DisplayDict, MenuList, encode
from nevsky.llm.compact import compact_briefing, detail_payload, player_view
from nevsky.llm.tools import safe_fallback_for_side
from nevsky.scenarios import SCENARIO_IDS, determine_scenario_winner, load_scenario

_spec = importlib.util.spec_from_file_location(
    "llm_sp", Path(__file__).resolve().parent / "llm_self_play.py")
_llm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_llm)
_concrete_actions = _llm._concrete_actions
_cav = _llm.concrete_actions_validated

_S = {"state": None, "scenario": None, "history": [], "findings": [], "turn": 0}
_BROWSER = ActionBrowser()


def _validated(s, side, log_rejects=True):
    """Validated, LLM-safe action menu (P0): only actions the handler
    accepts. Any filtered (over-enumerated) candidate is recorded as an
    `over_enum_filtered` finding so the root enumerator bug is still
    surfaced for the maintainer to fix."""
    validated, rejected = _cav(s, side)
    if log_rejects:
        for r in rejected:
            _S["findings"].append({"kind": "over_enum_filtered", "turn": _S["turn"],
                                   "side": side, **r})
    return validated


def _terminal() -> bool:
    s = _S["state"]
    return s.meta.game_over or (s.meta.phase == "campaign" and s.meta.campaign_step == "done")


def _coloc(s):
    by = defaultdict(set)
    for l in s.lords.values():
        if l.state == "mustered" and l.location is not None and not l.in_stronghold:
            by[l.location].add(l.side)
    bad = [loc for loc, sides in by.items() if len(sides) > 1]
    cp = s.combat_pending
    if cp is not None:
        bad = [loc for loc in bad if loc != cp.to_locale]
    return bad


def _check_invariants():
    s = _S["state"]
    out = []
    co = _coloc(s)
    if co:
        out.append(f"co_located_enemies:{co}")
    if s.calendar.teutonic_vp > 17.5 or s.calendar.russian_vp > 17.5:
        out.append("vp_over_cap")
    if s.calendar.teutonic_vp < 0 or s.calendar.russian_vp < 0:
        out.append("vp_negative")
    for v in out:
        _S["findings"].append({"kind": "invariant", "turn": _S["turn"], "violation": v,
                               "box": s.meta.box})
    return out


def start(scenario: str, seed: int = 1, *, confirm_transports: bool = False):
    if scenario not in SCENARIO_IDS:
        raise ValueError(f"unknown scenario {scenario!r}; choose from {sorted(SCENARIO_IDS)}")
    s = load_scenario(scenario, seed=seed)
    if confirm_transports:
        for sd in ("teutonic", "russian"):
            apply_action(s, {"type": "confirm_all_setup_transports", "side": sd, "args": {}})
    _S.update(state=s, scenario=scenario, history=[], findings=[], turn=0)
    _BROWSER.reset()
    print(f"started {scenario} (seed={seed}). Call nv.show() to see the first decision.")
    return show()


def _active():
    return _S["state"].meta.active_player or "teutonic"


def _perspective(side=None):
    if _S["state"] is None:
        raise ValueError("no game; call start() or load() first")
    side = side or _active()
    if side not in ("teutonic", "russian"):
        raise ValueError("side must be teutonic or russian")
    return side


def _overview(side):
    overview = _BROWSER.overview(_S["state"], side, _validated)
    print(f"Actions [{overview['version']}] perspective={side}: "
          f"{overview['total']} entries (templates denote parameter families)")
    print(" | ".join(f"{kind}={info['entries']}" +
                     (f" ({info['templates']} template)" if info['templates'] else "")
                     for kind, info in overview["categories"].items()) or "none")
    if overview["total"] == 1:
        # A sole choice can be displayed fully at negligible cost, avoiding a
        # compulsory follow-up just to reveal a forced draw/reveal/advance ID.
        _, _, rows = _BROWSER.catalog(_S["state"], side, _validated)
        _print_rows(rows, detailed=True)
    print("actions(category,lord=...,params={...},page=1); action(ID) gives full metadata; "
          "apply(ID,args={...}).")
    return overview


def _print_rows(rows, *, detailed=False):
    for row in rows:
        a = row["action"]
        core = {k: v for k, v in a.items() if k in ("args", "args_template", "note", "optional")}
        other = {k: v for k, v in a.items() if k not in (*core, "type", "side")}
        if detailed:
            core.update(other)
        elif other:
            # Never discard metadata. Its field names advertise the detail
            # request; the structured return always contains its full values.
            core["detail_fields"] = list(other)
        print(f"[{row['id']}] {a['type']} {encode(core)}")


def show(side: str | None = None, *, full_menu: bool = False):
    """Fresh compact position and category counts, not the full menu.

    Returns the SAME legacy validated list (including global integer indices),
    as a list subclass with a compact notebook repr. New safe selection uses
    the IDs returned by actions(). full_menu=True explicitly prints everything.
    No change-only briefings or implicit baseline are used.
    """
    side = _perspective(side)
    s = _S["state"]
    if _terminal():
        print("GAME OVER:", determine_scenario_winner(s))
        return MenuList()
    if side != _active():
        print(f"Optional interruptions for {side.upper()}; activation remains {_active()}.")
    print(compact_briefing(s, side))
    _overview(side)
    _, legacy, rows = _BROWSER.catalog(s, side, _validated)
    if full_menu:
        _print_rows(rows, detailed=True)
    if not rows and side == _active():
        _S["findings"].append({"kind": "no_legal_moves", "turn": _S["turn"],
                               "phase": s.meta.phase,
                               "step": s.meta.levy_step if s.meta.phase == "levy" else s.meta.campaign_step,
                               "side": side})
        print("!! no legal moves (stall) — recorded as a finding")
    return legacy


def actions(category=None, lord=None, *, side=None, params=None, query=None,
            templates=None, page=1, page_size=12, detailed=False):
    """Page/filter the complete catalog; IDs retain their unfiltered meaning.

    category is the exact action type printed in show(). Lord matches actor,
    target or group; params matches argument names/values. Unbound templates
    are retained conservatively in Lord/params filters (the handler validates
    their instantiation). query searches all entry text, including metadata.
    templates=True/False selects template/concrete entries; None includes both.
    The full generator metadata is returned even when detailed=False.
    """
    side = _perspective(side)
    result = _BROWSER.page(_S["state"], side, _validated, category=category, lord=lord,
                           params=params, query=query, templates=templates,
                           page=page, page_size=page_size)
    print(f"Actions [{result['version']}] {side}: page {page}/{result['pages']} "
          f"matched={result['matched']}/{result['total']} category={category or '*'} "
          f"lord={lord or '*'} params={encode(params or {})} query={query!r}")
    _print_rows(result["items"], detailed=detailed)
    if result["next_page"]:
        print(f"Next: page={result['next_page']} with the same filters; IDs unchanged.")
    if any("args_template" in r["action"] for r in result["items"]):
        print("Templates: inspect action(ID); supply args explicitly. No strategic filtering.")
    return result


def action(identifier, *, side=None):
    """Full original action/template, including all candidates, Holds and notes."""
    side = _perspective(side)
    row = _BROWSER.get(_S["state"], side, _validated, identifier)
    print(encode(row))
    return DisplayDict(row)


def details(topic="state", *, side=None, lord=None, locale=None, card_id=None):
    """On-demand player-filtered state, printed card rules, supply or other detail."""
    side = _perspective(side)
    payload = detail_payload(_S["state"], side, topic, lord=lord, locale=locale, card_id=card_id)
    print(encode(payload))
    return DisplayDict(topic=topic, side=side, data=payload)


def full_state(side=None):
    """Detached player-filtered full state; never the private save representation."""
    side = _perspective(side)
    data = player_view(_S["state"], side)
    print(encode(data))
    return DisplayDict(data)


def result(*, side=None, full=False):
    """Last result, filtered for this perspective; full=True includes all fields."""
    side = _perspective(side)
    history = player_view(_S["state"], side)["history"]
    if not history:
        data = {}
    else:
        entry = history[-1]
        payload = entry["result"]
        if not full:
            keep = ("outcome", "winner", "loser", "added", "removed", "new_step", "game_over")
            summary = {k: v for k, v in payload.items() if k in keep and
                       isinstance(v, (str, int, float, bool, type(None)))}
            summary["more_fields"] = [k for k in payload if k not in summary]
            payload = summary
        data = {"actor": entry["actor"], "type": entry["action"]["type"], "result": payload}
    print(encode(data))
    return DisplayDict(data)


_print_last_result = result


def _record_action(side, action):
    """Record each successful manual or forced move once, before advancing."""
    _S["history"].append({"turn": _S["turn"], "side": side,
                          "action": deepcopy(action)})
    _S["turn"] += 1


def apply(choice, side: str | None = None, *, args: dict | None = None):
    """Apply a state-bound ID, legacy global int, or raw action dictionary.

    IDs reject stale/wrong-owner/invalid selections without a fallback. args=
    fills a template or adds optional arguments, never changes bound arguments.
    Legacy int/dict behavior and returned next-side list are retained.
    """
    s = _S["state"]
    side = side or _active()
    if side not in ("teutonic", "russian"):
        raise ValueError("side must be teutonic or russian")
    strict = isinstance(choice, str)
    if args is not None and not strict:
        raise TypeError("args= is for state-bound IDs; raw dictionaries already include args")
    if strict:
        action = _BROWSER.resolve(s, side, _validated, choice, args)
        acts = []
    else:
        acts = _validated(s, side, log_rejects=False)
    if strict:
        pass
    elif isinstance(choice, int):
        if not (0 <= choice < len(acts)):
            if side != _active():
                raise ValueError("interruption index out of range; no action applied")
            print(f"index {choice} out of range 0..{len(acts)-1}; applying safe fallback")
            action = safe_fallback_for_side(s, side)
        else:
            a = acts[choice]
            action = {k: v for k, v in a.items() if k in ("type", "side", "args")}
            if "args" not in action:
                action = safe_fallback_for_side(s, side)
    elif isinstance(choice, dict):
        action = {k: v for k, v in choice.items() if k in ("type", "side", "args")}
        action.setdefault("side", side)
        side = action["side"]
    else:
        raise TypeError("choice must be a state-bound ID, int index, or action dict")
    try:
        result = apply_action(s, action)
    except IllegalAction as e:
        if strict:
            print(f"Rejected: {e}; no fallback applied. Inspect action(ID) or supply valid args.")
            raise
        _S["findings"].append({"kind": "illegal_concrete_action", "turn": _S["turn"],
                               "side": side, "action": action, "code": str(e.args[0])[:160]})
        if side != _active():
            print(f"!! ILLEGAL interruption (recorded): {e}; no fallback applied")
            return show(side)
        print(f"!! ILLEGAL (recorded): {str(e.args[0])[:160]} — applying safe fallback")
        action = safe_fallback_for_side(s, side)
        result = apply_action(s, action)
    except Exception as e:
        if strict:
            raise
        _S["findings"].append({"kind": "exception", "turn": _S["turn"], "side": side,
                               "action": action, "etype": type(e).__name__,
                               "msg": str(e)[:200], "tb": traceback.format_exc()[-700:]})
        print(f"!! EXCEPTION (recorded): {type(e).__name__}: {e}")
        return
    _record_action(side, action)
    bad = _check_invariants()
    if bad:
        print("!! INVARIANT VIOLATION (recorded):", bad)
    print(f"applied: {action['type']} ({side})"
          + (f" -> {result.get('outcome')}" if isinstance(result, dict) and result.get('outcome') else ""))
    _print_last_result(side=_active())
    return show()


def auto(max_steps: int = 300):
    """Auto-apply purely forced turns (exactly one legal action) so you skip
    boilerplate (Pass cards, single-option steps, FPD/reveal). Stops and
    show()s at the first turn with a real choice (>=2 actions), or game end.
    Instrumentation runs throughout."""
    s = _S["state"]
    n = 0
    while n < max_steps and not _terminal():
        side = _active()
        acts = _validated(s, side)
        if len(acts) != 1 or acts[0].get("optional"):
            break
        # One action type can still contain a family of choices. Do not
        # auto-resolve templates, Wastage candidates, Battle Holds, etc.
        if any(acts[0].get(k) for k in ("args_template", "candidates", "holds_available")):
            print("Parameter/detail choices require an explicit selection; auto stopped.")
            break
        from nevsky.held_actions import held_actions_for_side
        opponent = "russian" if side == "teutonic" else "teutonic"
        if held_actions_for_side(s, opponent, interrupts_only=True):
            # Generic wording: auto stopping must not identify an opponent's
            # private Hold. The controller may inspect that owner's perspective.
            print("Manual decision boundary; inspect the appropriate side's actions. "
                  "To continue, apply the ordinary active-side action explicitly.")
            break
        a = acts[0]
        action = {k: v for k, v in a.items() if k in ("type", "side", "args")}
        if "args" not in action:
            action = safe_fallback_for_side(s, side)
        try:
            apply_action(s, action)
        except Exception as e:
            _S["findings"].append({"kind": "exception", "turn": _S["turn"], "side": side,
                                   "action": action, "etype": type(e).__name__,
                                   "msg": str(e)[:200], "tb": traceback.format_exc()[-700:]})
            print(f"!! EXCEPTION during auto (recorded): {type(e).__name__}: {e}")
            return
        _record_action(side, action)
        n += 1
        if _check_invariants():
            print("!! INVARIANT VIOLATION during auto (recorded) at turn", _S["turn"])
    print(f"auto-advanced {n} forced turn(s).")
    return show()


def findings_report():
    notable = [f for f in _S["findings"]
               if f["kind"] in ("illegal_concrete_action", "exception",
                                "no_legal_moves", "invariant",
                                "over_enum_filtered")]
    print(f"\n===== FINDINGS: {len(_S['findings'])} total, {len(notable)} notable =====")
    for f in _S["findings"]:
        print("  ", json.dumps(f, default=str))
    if not _S["findings"]:
        print("  (none — no engine anomalies on this trajectory)")
    return _S["findings"]


def save(path: str = "chatgpt_game.json"):
    s = _S["state"]
    Path(path).write_text(json.dumps({"scenario_id": _S["scenario"],
                                      "state_json": s.model_dump_json(),
                                      "history": _S["history"],
                                      "findings": _S["findings"]}, indent=2))
    print("saved ->", path)


def load(path: str = "chatgpt_game.json", *, side=None):
    """Load helper/CLI-compatible save, invalidate all old IDs, print a fresh view.

    Parse and validate before replacing the running game. Browser baselines and
    cached catalogs are never serialized; even loading the same position starts
    a new ID namespace. Raw saves are private controller artifacts, not views.
    """
    from nevsky.state import GameState
    payload = json.loads(Path(path).read_text())
    state = GameState.model_validate_json(payload["state_json"])
    history = payload.get("history", [])
    findings = payload.get("findings", [])
    if not isinstance(history, list) or not isinstance(findings, list):
        raise ValueError("save history and findings must be lists")
    if side is not None and side not in ("teutonic", "russian"):
        raise ValueError("side must be teutonic or russian")
    _S.update(state=state, scenario=payload["scenario_id"], history=history,
              findings=findings, turn=len(history))
    _BROWSER.reset()
    print("Loaded; previous action IDs invalidated. Fresh position:")
    return show(side)
