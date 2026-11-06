"""Ransom and Sally rewards, settled after combat losses and before play resumes."""

from __future__ import annotations

from typing import Any, cast, get_args

from nevsky.state import AssetType, GameState, PendingDecision, Side

REWARD_ACTION = "allocate_aftermath_reward"


def pending_reward(state: GameState) -> PendingDecision | None:
    return next((p for p in state.pending_decisions if p.kind == REWARD_ACTION), None)


def _ransom_amount(state: GameState, victim: str, owner: Side) -> int:
    from nevsky.capabilities import has_side_capability
    from nevsky.static_data import load_lords

    if not has_side_capability(state, owner, "Ransom"):
        return 0
    lord = load_lords().get(victim)
    return int(lord["ratings"]["service"]) if lord else 0


def _ransom_recipients(state: GameState, owner: Side, locale: str) -> list[str]:
    return [lid for lid, lord in state.lords.items()
            if lord.side == owner and lord.location == locale and lord.state == "mustered"]


def _award_ransom(
    state: GameState, victim: str, amount: int, candidates: list[str], recipient: str | None,
) -> dict[str, Any]:
    from nevsky.actions import IllegalAction
    from nevsky.battle import _award_assets_capped

    if recipient is not None and recipient not in candidates:
        raise IllegalAction("bad_recipient", "choose a friendly Lord present for Ransom")
    if not candidates:
        return {"ransom": True, "coin_lost_no_recipient": amount}
    if recipient is None:
        recipient = max(
            candidates, key=lambda lid: min(amount, 8 - state.lords[lid].assets.get("coin", 0)),
        )
    award = _award_assets_capped(state, recipient, {"coin": amount})
    receipt = {"ransom": True, "removed": victim, "recipient": recipient,
               "coin": award["added"].get("coin", 0)}
    if award["lost_to_cap"]:
        receipt["coin_lost_to_cap"] = award["lost_to_cap"]["coin"]
    return receipt


def apply_ransom(
    state: GameState, removed_lord: str, killer_side: Side, locale_id: str,
    *, recipient: str | None = None,
) -> dict[str, Any]:
    """Apply one T16/R7 reward in referee code."""
    amount = _ransom_amount(state, removed_lord, killer_side)
    if not amount:
        return {"ransom": False}
    return _award_ransom(state, removed_lord, amount,
                         _ransom_recipients(state, killer_side, locale_id), recipient)


def record_ransom(state: GameState, victim: str, *, locale: str | None = None) -> None:
    """Record a qualifying departure before its location and mat are cleared."""
    lord = state.lords[victim]
    owner: Side = "russian" if lord.side == "teutonic" else "teutonic"
    amount = _ransom_amount(state, victim, owner)
    locale = locale if locale is not None else lord.location
    if amount and locale is not None:
        state.pending_decisions.append(PendingDecision(
            kind=REWARD_ACTION, owed_by=owner,
            context={"reward": "ransom", "victim": victim, "coin": amount,
                     "locale": locale},
        ))


def _asset_pool(captured: list[dict[str, Any]]) -> dict[str, int]:
    pool: dict[str, int] = {}
    for entry in captured:
        for asset, count in entry["assets"].items():
            pool[asset] = pool.get(asset, 0) + count
    return pool


def _asset_room(
    state: GameState, candidates: list[str], pool: dict[str, int],
) -> dict[str, dict[str, int]]:
    return {lid: {asset: max(0, 8 - state.lords[lid].assets.get(cast(AssetType, asset), 0))
                  for asset in pool} for lid in candidates}


def _validate_allocation(
    raw: Any, candidates: list[str], pool: dict[str, int] | None = None,
    room: dict[str, dict[str, int]] | None = None,
) -> dict[str, dict[str, int]]:
    from nevsky.actions import IllegalAction

    if not isinstance(raw, dict):
        raise IllegalAction("bad_spoils_allocation", "allocation must map Lords to Asset counts")
    totals: dict[str, int] = {}
    for lid, counts in raw.items():
        if lid not in candidates or not isinstance(counts, dict):
            raise IllegalAction("bad_spoils_allocation", "only eligible Lords receive Sally Spoils")
        for asset, count in counts.items():
            if asset not in get_args(AssetType) or type(count) is not int or count < 0:
                raise IllegalAction(
                    "bad_spoils_allocation", "use valid Assets and nonnegative integers",
                )
            totals[asset] = totals.get(asset, 0) + count
            if pool is not None and room is not None and (
                asset not in pool or count > room[lid][asset] or totals[asset] > pool[asset]
            ):
                raise IllegalAction(
                    "bad_spoils_allocation", "allocation exceeds the pool or mat capacity",
                )
    return {lid: dict(counts) for lid, counts in raw.items()}


def record_sally_spoils(
    state: GameState, winner: Side, candidates: list[str],
    captured: list[dict[str, Any]], args: dict[str, Any],
) -> None:
    if not captured:
        return
    pref = args.get("spoils_recipient")
    priority = [pref] if isinstance(pref, str) else pref if isinstance(pref, list) else []
    order = list(dict.fromkeys(lid for lid in priority if lid in candidates))
    has_priority = bool(order)
    order += [lid for lid in candidates if lid not in order]
    plan = args.get("spoils_allocation")
    allocation = _validate_allocation(plan, candidates) if plan is not None else None
    state.pending_decisions.append(PendingDecision(
        kind=REWARD_ACTION, owed_by=winner,
        context={"reward": "sally_spoils", "captured": captured, "recipients": order,
                 "allocation": allocation, "preselected": has_priority or allocation is not None},
    ))


def record_combat_spoils(
    state: GameState, winner: Side, candidates: list[str], captured: list[dict[str, Any]],
    allocation: dict[str, dict[str, int]] | None, *, award_order: list[int] | None = None,
    stronghold: dict[str, int] | None = None, veche_coin: int = 0,
) -> None:
    """Preserve the existing Battle or Storm allocation after Ransom choices."""
    if captured or stronghold or veche_coin:
        state.pending_decisions.append(PendingDecision(
            kind=REWARD_ACTION, owed_by=winner,
            context={"reward": "storm_spoils" if stronghold is not None else "battle_spoils",
                     "captured": captured, "recipients": candidates, "allocation": allocation,
                     "preselected": True, "award_order": award_order,
                     "stronghold": stronghold, "veche_coin": veche_coin},
        ))


def _reward_options(state: GameState, decision: PendingDecision) -> dict[str, Any]:
    ctx = decision.context
    if ctx["reward"] == "ransom":
        recipients = _ransom_recipients(state, decision.owed_by, ctx["locale"])
        return {"reward": "ransom", "removed": ctx["victim"], "coin": ctx["coin"],
                "recipients": recipients,
                "capacity": _asset_room(state, recipients, {"coin": ctx["coin"]})}
    pool = _asset_pool(ctx["captured"])
    return {"reward": ctx["reward"], "pool": pool, "recipients": ctx["recipients"],
            "capacity": _asset_room(state, ctx["recipients"], pool)}


def _needs_choice(decision: PendingDecision, options: dict[str, Any]) -> bool:
    if options["reward"] == "ransom":
        # Ransom goes to one mat, even if the player chooses a capped one.
        return len(options["recipients"]) > 1 and any(
            room["coin"] for room in options["capacity"].values())
    if decision.context["preselected"]:
        return False
    for asset, count in options["pool"].items():
        rooms = [room[asset] for room in options["capacity"].values() if room[asset] > 0]
        if len(rooms) > 1 and count < sum(rooms):
            return True
    return False


def _award_storm_spoils(
    state: GameState, ctx: dict[str, Any], result: dict[str, Any],
) -> None:
    from nevsky.battle import award_spoils, distribute_spoils

    recipients, plan = ctx["recipients"], ctx["allocation"]
    for captured in ctx["captured"]:
        award = award_spoils(state, recipients, captured, plan)
        result.setdefault("sack_spoils_distribution", []).append({
            "from_lord": award["from"], "split": award["distributed"],
        })
        if award["lost_to_cap"]:
            result.setdefault("storm_spoils_lost_to_cap", []).append({
                "from_lord": award["from"], "lost": award["lost_to_cap"],
            })
    if recipients and ctx["stronghold"]:
        award = distribute_spoils(state, recipients, ctx["stronghold"], plan)
        result["stronghold_spoils_distribution"] = award["added"]
        if award["lost_to_cap"]:
            result.setdefault("storm_spoils_lost_to_cap", []).append({
                "from_lord": "stronghold", "lost": award["lost_to_cap"],
            })
    if recipients and ctx["veche_coin"]:
        award = distribute_spoils(state, recipients, {"coin": ctx["veche_coin"]}, plan)
        result["veche_coin_distribution"] = award["added"]


def _resolve_reward(
    state: GameState, decision: PendingDecision, options: dict[str, Any], args: dict[str, Any],
    result: dict[str, Any],
) -> None:
    from nevsky.actions import IllegalAction
    from nevsky.battle import award_spoils

    ctx = decision.context
    if ctx["reward"] == "ransom":
        if set(args) - {"recipient"} or (
            "recipient" in args and not isinstance(args["recipient"], str)
        ):
            raise IllegalAction("bad_recipient", "Ransom requires a recipient Lord ID")
        receipt = _award_ransom(state, ctx["victim"], ctx["coin"], options["recipients"],
                                args.get("recipient"))
        result.setdefault("ransom", []).append(receipt)
    elif ctx["reward"] == "storm_spoils":
        _award_storm_spoils(state, ctx, result)
    else:
        if set(args) - {"allocation"}:
            raise IllegalAction("bad_spoils_allocation", "choose Sally Spoils with allocation")
        allocation = ctx["allocation"]
        if "allocation" in args:
            allocation = _validate_allocation(
                args["allocation"], options["recipients"], options["pool"], options["capacity"])
        captured = ctx["captured"]
        receipts = list(captured)
        for index in ctx.get("award_order") or range(len(captured)):
            receipts[index] = award_spoils(
                state, options["recipients"], captured[index], allocation,
            )
        result["spoils"] = receipts
    state.pending_decisions.remove(decision)


def settle_rewards(state: GameState, result: dict[str, Any]) -> None:
    """Settle forced awards, or hand off to the owner before the next action."""
    while (decision := pending_reward(state)) is not None:
        options = _reward_options(state, decision)
        if not state.meta.game_over and _needs_choice(decision, options):
            decision.context["resume_side"] = state.meta.active_player
            state.meta.active_player = decision.owed_by
            result["awaiting_aftermath_reward"] = {
                "owed_by": decision.owed_by, "reward": options["reward"],
            }
            return
        _resolve_reward(state, decision, options, {}, result)


def allocate_aftermath_reward(
    state: GameState, side: str, args: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    from nevsky.actions import IllegalAction

    decision = pending_reward(state)
    if decision is None:
        raise IllegalAction("no_aftermath_reward", "no aftermath reward is pending")
    if decision.owed_by != side or state.meta.active_player != side:
        raise IllegalAction("wrong_actor", f"aftermath reward is owed by {decision.owed_by}")
    result: dict[str, Any] = {}
    _resolve_reward(state, decision, _reward_options(state, decision), args, result)
    state.meta.active_player = decision.context["resume_side"]
    return result, []


def reward_moves(state: GameState, decision: PendingDecision) -> list[dict[str, Any]]:
    options = _reward_options(state, decision)
    base = {"type": REWARD_ACTION, "side": decision.owed_by}
    if options["reward"] == "ransom":
        return [{**base, "args": {"recipient": lid}, "reward": options,
                 "note": f"Give Ransom for {options['removed']} to {lid}"}
                for lid in options["recipients"]]
    return [{**base, "args": {}, "reward": options,
             "allocation_template": {"allocation": {"<lord_id>": {"<asset>": "<count>"}}},
             "note": "Allocate Sally Spoils among surviving Lords, or use the default split"}]
