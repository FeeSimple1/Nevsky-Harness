# Pleskau end-to-end playthrough — LLM (Teutonic) vs simulated opponent

Session: pleskau_seed1
LLM side: teutonic
Human side: russian
Scenario: Pleskau (2 turns)

## Initial briefing

```
# Nevsky game state — you play TEUTONIC

Scenario: pleskau  Seed: 1  Calendar box: 1 (Summer)
Span: box 1 → 2

## Phase
Levy phase, step **arts_of_war**, active player **teutonic**.
This is the FIRST Levy (3.1.2): drawn AoW cards are implemented as Capabilities, not Events.

## Victory Points
Teutonic: 0.0  Russian: 1.0
Pleskau bonus: +1 VP per enemy Lord removed (T removed by R: 0, R removed by T: 0).

## Your Lords (teutonic)
- **andreas** [removed]: at (off-board)
    cmd 3, lordship 3, service 4; cylinder (on map), service marker not on Calendar
- **hermann** [mustered]: at dorpat
    cmd 3, lordship 3, service 4; cylinder (on map), service marker box 4
    forces: knights×1, sergeants×1, men_at_arms×1, militia×1
    assets: coin×1, provender×1, cart×1
- **rudolf** [ready]: at (off-board)
    cmd 3, lordship 1, service 2; cylinder box 1, service marker not on Calendar
- **heinrich** [removed]: at (off-board)
    cmd 1, lordship 2, service 4; cylinder (on map), service marker not on Calendar
- **yaroslav** [mustered]: at odenpah
    cmd 2, lordship 1, service 2; cylinder (on map), service marker box 2
    forces: knights×1, men_at_arms×1, light_horse×1
    assets: provender×1, cart×1
- **knud_and_abel** [mustered]: at reval
    cmd 2, lordship 3, service 3; cylinder (on map), service marker box 3
    forces: knights×1, sergeants×1, men_at_arms×2, militia×1
    assets: coin×1, provender×2, ship×2

## Opponent Lords (russian)
- **aleksandr** [removed]: at (off-board)
    cmd
...
```

  Step 0: LLM (T) → advance_step args={}; outcome: {}
  Step 1: HUMAN (R) → advance_step args={}; outcome: {}
  Step 2: LLM (T) → advance_step args={}; outcome: {}
  Step 3: HUMAN (R) → advance_step args={}; outcome: {}
  Step 4: LLM (T) → advance_step args={}; outcome: {}
  Step 5: HUMAN (R) → advance_step args={}; outcome: {}
  Step 6: LLM (T) → advance_step args={}; outcome: {}
  Step 7: HUMAN (R) → advance_step args={}; outcome: {}
  Step 8: LLM (T) → advance_step args={}; outcome: {}
  Step 9: HUMAN (R) → advance_step args={}; outcome: {}
  Step 10: LLM (T) → plan_add_card args={'card': 'hermann'}; outcome: {}
  Step 11: LLM (T) → plan_add_card args={'card': 'yaroslav'}; outcome: {}
  Step 25: LLM (T) → cmd_march FAILED: excess_provender: hermann has 1 more Provender than 2x usable Transport (4.3.2); pass args.discard_excess_provender=True to discard
           fell back to end_card
  Step 29: HUMAN (R) → cmd_ravage FAILED: own_territory: Cannot Ravage own territory (pskov)
           fell back to end_card
  Step 33: LLM (T) → cmd_ravage FAILED: own_territory: Cannot Ravage own territory (odenpah)
           fell back to end_card
  Step 37: HUMAN (R) → cmd_ravage FAILED: own_territory: Cannot Ravage own territory (neva)
           fell back to end_card
  Step 41: LLM (T) → cmd_ravage FAILED: own_territory: Cannot Ravage own territory (reval)
           fell back to end_card
  Step 92: LLM (T) → cmd_march FAILED: excess_provender: hermann has 1 more Provender than 2x usable Transport (4.3.2); pass args.discard_excess_provender=True to discard
           fell back to end_card
  Step 96: HUMAN (R) → cmd_ravage FAILED: own_territory: Cannot Ravage own territory (pskov)
           fell back to end_card
  Step 103: HUMAN (R) → cmd_ravage FAILED: own_territory: Cannot Ravage own territory (neva)
           fell back to end_card
  Step 107: LLM (T) → cmd_ravage FAILED: own_territory: Cannot Ravage own territory (reval)
           fell back to end_card

## End state

Terminal: True
Steps: 133
Final box: 2
VP — Teutonic: 0.0, Russian: 1.0
Winner: {'winner': 'russian', 'reason': '5.3 higher VP', 't_vp': 0.0, 'r_vp': 1.0, 'applied_override': None}

## Action mix (LLM as Teutonic)

  fpd_resolve: 24
  plan_add_card: 12
  command_reveal: 12
  advance_step: 10
  end_card: 5
  finalize_plan: 2
  end_campaign_resolve: 2