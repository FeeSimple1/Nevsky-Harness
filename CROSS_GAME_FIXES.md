# Cross-game audit repairs

The November 4, 2026 cross-game audit identified six Nevsky defect groups.
The first batch addressed **N1, N2, and N3**, all in the simple Sally path.

- **N1 — Routed besiegers:** fully Routed losing Lords may Retreat and roll
  Losses. A Lord who loses his final unit in Losses is then removed, yields
  all non-Ship Assets as Spoils, and triggers Ransom where applicable. Losses
  now precede Spoils, including when a conceding besieger is removed.
- **N2 — Held Events:** Sally consumes and applies Battle Holds through the
  ordinary Battle validator. The legal menu advertises available cards and
  target parameters using the same participant/role context as execution.
- **N3 — Array:** the activating Lord is explicitly the Active Attacker at
  Front center. Other Array decisions use the normal scripted/live Battle
  decision context instead of being limited to automatic defaults.

Regression tests use seeded public Sally actions to cover recovery, removal,
Ransom, conceded versus ordinary Spoils, blocked Retreats, real Field Organ
combat effects, invalid Hold rollback, menu parameters, and Active-Lord/other
Lord placement. Existing source-inspection Ransom checks were adjusted for
removal after Losses.

## Reset repair batch — N4 and N5

- **N4 — Final Serf removal:** returning a Lord's final Serf immediately
  Disbands him under 1.6/3.3.2. His cylinder goes his Service rating beyond the
  next Levy; mat Assets, Capabilities and Service markers return normally.
  A final-Lord departure ends the Campaign before any Calendar advance.
  Removing Special Vassals follows the same empty-Lord rule. Automatic Summer
  Crusader expiry occurs after the marker flips to Levy, so it counts from
  that new box and does not create a Campaign victory in Levy.
- **N5 — Voluntary Reset discards:** `args.reset_discard` and its legal menu
  include Holds, side-wide Capabilities and This Lord Capabilities. Selection
  is validated before resolution and executed after Wastage and Serf return.
  Side-wide cards run their normal Legate/Special-Vassal cleanup, then return
  to the draw deck. Cards already returned by mandatory cleanup are not
  duplicated. Foreign, duplicate and malformed selections reject atomically.

Capability-limit enforcement also recounts Mustered Lords after each cascade;
players can name the extra discards a resulting Disband requires. Three older
card-selection tests now give their Mustered fixture Lord a regular Force so
they continue to test card choice while he survives Special-Vassal removal.

Twenty-one new regression cases cover both findings, off-board Calendar
placement, besieged Serfs, surviving Lords, marker/card cleanup, immediate
victory, next-Levy timing, cascade-dependent Capability limits, save/load,
legal-menu coverage and rejected-action rollback. Against the preceding main
revision, fifteen cases fail and six preservation/validation cases pass.

Validation: 1,931 tests passed. All 150 self-play cases across three scenarios,
25 seeds and two policies completed without invariant violations or step-limit
exits. The changed source adds no Ruff or mypy diagnostics relative to main.

## Hidden Mats repair batch — IF-3

Session, notebook, compact and detailed player views now share the optional
Hidden Mats filter. Opposing Mustered Lords' Forces, Routed units, Assets,
This Lord Capabilities and Vassal mat status are concealed consistently.
A constant mask avoids revealing whether a hidden Force pile is empty.
Owners retain full access, and public Advanced Vassal Service Calendar
markers remain visible. Player views leave the saved mechanical state intact.

During actual Battle, Sally and Storm decision callbacks, participating mats
are visible under the combat exception while other enemy mats stay hidden.
The reveal scope ends on normal return or exception and is separate from
saved game state.

Twenty-three regressions cover both sides, Hidden Mats and Advanced Vassal
Service combinations, real Muster changes, save/load, focused inspections,
mask consistency and live combat callbacks. Nineteen fail against the
preceding main revision; four preservation cases pass.

Validation: 1,954 tests passed. All 150 self-play cases across three scenarios,
25 seeds and two policies completed without invariant violations or step-limit
exits. Changed source adds no Ruff diagnostics relative to main, and the new
visibility module passes mypy.

All six original Nevsky audit findings are fixed.

## Second audit, batch 2 — N2-01, N2-02 and N2-03

- **N2-01 — Relief Sally:** all losing besieged joiners use Withdrawal
  aftermath, including fully Routed Lords. They roll Losses without Retreat
  movement or Service rolls. Survivors stay inside; final-Force deaths apply
  normal removal, non-Ship Spoils and Ransom. Routed piles no longer remain
  unresolved after the Battle.
- **N2-02 — Withdrawal capacity:** the post-Battle election counts friendly
  Lords already inside, including partial Approach withdrawals. An overfull
  selection rejects with state, dice and retained object references restored;
  a legal retry is equivalent to resolving from the untouched save.
- **N2-03 — Retreat Transport:** ordinary/Relief Battle and simple Sally
  now group Conceding survivors by destination and actual Retreat Way after
  Losses. Usable Transport is shared under the current Season. Removed Lords,
  withdrawing Lords and different-route groups cannot donate capacity. An
  optional, menu-discoverable `retreat_keep_order` preserves player choice
  over whose food remains; food and Transport stay on their owners' mats.

Twenty-five new regressions cover seeded Relief Sally, final-Force deaths,
Spoils/Ransom, existing and partial-Approach occupancy, legal retries,
co-Retreat loads, both priority choices, Transport-holder food priority,
seasonal Boats/Carts/Sleds, separate destinations, withdrawn/removed donors,
simple Sally, save/load, menus and malformed-priority rollback. Nineteen fail
on the preceding main revision; six preservation cases pass.

Validation: 1,979 tests passed. All 150 self-play cases across three scenarios,
25 seeds and two policies completed without invariant violations or step-limit
exits. New and updated tests pass Ruff; changed source adds no Ruff diagnostics
relative to the preceding main. Two historical source-inspection checks now
exercise public Sally outcomes for Spoils and the actual Retreat Way.

Second-audit progress: **3 of 4 Nevsky groups fixed**. IF2-1, side-bound tool
ownership validation, remains open. The original six groups remain fixed.

## Second audit, batch 3 — IF2-1

The side-bound action tool rejects an explicitly conflicting action side,
including attempts to use the system actor, before setup auto-confirmation,
card drawing, RNG use or history changes. Invalid caller identities and
malformed action envelopes reject as well. Missing sides still default to
the caller, and valid owner actions retain the engine's normal turn and
reactive-event validation. Caller dictionaries are not modified.

Sixteen new cases cover both players, opponent/system/invalid identities,
missing and explicit matching sides, malformed envelopes and rejected-action
state/reference preservation. Nine fail on the preceding main revision;
seven preservation cases pass.

Validation: 1,995 tests passed. All 150 configured self-play cases completed
without invariant violations or step-limit exits. New tests pass Ruff, and
changed source adds no Ruff diagnostics relative to the preceding main.

All **four second-audit Nevsky groups are fixed**, as are the original six.

## Third audit, batch 1 — N3-03 through N3-05

An Avoid priority list now applies to the co-Avoiders' full usable Transport
capacity, using the same calculation as Retreat. A player can also specify
an exact retention split on the owners' mats. The default reserves each
Lord's own Transport first and then shares spare capacity. Distinct Lord IDs
are required before capacity is counted.

When discarded Assets can be split more than one way, the approaching player
allocates the public pool in a saved response window. The menu shows the pool
and remaining room. An explicit plan can fill any part of that pool, with
unassigned Assets spilling in approaching order. Forced awards resolve
immediately. The choice resumes the remaining defenders' response or completes
the Approach and any resulting Siege or Feed. Ambush follows validation of
the declared Avoid and precedes movement, discards and allocation.

Twenty-five regressions cover full and exact retention, malformed or repeated
IDs, default and custom awards, cap overflow, owner authority, partial
responses, atomic retry, save/load and Ambush timing. Against preceding main,
22 fail and three control cases pass. The playbook replay explicitly assigns
the discarded Provender to Andreas and verifies the original Feed totals.

**2,020 tests passed.** All 150 configured invariant cases completed without
violations or step-limit exits. New tests pass Ruff, and changed source adds
no Ruff diagnostics relative to preceding main.

Third-audit progress is **three of six Nevsky groups** and **10 of 23 overall**.
