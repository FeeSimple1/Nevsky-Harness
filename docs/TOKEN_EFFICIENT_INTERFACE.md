# Compact, lossless ChatGPT play interface

The in-process `scripts/chatgpt_play_helper.py` now separates the position,
the inventory of legal action categories, and the individual choices. The
rules engine, action handlers, original legal generator, validators, and
`LLMSession` API are unchanged. This is presentation and selection tooling,
not a strategic agent or an action-ranking system.

## Start and browse

```python
import sys
sys.path[:0] = ["src", "scripts"]
import chatgpt_play_helper as nv

nv.start("crusade_on_novgorod", seed=20261016)
nv.show()                              # fresh position + category counts
page = nv.actions("muster_lord")        # exact category name from the overview
page = nv.actions(lord="hermann")      # actor, target, group or candidate
page = nv.actions("cmd_march", params={"to": "pskov"})
page = nv.actions(page=2, page_size=12) # unfiltered canonical catalog, page 2
```

Only use category names and page numbers present in the current position.
Pages are one-based, with a default size of 12 and a maximum size of 100.
`page["next_page"]` is the next page number or `None`; repeat the same filters
when fetching it. `page["matched"]` is the filtered count and `page["total"]`
is the entire catalog count. An out-of-range page raises an error.

The overview reports **entries**, not a finite number of all possible moves:
a parameterized template represents a family of choices. Each category shows
its entry count and, when present, its template count. A sole catalog entry
is printed in full with its ID, saving a separate request for a forced draw,
reveal or other genuinely single-entry choice. `show(full_menu=True)` explicitly
prints the complete catalog and all its metadata in one response.

Additional filters are `templates=True` (templates only), `templates=False`
(concrete entries only), and `query="text"` (case-insensitive search of all
entry text and metadata). `params={...}` matches exact nested argument values;
`lord=` matches actors, targets, groups and candidate metadata. Unbound
templates are **conservatively retained in Lord and argument filters** because
the requested Lord or value may be a legal instantiation. This can include
extra template matches; it does not silently discard possible choices.

## Inspect, then select a state-bound ID

```python
page = nv.actions("cmd_march", lord="hermann")
choice = page["items"][0]               # choose deliberately, not automatically
nv.action(choice["id"])               # full entry, notes and all candidate fields
nv.apply(choice["id"])                # same choice regardless of filters/pages
```

The ID contains an opaque random session namespace, a position revision,
a player owner, and an absolute catalog ordinal. IDs are not filtered-list
indices. Repeated views, category searches, pagination, detail requests and
switching perspective do not reassign an ID. Successful actions, external
state edits, state replacement, loading, starting a new game, or losing the
browser session invalidate earlier selections. Loading deliberately issues a
fresh namespace even when loading an identical saved board. Private state
fingerprints are **never displayed**; they are not hashes an opponent can
use to guess hidden cards or the next dice.

A stale, malformed, unknown, wrong-perspective or improperly parameterized ID
raises a clear exception **without applying any action or fallback**, spending
resources, changing dice, appending game history, or changing the findings
queue. A rejected engine action using an ID likewise has no substituted move.
The unchanged engine remains the final authority for legality.

## Parameterized actions are first-class choices

The catalog retains every entry of the existing validated menu and also the
original parameterized templates that its concrete expansion would otherwise
replace. In particular, one-Coin examples do not replace the pay template's
other legal quantities. Nothing is dropped for being weak, redundant, unusual,
or unattractive to the automated play policy.

```python
page = nv.actions("pay_with_coin", templates=True)
choice = page["items"][0]
nv.action(choice["id"])               # inspect the actual template and candidates
nv.apply(choice["id"], args={
    "from": "lord:hermann", "target_lord": "hermann", "units": 2
})
```

The example requires the corresponding phase, payer, target and resources;
it is not a claim that this payment is legal in every position. Fixed template
arguments are filled automatically. Supplying `args=` can fill parameter slots
or add optional arguments, but cannot change a concrete entry's bound values
or a template's fixed values. Select a different entry or the original template
to change those. Missing required parameters and illegal instantiations reject
rather than advancing the game. The displayed template is not an assertion
that all conceivable parameter values are legal.

Page rows print the action type, exact concrete arguments or template, notes,
and optional status. Other original metadata is advertised by `detail_fields`
and remains fully present in the structured return. `nv.action(ID)` or
`nv.actions(..., detailed=True)` prints **all** that metadata, including
candidate recipients, supply parameters and battle Hold options. No parameter
schema or explanatory note is truncated. `ACTIONS.md` remains the complete
action grammar; printed card and reference lookups remain available.

## Position, results and player privacy

Every compact briefing is **fresh and self-contained**. There are no change-only
briefings and no implicit baseline to reconstruct after loading or a player
switch. It includes the scenario and season, victory requirements, phase and
Command/Feed-Pay-Disband state, pending decisions, all visible Lords' location,
forces, resources, Service, Lordship usage and bonuses, relevant mat flags,
Capabilities, held Events, the Veche, the Legate, and map markers. Explicit table
headers and default-flag legends replace repeated prose, not decision-relevant
distinctions. Detailed vassal/printed ratings remain one request away.

```python
nv.details("lord", lord="hermann")
nv.details("card", card_id="T3")       # printed text, eligibility, full reference tips
nv.details("supply", lord="hermann")  # Seats, shared transport, events and counters
nv.details("locale", locale="pskov") # terrain/control and adjacent Ways
nv.details("map")                     # all Locales and Ways
nv.details("pending")
nv.details("victory")
nv.full_state()                        # full player-filtered state, not private save
nv.result(full=True)                   # entire last result, filtered for this player
```

Other topics are `cards`, `combat`, `calendar`, `rules`, and `history`.
Supply information does not claim to certify an arbitrary route: inspect the
map and the full `cmd_supply` template, including optional transport conversion
and per-route choices. The handler validates the actual route.

Normal successful `apply()` prints a short result and the new position/overview.
`more_fields` names result fields available through `result(full=True)`; combat,
card effects and other structured outcomes are not discarded. The result uses
the same filtered history representation as full-state access, including when
an action hands the activation to the opponent.

Every new output/structured accessor uses the existing per-side card/history
mask, the optional Hidden Mats mask, and owner-only pending-decision contexts.
Opponent held-card identities, pending draws and plans are not exposed; future
draw order and RNG state are not exposed even to the owning player. Printed
card rules are public information. Optional interruption menus are accessible
only through an explicit owner perspective, without transferring activation:

```python
nv.show("russian")
page = nv.actions("aow_play_hold", side="russian")
nv.apply(page["items"][0]["id"], side="russian")
```

The helper is a local controller allowed to play both sides, **not an
authentication boundary** between two hostile processes sharing Python memory.
`_S` and the save file contain the actual private state; do not hand those to
an opposing player. Use the filtered accessors for player-facing output.

## Compatibility, automatic play and resume

`show()` still returns the original validated menu, with the same order,
values, integer indexing and list behavior. `start()`, `apply()` and `auto()`
retain their next-position list return. The return is a `list` subclass with a
short notebook representation: a notebook no longer prints a second enormous
menu after `show()` has already printed the briefing. `list(value)` restores
ordinary full inspection; slicing, iteration, equality and JSON serialization
remain available. New dictionary accessors likewise return full data with a
short notebook echo; `dict(value)` shows it normally.

Legacy `apply(int)` and raw `apply({...})` remain supported, including the
historical integer/global-menu and fallback behavior. **Bare legacy integers
and raw dictionaries are not state-bound selections.** Use IDs for stale-input
protection. Filtering never changes their old absolute integer meaning. The
new IDs do not appear inside the existing generator's returned action objects.

`auto()` records successful forced actions as before, but stops at optional
choices, original parameter templates, candidate-bearing entries, battle Hold
metadata and opposing interruption opportunities rather than silently choosing
parameters. This is intentionally more conservative than the old automation.

```python
nv.save("game.json")
nv.load("game.json")                   # fresh briefing, restored history/findings
# Request new IDs: selections from before load are deliberately stale.
```

The existing save structure is preserved. Loading validates the entire state
before replacing the current session and restores the helper turn count from
its saved action history. Existing helper and CLI `state_json` saves are
accepted. Corrupt saves leave the current game untouched. No engine schema or
rules-state field was added for UI revisions.

## Tests and measurements

`tests/test_token_efficient_helper.py` verifies complete catalog/page/category
coverage against the unchanged generator, preservation of original templates,
fixed identifiers across filters, stale rejection after every invalidating path,
parameter execution and rollback, both players' hidden information, optional
Hidden Mats, pending and combat windows, programmatic compatibility, and
save/resume. It also drives the complete 860-action Return of the Prince
maritime log through IDs (858 actions after setup), with periodic save/load and
exact state comparison after every action.

See `TOKEN_EFFICIENCY_MEASUREMENTS.md` for measured **complete sequences**, not
just a comparison of the first screen. Every requested page, selected-action
detail, card rule, supply/position detail and full-state response is included.
The exhaustive-browsing workflow may use more output than the old flat menu;
those results are reported rather than hidden behind an output-size target.

## Starting Transport choices

`nv.start()` now preserves each Lord's pending Transport choices. Use the
`set_setup_transport` category to choose Boat, Cart, Sled or Ship for each
allowed slot, or `confirm_all_setup_transports` to accept the active side's
defaults. Non-hotspot defaults still auto-confirm if you proceed with a normal
Levy action, per Q-001. For an automated run that explicitly accepts both
sides' defaults, use `nv.start(scenario, seed=1, confirm_transports=True)`.
`LLMSession.start_new` supports the same keyword.

The Vassal component audit corrected Domash to four starting Transport and
four Provender, and Gavrilo to two starting Transport. Every Transport slot
can be chosen independently, including mixed combinations. See
[Vassal audit](VASSAL_AUDIT_20261019.md).
