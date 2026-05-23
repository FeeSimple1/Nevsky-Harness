"""R215 (SMOKE-153): a Stronghold's Siege must lift when its last besieger
leaves (March away) or is removed (Disband / permanent removal). A Stronghold
is Besieged only while enemy besiegers are present (4.3.5).

Surfaced in the Crusade seed-1 LLM self-play: Hermann, Pskov's sole besieger,
was Unfed and Disbanded during FPD; pre-fix `pskov.siege_markers` stayed 1 and
Gavrilo remained `_is_besieged` with 0 besiegers present.
"""
import nevsky.actions  # noqa: F401 (import order)
from nevsky.actions import (
    _lift_siege_if_no_besiegers,
    _is_besieged,
    _disband_at_limit,
    _remove_lord_permanently,
)
from nevsky.scenarios import load_scenario
from nevsky.static_data import load_lords


def _setup_besieged_pskov(seed=1):
    s = load_scenario("crusade_on_novgorod", seed=seed)
    g = s.lords["gavrilo"]
    h = s.lords["hermann"]
    g.state = "mustered"; g.location = "pskov"; g.in_stronghold = True
    h.state = "mustered"; h.location = "pskov"; h.in_stronghold = False
    s.locales["pskov"].siege_markers = 1
    return s


def test_helper_lifts_when_no_besieger():
    s = _setup_besieged_pskov()
    # Remove the besieger first (simulate departure), then helper lifts.
    s.lords["hermann"].location = None
    assert _is_besieged(s, "gavrilo") is True
    lifted = _lift_siege_if_no_besiegers(s, "pskov")
    assert lifted is True
    assert s.locales["pskov"].siege_markers == 0
    assert s.lords["gavrilo"].in_stronghold is False
    assert _is_besieged(s, "gavrilo") is False


def test_helper_no_lift_while_besieger_present():
    s = _setup_besieged_pskov()
    lifted = _lift_siege_if_no_besiegers(s, "pskov")
    assert lifted is False
    assert s.locales["pskov"].siege_markers == 1
    assert _is_besieged(s, "gavrilo") is True


def test_helper_lifts_empty_stronghold_free_of_enemies():
    # R218 (Inferno Advisory #2, Door B): RoP 4.3.5 -- a besieged
    # Stronghold free of ENEMY Lords loses its Siege markers whether or not
    # a defender is inside. With the sole besieger (hermann) gone and only
    # the owner's Lord (gavrilo, in the open) present, the Siege lifts.
    # (Pre-R218 this no-op'd, leaving a stale marker; R215's original test
    # encoded that now-corrected behavior.)
    s = _setup_besieged_pskov()
    s.lords["gavrilo"].in_stronghold = False
    s.lords["hermann"].location = None
    lifted = _lift_siege_if_no_besiegers(s, "pskov")
    assert lifted is True
    assert s.locales["pskov"].siege_markers == 0


def test_disband_of_sole_besieger_lifts_siege():
    # The exact playthrough case: the sole besieger Disbands -> siege lifts.
    s = _setup_besieged_pskov()
    assert _is_besieged(s, "gavrilo") is True
    _disband_at_limit(s, "hermann", new_box_with_overflow=8)
    assert s.lords["hermann"].state == "disbanded"
    assert s.locales["pskov"].siege_markers == 0
    assert _is_besieged(s, "gavrilo") is False


def test_permanent_removal_of_sole_besieger_lifts_siege():
    s = _setup_besieged_pskov()
    _remove_lord_permanently(s, "hermann", load_lords()["hermann"])
    assert s.locales["pskov"].siege_markers == 0
    assert _is_besieged(s, "gavrilo") is False


def test_disband_with_second_besieger_keeps_siege():
    # Two besiegers; disband one -> siege persists (other remains).
    s = _setup_besieged_pskov()
    r = s.lords["rudolf"]
    r.state = "mustered"; r.location = "pskov"; r.in_stronghold = False
    _disband_at_limit(s, "hermann", new_box_with_overflow=8)
    assert s.locales["pskov"].siege_markers == 1
    assert _is_besieged(s, "gavrilo") is True
