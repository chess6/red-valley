#!/usr/bin/env python3
"""Vast.ai spend guard: keep the account balance above the auto-refill floor.

Dropping below $5 on this account triggers an automatic top-up — an
involuntary charge. So $5 is not a budget, it is a wall, and the rule is that
no agent-driven compute may ever push the balance into it. Everything here
exists to make that mechanical rather than a matter of remembering.

The guard works on *projected* balance, not current balance. A balance of $8
with a $1.20/h GPU and six hours left on the clock is already a breach — the
money is spent, it just has not left the account yet.

Two numbers:
  floor    $5.00  the auto-refill trigger. Hard. May be raised, never lowered.
  reserve  $1.00  margin for billing lag, bandwidth and rounding.
  -> stop line = floor + reserve = $6.00. Compute stops here, not at $5.

Storage is the trap. A *stopped* instance still bills storage: this pilot's
300 GB disk costs about $0.10/h, which is $2.40/day whether or not anything is
running. "Offline storage is cheap" is only true for small disks, so stopped
instances are projected against the floor exactly like running ones.

Exit codes:  0 safe   1 refused / breach   2 could not determine (fail closed)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# The auto-refill trigger on this account. Lowering it would defeat the point,
# so the override can only move it up.
FLOOR_FLOOR_USD = 5.00
DEFAULT_RESERVE_USD = 1.00

# Destroy rather than coast into the wall: if less than this much runway
# remains, there is no useful work left to do anyway.
MIN_RUNWAY_HOURS = 0.25

# A stopped instance held for storage must be affordable for at least this
# long, otherwise it is not "parked", it is a slow leak.
DEFAULT_MIN_HOLD_HOURS = 72.0

VAST_BIN = Path(__file__).resolve().parent / ".venv" / "bin" / "vastai"


class BudgetError(Exception):
    """Could not determine the situation — always resolved as unsafe."""


def _floor() -> float:
    raw = os.environ.get("RV_VAST_FLOOR_USD")
    if not raw:
        return FLOOR_FLOOR_USD
    try:
        value = float(raw)
    except ValueError as exc:
        raise BudgetError(f"RV_VAST_FLOOR_USD={raw!r} is not a number") from exc
    if value < FLOOR_FLOOR_USD:
        raise BudgetError(
            f"RV_VAST_FLOOR_USD={value:.2f} is below the ${FLOOR_FLOOR_USD:.2f} "
            "auto-refill trigger; the floor may be raised, never lowered"
        )
    return value


def _reserve() -> float:
    raw = os.environ.get("RV_VAST_RESERVE_USD")
    if not raw:
        return DEFAULT_RESERVE_USD
    try:
        value = float(raw)
    except ValueError as exc:
        raise BudgetError(f"RV_VAST_RESERVE_USD={raw!r} is not a number") from exc
    return max(value, DEFAULT_RESERVE_USD)


def stop_line() -> float:
    return _floor() + _reserve()


# --------------------------------------------------------------------------
# vast api


def _vast(*args: str) -> object:
    if not VAST_BIN.exists():
        raise BudgetError(f"vastai CLI not found at {VAST_BIN}")
    try:
        proc = subprocess.run(
            [str(VAST_BIN), *args, "--raw"],
            capture_output=True,
            text=True,
            timeout=90,
        )
    except subprocess.TimeoutExpired as exc:
        raise BudgetError(f"vastai {' '.join(args)} timed out") from exc
    if proc.returncode != 0:
        raise BudgetError(f"vastai {' '.join(args)} failed: {proc.stderr.strip()[:200]}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise BudgetError(f"vastai {' '.join(args)} returned unparseable output") from exc


def fetch_balance() -> float:
    data = _vast("show", "user")
    if not isinstance(data, dict) or "credit" not in data:
        raise BudgetError("could not read account balance")
    return float(data["credit"])


def fetch_instances() -> list[dict]:
    data = _vast("show", "instances")
    if not isinstance(data, list):
        raise BudgetError("could not read instance list")
    return data


# --------------------------------------------------------------------------
# assessment


# States that bill at the full hourly rate. "loading" is included on purpose:
# an instance pulling its image is charged like a running one, and treating it
# as merely "stopped" understates burn and hides a second concurrent instance.
ACTIVE_STATES = {"running", "loading", "created", "starting"}


def _state(inst: dict) -> str:
    return (inst.get("actual_status") or inst.get("cur_state") or "").lower()


def is_running(inst: dict) -> bool:
    return _state(inst) == "running"


def is_active(inst: dict) -> bool:
    """Billing at the hourly rate right now, running or still coming up."""
    return _state(inst) in ACTIVE_STATES


def storage_dph(inst: dict) -> float:
    """What this instance bills even when stopped."""
    return float(inst.get("storage_total_cost") or 0.0)


def live_dph(inst: dict) -> float:
    """What this instance bills right now, in its current state."""
    if is_active(inst):
        return float(inst.get("dph_total") or 0.0)
    return storage_dph(inst)


@dataclass
class Assessment:
    balance: float
    stop_line: float
    running: list[dict] = field(default_factory=list)
    stopped: list[dict] = field(default_factory=list)
    breaches: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def burn(self) -> float:
        return sum(live_dph(i) for i in self.running + self.stopped)

    @property
    def headroom(self) -> float:
        return self.balance - self.stop_line

    @property
    def runway_hours(self) -> float:
        if self.burn <= 0:
            return float("inf")
        return self.headroom / self.burn

    @property
    def safe(self) -> bool:
        return not self.breaches and not self.violations

    def as_dict(self) -> dict:
        return {
            "balance": round(self.balance, 4),
            "stop_line": self.stop_line,
            "burn_per_hour": round(self.burn, 4),
            "headroom": round(self.headroom, 4),
            "runway_hours": None if self.runway_hours == float("inf") else round(self.runway_hours, 3),
            "running": [i.get("id") for i in self.running],
            "stopped": [i.get("id") for i in self.stopped],
            "breaches": self.breaches,
            "violations": self.violations,
            "notes": self.notes,
            "safe": self.safe,
        }


def assess(min_hold_hours: float = DEFAULT_MIN_HOLD_HOURS) -> Assessment:
    balance = fetch_balance()
    instances = fetch_instances()
    result = Assessment(balance=balance, stop_line=stop_line())
    for inst in instances:
        (result.running if is_active(inst) else result.stopped).append(inst)

    if balance <= result.stop_line:
        result.breaches.append(
            f"balance ${balance:.2f} is at or below the ${result.stop_line:.2f} stop line "
            f"(auto-refill triggers at ${_floor():.2f})"
        )

    if result.running and result.runway_hours <= MIN_RUNWAY_HOURS:
        result.breaches.append(
            f"only {result.runway_hours * 60:.0f} min of runway left at "
            f"${result.burn:.3f}/h before the stop line"
        )

    if len(result.running) > 1:
        result.violations.append(
            f"{len(result.running)} instances active at once (running or loading) "
            "— the projection assumes one, so cost cannot be bounded"
        )

    if len(result.stopped) > 1:
        result.violations.append(
            f"{len(result.stopped)} stopped instances are billing storage — at most one may be parked"
        )

    parked_burn = sum(storage_dph(i) for i in result.stopped)
    if parked_burn > 0 and not result.running:
        hold = result.headroom / parked_burn if parked_burn else float("inf")
        message = (
            f"parked storage costs ${parked_burn:.3f}/h (${parked_burn * 24:.2f}/day); "
            f"balance reaches the stop line in {hold:.0f}h"
        )
        if hold < min_hold_hours:
            result.violations.append(message + f" — under the {min_hold_hours:.0f}h minimum, destroy it instead")
        else:
            result.notes.append(message)

    if not instances:
        result.notes.append("no instances — nothing is billing")

    return result


def preflight(hours: float, dph: float, min_hold_hours: float = DEFAULT_MIN_HOLD_HOURS) -> Assessment:
    """Can a new instance at `dph` run for `hours` without reaching the wall?"""
    result = assess(min_hold_hours)

    if result.running:
        result.violations.append(
            f"instance {result.running[0].get('id')} is already running — "
            "stop or destroy it before starting another"
        )

    existing = sum(live_dph(i) for i in result.stopped)
    projected = (dph + existing) * hours
    remaining = result.balance - projected

    if remaining < result.stop_line:
        affordable = (result.balance - result.stop_line) / (dph + existing) if (dph + existing) else float("inf")
        result.violations.append(
            f"${dph:.3f}/h for {hours:g}h projects to ${projected:.2f}, leaving "
            f"${remaining:.2f} — below the ${result.stop_line:.2f} stop line. "
            f"Affordable budget here is {affordable:.1f}h."
        )
    else:
        result.notes.append(
            f"projected spend ${projected:.2f} over {hours:g}h leaves "
            f"${remaining:.2f}, clear of the ${result.stop_line:.2f} stop line"
        )
    return result


# --------------------------------------------------------------------------
# cli


def render(result: Assessment, title: str) -> None:
    runway = "unbounded" if result.runway_hours == float("inf") else f"{result.runway_hours:.2f}h"
    print(f"-- vast budget guard: {title}")
    print(f"   balance    ${result.balance:.2f}   stop line ${result.stop_line:.2f}   headroom ${result.headroom:.2f}")
    print(f"   burn       ${result.burn:.3f}/h   runway {runway}")
    print(f"   instances  {len(result.running)} running, {len(result.stopped)} stopped")
    for note in result.notes:
        print(f"   note: {note}")
    for violation in result.violations:
        print(f"   REFUSED: {violation}", file=sys.stderr)
    for breach in result.breaches:
        print(f"   BREACH: {breach}", file=sys.stderr)


def _add_global_flags(parser: argparse.ArgumentParser, *, suppress: bool) -> None:
    """Give `parser` its own copy of the flags that work on either side.

    `budget.py --json assess` and `budget.py assess --json` must both work: a
    caller that guesses wrong otherwise gets unparseable output, which is how
    the doc example in VAST_BUDGET.md shipped broken.

    Two details make it work. Each parser gets freshly constructed actions
    rather than shared ones, because argparse's set_defaults() mutates action
    objects in place -- with parents= the subparser and the main parser share
    those objects, so setting a default on one silently changes the other. And
    the subparser's defaults are SUPPRESS, so an absent flag leaves no key in
    the sub-namespace to overwrite what the main parser already parsed.
    """
    parser.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS if suppress else False,
        help="machine-readable output",
    )
    parser.add_argument(
        "--min-hold-hours",
        type=float,
        default=argparse.SUPPRESS if suppress else DEFAULT_MIN_HOLD_HOURS,
        help="minimum affordable hold time for a parked (stopped) instance",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Vast.ai spend guard.")
    _add_global_flags(parser, suppress=False)
    sub = parser.add_subparsers(dest="command", required=True)

    assess_p = sub.add_parser("assess", help="report the current position")

    pre = sub.add_parser("preflight", help="check a proposed run before creating it")
    pre.add_argument("--hours", type=float, required=True)
    pre.add_argument("--dph", type=float, required=True, help="dollars per hour of the proposed instance")

    post = sub.add_parser("postcheck", help="check a just-created instance against its budget")
    post.add_argument("--instance", required=True)
    post.add_argument("--hours", type=float, required=True)

    for subparser in (assess_p, pre, post):
        _add_global_flags(subparser, suppress=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        if args.command == "assess":
            result = assess(args.min_hold_hours)
            title = "current position"
        elif args.command == "preflight":
            result = preflight(args.hours, args.dph, args.min_hold_hours)
            title = f"proposed {args.hours:g}h at ${args.dph:.3f}/h"
        else:
            instances = fetch_instances()
            match = [i for i in instances if str(i.get("id")) == str(args.instance)]
            if not match:
                raise BudgetError(f"instance {args.instance} not found")
            dph = float(match[0].get("dph_total") or 0.0)
            # It already exists, so exclude it from the "already running" test
            # and ask only whether its remaining budget is affordable.
            balance = fetch_balance()
            others = sum(live_dph(i) for i in instances if str(i.get("id")) != str(args.instance))
            projected = (dph + others) * args.hours
            result = Assessment(balance=balance, stop_line=stop_line())
            result.running = [i for i in instances if is_running(i)]
            result.stopped = [i for i in instances if not is_running(i)]
            if balance - projected < result.stop_line:
                result.violations.append(
                    f"instance {args.instance} at ${dph:.3f}/h for {args.hours:g}h projects to "
                    f"${projected:.2f}, leaving ${balance - projected:.2f} — below the "
                    f"${result.stop_line:.2f} stop line. Destroy it now."
                )
            else:
                result.notes.append(
                    f"instance {args.instance} at ${dph:.3f}/h for {args.hours:g}h is affordable "
                    f"(${balance - projected:.2f} left at the deadline)"
                )
            title = f"instance {args.instance}"
    except BudgetError as exc:
        if args.json:
            print(json.dumps({"safe": False, "error": str(exc)}))
        else:
            print(f"-- vast budget guard: CANNOT DETERMINE — {exc}", file=sys.stderr)
            print("   Treating as unsafe: no compute may start, running compute must stop.", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result.as_dict()))
    else:
        render(result, title)
    return 0 if result.safe else 1


if __name__ == "__main__":
    sys.exit(main())
