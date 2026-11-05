# Cross-game audit repairs

The November 4, 2026 cross-game audit identified six Nevsky defect groups.
This batch addresses **N1, N2, and N3**, all in the simple Sally path.

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

Three of six Nevsky findings are fixed. Serf Reset cleanup, voluntary Reset
Capability discard, and Hidden Mats view consistency remain open.
