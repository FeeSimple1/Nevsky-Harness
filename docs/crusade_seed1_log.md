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

### Box 2 (Summer) — Levy + Campaign highlights
- AoW Events: Teu T1 "Grand Prince favors a son" -> shift **Aleksandr box5->7** (delay Russian hammer a season). Rus R10 "Batu Khan" -> shift **Andreas box3->5** (delay Teutonic Marshal). T6/R15 no-target reveal-discard.
- Disband: **yaroslav disbanded** (svc box2, no coin/payer at Ugaunia).
- Teu Muster (knud only able; besiegers can't muster): knud mustered dietrich+otto (knights+MAA) -> stack knights3/MAA4 + Balistarii; +1 cart.
- Rus Muster: domash Luchniki (militia/LH archery) + novgorod_1; gavrilo borderland + Black Sea Trade (R8, +1 Veche coin/CtA); vladislav ingrian_aux + sled.
- **STORM IZBORSK (hermann+Trebuchets, rudolf reserve):** beat the fort garrison (MAA+knights wiped), **Izborsk CONQUERED (teutonic_conquered=1), +1 VP, spoils loot/prov/coin to hermann.** VERIFIED: conquest recorded via locale.teutonic_conquered (not a conquered_by field); forts have inherent garrisons; all consistent — no bug.
- **Score: Teu 1.0 / Rus 0.0.**

### Box 2 end — KNUD DISBANDED (Unfed cascade) — VERIFIED CORRECT (not a bug)
At box-2 FPD after knud's march to Uzmen, knud's 9-unit stack needed **2 Provender** to Feed (units>=7 -> 2; rule 4.8.1) but had only 1 (the Uzmen waterway march discarded excess provender; an earlier end-of-campaign wastage cost a ship). Engine: Unfed penalty = shift Service 1 box LEFT (box3->2) -> service == campaign marker (box2) -> at-limit Disband (4.8.2->3.3.2) -> cylinder placed SERVICE_RATING(3) right of NEXT box (3) = **box 6**. All steps match the rules. **STRATEGIC LESSON (my blunder): do not field a 7+ unit stack (2 provender/Feed) while marching away from friendly supply; the "discard_excess_provender" prompt on knud's Uzmen march was the warning sign.** knud lost; Teutonic Pskov assault now relies on hermann+rudolf.

**Box 3 (Early Winter) start:** Teu hermann+rudolf @ Izborsk (conquered), knud disbanded->box6. Rus gavrilo holds Pskov(walls+1, 9-unit garrison), domash @ Dubrovno (Luchniki +2 serfs), vladislav @ Novgorod (paid to box4, +2 serfs). VP Teu 1.0 / Rus 0.0. Aleksandr box7, Andrey box5, Andreas box5.

### Box 3 Pskov assault — HERMANN DISBANDED (Unfed on march) + ORPHANED SIEGE BUG (SMOKE-153)
- gavrilo withdrew inside Pskov (4.3.4) when hermann approached -> besieged, siege_markers=1, walls+1 kept.
- At FPD, hermann (marched = MOVED_FOUGHT, legit) needed 1 Provender, had 0 -> **Unfed -> service shift left -> disbanded** (cylinder box 8). Correct under BOTH rule readings (March requires Feed). My supply blunder: marched the Trebuchets lord into the assault with 0 provender. Three lords now lost to Feed (knud, vladislav, hermann).
- **BUG SMOKE-153 (real, R215):** hermann was Pskov's SOLE besieger. After his disband, `pskov.siege_markers` stayed 1 and gavrilo stayed `in_stronghold` -> `_is_besieged(gavrilo)=True` with **0 besiegers present**. The engine lifts sieges only on combat (Sally/Storm) outcomes, never when the last besieger departs (march-away) or is removed (disband/permanent). Masked here only because rudolf re-besieges at T-slot-2 before gavrilo's card. Fixing as R215: lift siege when no besiegers remain at a besieged stronghold.

### Box 3 conclusion + STOP point (Q-009 paralysis)
- R215 fix merged into the playthrough engine; the orphaned Pskov siege was corrected in-state (siege_markers 0, gavrilo freed, walls+1 intact) to match what the fixed engine would have produced at Hermann's disband.
- Teutonic offensive collapsed: hermann + knud both lost to Unfed; only rudolf (5u) holds conquered Izborsk. Russia strong: gavrilo (9u) free at Pskov(walls+1), domash (7u) reserve at Dubrovno.
- **Q-009 paralysis observed (concrete):** under behavior B (any Command action -> Feed), BOTH sides' large stacks (gavrilo 9u, domash 7u, rudolf) have 0 provender and CANNOT take ANY command (even Tax/Forage at their own city) without Feeding 2 -> Unfed -> Service drift -> Disband. gavrilo would Disband if he merely Taxed Pskov. A 7+ unit stack also cannot self-sustain by Foraging (forage +1 vs Feed -2). This makes mid-game play a starvation spiral and is strong evidence behavior B may be wrong — flagged in Q-009 for adjudication. Both lords PASSED to avoid disband.
- **Clean resumable checkpoint: box 4 (Early Winter) Levy/arts_of_war. VP Teu 1.0 / Rus 0.0.** Recommend adjudicating Q-009 before resuming the deep playthrough.
