#!/usr/bin/env python3
"""Atomic Vast.ai instance provisioning.

`vastai create` can report ``success: false`` and still leave a live contract
behind -- and it can leave *two*. The first pilot lost $0.58 to an orphan that
billed for half an hour because only the ID in the create response was ever
recorded, and the spend guard then refused (correctly) because two instances
were active at once.

So this module never trusts the create response. It diffs the account's
instance list around the call:

  1. take a local flock, so two `up` runs cannot interleave
  2. refuse to start if anything is already active (running OR loading)
  3. snapshot every existing instance ID
  4. arm the account-wide watchdog BEFORE creating anything
  5. call create, ignoring whatever it claims
  6. poll for new IDs, with a settle window so a late second contract is seen
  7. exactly one new  -> adopt it, recording the ID atomically
     zero new         -> abort
     two or more new  -> destroy every new contract and abort; never guess
  8. on any exception or signal, destroy everything this invocation created

`reconcile()` re-runs the "exactly one, and it is ours" check; call it before
installation and again before inference.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
STATE = ROOT / "tools" / "assetgen" / ".state"
LOCK = STATE / "provision.lock"
IDFILE = STATE / "instance_id"
VAST = ROOT / "tools" / "assetgen" / ".venv" / "bin" / "vastai"

ACTIVE = {"running", "loading", "created", "starting"}
APPEAR_TIMEOUT = 180.0   # a contract can take a while to show up in the list
SETTLE_SECONDS = 25.0    # after the first new ID, keep watching for a second
POLL_SECONDS = 5.0


class ProvisionError(RuntimeError):
    pass


def state_of(inst: dict) -> str:
    return (inst.get("actual_status") or inst.get("cur_state") or "").lower()


def is_active(inst: dict) -> bool:
    return state_of(inst) in ACTIVE


class VastCLI:
    """Real client. Tests substitute a fake with the same three methods."""

    def list_instances(self) -> list[dict]:
        out = subprocess.run([str(VAST), "show", "instances", "--raw"],
                             capture_output=True, text=True, timeout=120)
        if out.returncode != 0:
            raise ProvisionError(f"could not list instances: {out.stderr[:200]}")
        try:
            return json.loads(out.stdout or "[]")
        except json.JSONDecodeError as exc:
            raise ProvisionError(f"unparseable instance list: {exc}") from exc

    def create(self, offer: str, image: str, disk: int) -> dict:
        out = subprocess.run(
            [str(VAST), "create", "instance", str(offer), "--image", image,
             "--disk", str(disk), "--ssh", "--direct",
             "--env", "-e HF_HOME=/workspace/hf -e TORCH_HOME=/workspace/torch",
             "--onstart-cmd", "touch /workspace/.rv_booted", "--raw"],
            capture_output=True, text=True, timeout=300)
        try:
            return json.loads(out.stdout or "{}")
        except json.JSONDecodeError:
            return {"success": False, "raw": out.stdout[:200]}

    def destroy(self, instance_id) -> bool:
        out = subprocess.run([str(VAST), "destroy", "instance", str(instance_id)],
                             input="y\n", capture_output=True, text=True, timeout=120)
        return out.returncode == 0


@dataclass
class Provisioned:
    instance_id: str
    created: list[str] = field(default_factory=list)
    destroyed: list[str] = field(default_factory=list)


def _ids(instances: list[dict]) -> set[str]:
    return {str(i.get("id")) for i in instances if i.get("id") is not None}


def _adopt(instance_id: str) -> None:
    """Record the ID atomically: a half-written id file is worse than none."""
    STATE.mkdir(parents=True, exist_ok=True)
    tmp = IDFILE.with_suffix(".tmp")
    tmp.write_text(str(instance_id))
    os.replace(tmp, IDFILE)


def provision(offer: str, image: str, disk: int, *, client=None,
              sleep=time.sleep, now=time.monotonic,
              appear_timeout: float = APPEAR_TIMEOUT,
              settle: float = SETTLE_SECONDS,
              on_armed=None) -> Provisioned:
    client = client or VastCLI()
    created: list[str] = []

    def cleanup(reason: str) -> list[str]:
        """Destroy everything this invocation created. Never leave an orphan."""
        gone, stuck = [], []
        for cid in created:
            try:
                ok = client.destroy(cid)
            except Exception:
                ok = False
            (gone if ok else stuck).append(cid)
        if stuck:
            raise ProvisionError(
                f"{reason}; FAILED TO DESTROY {stuck} — these are still billing, "
                f"destroy them by hand: vastai destroy instance {' '.join(stuck)}")
        return gone

    installed = {}

    def on_signal(signum, _frame):
        cleanup(f"received signal {signum}")
        raise SystemExit(130)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            installed[sig] = signal.signal(sig, on_signal)
        except (ValueError, OSError):
            pass  # not in the main thread (tests)

    try:
        # 2. nothing may already be active
        before_list = client.list_instances()
        already = [i for i in before_list if is_active(i)]
        if already:
            raise ProvisionError(
                f"refusing to create: {len(already)} instance(s) already active "
                f"({[i.get('id') for i in already]}). Destroy them first.")
        before = _ids(before_list)

        # 4. arm the watchdog BEFORE anything can be created
        if on_armed:
            on_armed(before)

        # 5. create, and disregard what it claims
        try:
            client.create(offer, image, disk)
        except Exception as exc:  # the contract may exist anyway
            cleanup(f"create raised {exc!r}")
            raise

        # 6. diff the account, allowing for delayed appearance
        deadline = now() + appear_timeout
        first_seen_at = None
        new: set[str] = set()
        while True:
            current = _ids(client.list_instances())
            new = current - before
            created[:] = sorted(new)
            if new and first_seen_at is None:
                first_seen_at = now()
            # keep watching briefly after the first, to catch a late sibling
            if first_seen_at is not None and now() - first_seen_at >= settle:
                break
            if first_seen_at is None and now() >= deadline:
                break
            sleep(POLL_SECONDS)

        # 7. decide
        if len(new) == 1:
            adopted = next(iter(new))
            _adopt(adopted)
            return Provisioned(instance_id=adopted, created=sorted(new))
        if not new:
            raise ProvisionError(
                f"create produced no contract within {appear_timeout:.0f}s — aborting")
        gone = cleanup(f"create produced {len(new)} contracts {sorted(new)}")
        raise ProvisionError(
            f"create produced {len(new)} contracts {sorted(new)}; destroyed {gone}. "
            "Refusing to guess which to keep.")
    except ProvisionError:
        raise
    except BaseException as exc:
        cleanup(f"unexpected {exc!r}")
        raise
    finally:
        for sig, prev in installed.items():
            try:
                signal.signal(sig, prev)
            except (ValueError, OSError):
                pass


def reconcile(expected_id: str, *, client=None) -> list[dict]:
    """Assert the account holds exactly our instance and nothing else active."""
    client = client or VastCLI()
    instances = client.list_instances()
    active = [i for i in instances if is_active(i)]
    ids = sorted(str(i.get("id")) for i in active)
    if ids != [str(expected_id)]:
        raise ProvisionError(
            f"reconcile failed: expected exactly [{expected_id}] active, found {ids}")
    return active


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Atomic vast.ai provisioning")
    sub = ap.add_subparsers(dest="cmd", required=True)
    up = sub.add_parser("up")
    up.add_argument("offer")
    up.add_argument("--image", default="pytorch/pytorch:2.5.1-cuda12.4-cudnn9-devel")
    up.add_argument("--disk", type=int, default=200)
    up.add_argument("--hours", type=float, default=2.0)
    rec = sub.add_parser("reconcile")
    rec.add_argument("--id", default=None)
    args = ap.parse_args(argv)

    STATE.mkdir(parents=True, exist_ok=True)
    if args.cmd == "reconcile":
        try:
            wanted = args.id or IDFILE.read_text().strip()
            reconcile(wanted)
        except (ProvisionError, OSError) as exc:
            print(f"RECONCILE FAILED: {exc}", file=sys.stderr)
            return 1
        print(f"reconcile ok: exactly {wanted} active")
        return 0

    # 1. flock: two `up` runs must never interleave
    lock = open(LOCK, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("another provision is already running (lock held) — aborting", file=sys.stderr)
        return 2

    watchdog = []

    def arm(_before):
        wd = ROOT / "tools" / "assetgen" / "watchdog.sh"
        proc = subprocess.Popen(["setsid", str(wd), "ACCOUNT", str(args.hours)],
                                stdout=open(STATE / "logs" / "wd_account.log", "a"),
                                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        watchdog.append(proc)
        print(f"watchdog armed before create (pid {proc.pid}, {args.hours}h)")

    try:
        result = provision(args.offer, args.image, args.disk, on_armed=arm)
    except ProvisionError as exc:
        print(f"PROVISION FAILED: {exc}", file=sys.stderr)
        return 1
    print(f"adopted instance {result.instance_id}")
    (STATE / "started_at").write_text(str(int(time.time())))
    (STATE / "budget_hours").write_text(str(args.hours))
    print(f"INSTANCE_ID={result.instance_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
