# Open Questions

Format per BRIEF: ID, Context, Consultation log (5 steps), What is
ambiguous, Options, Affects, Blocking?

When resolved, MOVE the entry to RULES_DECISIONS.md with the user's
adjudication, citation, and commit hash.

---

## Q-003 — Lieutenants: enforce "Neither may currently be a Marshal" (4.1.3)

**Context.**
4.1.3 says a Lieutenant pairing requires that "neither may currently
be a Marshal." Marshal roles are encoded in `lords.json` static data
as `marshal_role: "permanent" | "secondary" | null`. The current
`place_lieutenant` action in `campaign.py` does NOT enforce this
constraint.

**Consultation log.**
1. *Reference.* `reference/Nevsky_Lords.txt` records `marshal_role`
   per Lord. `reference/Nevsky_Sequence_of_Play.txt` Lieutenants
   section: "Lieutenant -- neither may currently be a Marshal".
2. *Rules of Play 4.1.3.* Same constraint. Not consulted directly
   (PDF restriction).
3. *Cross-references.* The Marshal role is also relevant to group
   March (4.3.1) and Battle array Front Center (4.4.1). Phase 4d
   does not implement front-center positioning, so Marshals are
   currently un-modeled.
4. *Playbook.* Not consulted.
5. *2E.* Not relevant.

**What is ambiguous.**
Whether "currently a Marshal" means "has marshal_role != None
statically" OR "is currently THE side's active Marshal in this
Battle / Campaign". The static-data interpretation is strict
(permanent Marshals like Andreas/Aleksandr can NEVER be Lieutenants).
The dynamic interpretation is permissive (only the actively-chosen
Marshal at the current moment is excluded). Since front-center is
not modeled, "current" is hard to define.

**Options.**

a. *Enforce strictly.* `marshal_role != None` -> reject pairing as
   Lieutenant. Affects Andreas, Aleksandr (permanent), Hermann,
   Andrey (secondary). Conservative; matches static reading of rules.
b. *Enforce only permanent.* `marshal_role == "permanent"` -> reject.
   Secondary Marshals (Hermann, Andrey) can be Lieutenants outside
   their Marshal moments. Closer to "currently".
c. *Don't enforce (current behavior).* Defer to player judgment.

**Affects.**
- `src/nevsky/campaign.py::_h_place_lieutenant`
- `tests/test_lieutenants.py`

**Blocking?**
No. Phase 4d default is permissive (option c). Game-play impact is
small unless a player tries to construct exotic Marshal+Lower-Lord
pairings.
