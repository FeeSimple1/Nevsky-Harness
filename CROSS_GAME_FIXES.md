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
