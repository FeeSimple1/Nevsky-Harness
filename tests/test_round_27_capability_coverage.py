"""Round 27: focused tests for the two capabilities the audit found
without dedicated functional tests — Archbishopric of Novgorod (R15)
and Hillforts of the Sword Brethren (T8).

The other 24 capabilities have existing test coverage (verified by
grepping the test suite for capability names)."""
from __future__ import annotations

from nevsky.actions import apply_action
from nevsky.campaign import _effective_command_rating, _hillforts_skip_lord
from nevsky.scenarios import load_scenario
from nevsky.static_data import load_lords as _static_lords


def _setup_with_caps_in_play(scenario, side, caps):
    """Force-load a scenario, push named capability cards into play."""
    s = load_scenario(scenario, seed=1)
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})
    deck = s.decks.teutonic if side == "teutonic" else s.decks.russian
    for cap in caps:
        if cap not in deck.capabilities_in_play:
            deck.capabilities_in_play.append(cap)
    return s


# ---------------------------------------------------------------------------
# R15 Archbishopric of Novgorod
# ---------------------------------------------------------------------------


def test_r15_archbishopric_grants_cmd_plus_1_at_novgorod():
    """Russian Lord starting a Command card at Novgorod gets +1
    effective Command when R15 in play."""
    s = _setup_with_caps_in_play("watland", "russian", ["R15"])
    # Domash starts at Novgorod in Watland setup.
    assert s.lords["domash"].location == "novgorod"
    static = _static_lords()
    base_cmd = int(static["domash"]["ratings"]["command"])
    eff = _effective_command_rating(s, "domash")
    assert eff == base_cmd + 1, (
        f"R15 should grant +1 Cmd at Novgorod: base={base_cmd}, eff={eff}"
    )


def test_r15_no_bonus_when_lord_not_at_novgorod():
    s = _setup_with_caps_in_play("watland", "russian", ["R15"])
    # Vladislav starts at Ladoga in Watland.
    assert s.lords["vladislav"].location != "novgorod"
    static = _static_lords()
    base_cmd = int(static["vladislav"]["ratings"]["command"])
    eff = _effective_command_rating(s, "vladislav")
    # No bonus from R15 (not at Novgorod). May still get other side-wide
    # bonuses (Druzhina if Knights present etc.).
    # Vladislav has no Knights, no Druzhina active, so eff should equal base.
    assert eff == base_cmd


def test_r15_no_bonus_without_capability_in_play():
    s = load_scenario("watland", seed=1)
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})
    # R15 NOT in play.
    assert "R15" not in s.decks.russian.capabilities_in_play
    static = _static_lords()
    base_cmd = int(static["domash"]["ratings"]["command"])
    eff = _effective_command_rating(s, "domash")
    assert eff == base_cmd


def test_r15_bonus_only_for_russian_side():
    """Sanity: even if T15 (which has the same numeric position) were
    confused, Teutons don't get an Archbishopric bonus."""
    s = _setup_with_caps_in_play("watland", "russian", ["R15"])
    static = _static_lords()
    # Andreas at Fellin (not Novgorod) — no R15 bonus.
    base_cmd = int(static["andreas"]["ratings"]["command"])
    eff = _effective_command_rating(s, "andreas")
    # Andreas has Marshal +1 by Q-003 if he's the senior Marshal — for
    # this scenario test we just check that the bonus delta from R15 is
    # zero (bonus from Marshal status is unrelated). Recompute his
    # cmd without R15.
    s.decks.russian.capabilities_in_play.remove("R15")
    eff_no_r15 = _effective_command_rating(s, "andreas")
    # R15 bonus must not affect Teutonic Lords.
    assert eff == eff_no_r15


# ---------------------------------------------------------------------------
# T8 Hillforts of the Sword Brethren
# ---------------------------------------------------------------------------


def test_t8_hillforts_returns_eligible_lord_in_livonia():
    """T8: at Feed, one Teutonic Lord in Livonia who has moved/fought
    skips Feed."""
    s = _setup_with_caps_in_play("watland", "teutonic", ["T8"])
    # Andreas at Fellin (Livonia). Mark moved_fought.
    s.lords["andreas"].moved_fought = True
    chosen = _hillforts_skip_lord(s, "teutonic")
    assert chosen == "andreas", (
        f"T8 should pick a Teutonic Lord in Livonia who has acted; got {chosen}"
    )


def test_t8_returns_none_without_capability():
    s = load_scenario("watland", seed=1)
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "teutonic", "args": {}})
    apply_action(s, {"type": "confirm_all_setup_transports", "side": "russian", "args": {}})
    s.lords["andreas"].moved_fought = True
    chosen = _hillforts_skip_lord(s, "teutonic")
    assert chosen is None


def test_t8_returns_none_for_russian_side():
    s = _setup_with_caps_in_play("watland", "teutonic", ["T8"])
    s.lords["andreas"].moved_fought = True
    # Even with T8 active and an eligible Teu Lord, asking for Russian skip
    # returns None (T8 is Teu side-wide).
    chosen = _hillforts_skip_lord(s, "russian")
    assert chosen is None


def test_t8_skips_besieged_lord():
    """A Besieged Teutonic Lord shouldn't be picked even if otherwise
    eligible (rule: 'Unbesieged' qualifier)."""
    s = _setup_with_caps_in_play("watland", "teutonic", ["T8"])
    # Set Andreas Besieged: place Siege at Fellin and put him inside.
    s.locales["fellin"].siege_markers = 1
    s.lords["andreas"].in_stronghold = True
    s.lords["andreas"].moved_fought = True
    chosen = _hillforts_skip_lord(s, "teutonic")
    # Should pick someone else if eligible, or None.
    assert chosen != "andreas"


def test_t8_returns_none_when_no_lord_moved():
    """T8 only skips Lords who actually fought/moved."""
    s = _setup_with_caps_in_play("watland", "teutonic", ["T8"])
    # Ensure no T Lord has moved_fought set.
    for l in s.lords.values():
        if l.side == "teutonic":
            l.moved_fought = False
    chosen = _hillforts_skip_lord(s, "teutonic")
    assert chosen is None
