# Crusade on Novgorod — seed 1 — LLM self-play strategic log

Driver: scripts/llm_self_play.py  State: docs/crusade_seed1.state.json
Baseline: main @ 480c589 (R213), verification battery clean.
Played by Claude switching perspective each turn, respecting hidden info.
Bug-hunting run: STOP and investigate anything that looks wrong.

## Setup (box 1, Summer, span 1->16)
Teutonic mustered: hermann@dorpat, yaroslav@odenpah, knud_and_abel@reval (ships x2).
Teutonic ready off-board: andreas, rudolf, heinrich.
Russian mustered: gavrilo@pskov, vladislav@neva. Ready off-board: aleksandr, andrey, domash, karelians.
Start VP: Teu 0.0 / Rus 1.0.

## Strategic frame
- Teutonic = crusade aggressor: must conquer Russian strongholds (Pskov, Novgorod approaches) for VP.
- Russian = defend, exploit Rasputitsa/winter, time Aleksandr's arrival.

## Turn-by-turn

### Box 1 (Summer) — First Levy
**Arts of War (capabilities, 3.1.2):**
- Teutonic drew T4 Balistarii -> knud_and_abel (2 MAA), T12 Ordensburgen (side-wide: Commanderies = extra Seats, +1 Cmd there).
- Russian drew R13 Streltsy -> vladislav (2 MAA, cmd3), R12 Raiders -> gavrilo@pskov (front-line scorched earth).

**Pay (3.2):** Both sides skipped — no Service marker at/left of box-1 Levy marker; conserve coin.
**Disband (3.3):** No-op both sides.

**Teutonic Muster (3.4)** — budget 7 (hermann 3, yaroslav 1, knud 3):
- hermann: muster heinrich@fellin x2 FAILED (Fealty 3); then Trebuchets (T14) on hermann (siege Pskov).
- yaroslav: Converts (T3) — group reaches 1st locale free (yaroslav has light horse).
- knud: muster rudolf@fellin (1 fail, then success, Fealty 5, cmd3 reinforcement); Cogs (T18) on knud.
- Net: rudolf mustered@fellin; heinrich not mustered. Caps now: Balistarii(knud), Trebuchets(hermann), Converts(yaroslav), Cogs(knud), Ordensburgen(side).
- Plan: mass at Dorpat/Odenpah/Fellin, push Dorpat->Ugaunia->Izborsk->Pskov; knud sails the lakes; siege Pskov with Trebuchets.

---
## ROUND 214 — BUG FOUND & FIXED, playthrough restarted on fixed engine
**SMOKE-152:** At box1 command, yaroslav (Command 2) revealed his card at Odenpah with **3 actions**. Root cause: `_effective_command_rating` granted Ordensburgen (T12) +1 at any of a Lord's `primary_seats`, not just Commanderies. Odenpah is yaroslav's seat but NOT a Commandery. Per Q-004 / AoW T12 tips / Map 226-236 the +1 applies only at Wenden/Fellin/Adsel/Leal (all flagged commandery:true). Fixed: gate purely on the commandery flag. Regression test added; full battery clean (pytest 1315, sweep 300, tournament 24/24, roundtrip 0). Merged to main @ 687eeb5.

Playthrough restarted from a fresh seed-1 game on the fixed engine; Levy+Plan (turns 1-49) replayed deterministically (identical: rudolf@fellin, domash@novgorod, heinrich still ready, Veche markers 0). yaroslav now correctly has 2 actions. Resuming from box1 command.

### Box 1 (Summer) — Campaign command (fixed engine)
- T slot1 yaroslav (Cmd 2, Converts+LH): Odenpah->Dorpat (free, Converts), Dorpat->Ugaunia (1), Forage (1). Forward screen on Izborsk approach, +1 provender.
- T slot2 hermann (Cmd 3, base — fix confirms no +1 at Dorpat): Dorpat->Ugaunia->Izborsk, **besieged Izborsk** (undefended fort).
- R slot2 gavrilo: **Stone Kremlin** -> Pskov Walls +1.
- T slot3 rudolf (Cmd 3 +1 Fellin Commandery = 4, fix confirms legit +1): Fellin->Dorpat->Ugaunia->Izborsk, joined hermann's siege; Forage. (Verified: joining an already-besieged stronghold does NOT end the card — Commands.txt L60 "begin Siege" only on UNbesieged. Not a bug.)
- R slot3 vladislav: Neva->Ladoga->Volkhov->Novgorod (consolidate strongest Russian centrally for the Aleksandr counterstroke; abandons Neva).
- T slot4 knud: Sail Reval->Narwia (Cogs) — stage the Balistarii stack toward the Dorpat axis.
- Slots 5-6 pass both sides. End box 1.

**Box 1 end state:** Teu hermann+rudolf besiege Izborsk (siege 1), yaroslav@Ugaunia, knud@Narwia. Rus gavrilo holds Pskov(walls+1), domash@Dubrovno, vladislav@Novgorod. VP 0-0.
**Box 2 plan:** Teu storm Izborsk (Trebuchets) for first VP; bring knud up. Rus hold Pskov; domash supports; await Aleksandr (box 5).
