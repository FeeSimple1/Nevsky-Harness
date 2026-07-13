"""Shared scripted-die support for the Playbook golden tests.

The Background Book's Examples of Play print specific die rolls. To
replay them, ScriptedRolls replaces nevsky.rng.roll_d6 with a strict
FIFO of the printed rolls -- it still advances meta.rng_state so state
bookkeeping matches a real roll, and it fails loudly if the engine
consumes more or different rolls than the example prints.

battle.py binds roll_d6 at import time, so patch BOTH nevsky.rng and
nevsky.battle. actions.py / campaign.py import inside functions and
resolve through nevsky.rng at call time.
"""
from __future__ import annotations


class ScriptedRolls:
    def __init__(self, rolls):
        self.rolls = list(rolls)
        self.consumed: list[int] = []

    def __call__(self, state):
        if not self.rolls:
            raise AssertionError(
                f"scripted rolls exhausted after {self.consumed}")
        r = self.rolls.pop(0)
        self.consumed.append(r)
        state.meta.rng_state += 1
        return r


def script_rolls(monkeypatch, rolls) -> ScriptedRolls:
    import nevsky.battle
    import nevsky.rng
    sr = ScriptedRolls(rolls)
    monkeypatch.setattr(nevsky.rng, "roll_d6", sr)
    monkeypatch.setattr(nevsky.battle, "roll_d6", sr)
    return sr
