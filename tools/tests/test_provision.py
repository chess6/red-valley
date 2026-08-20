"""Regression tests for atomic provisioning.

Each case is a failure mode that actually happened, or that would have cost
money if it had. The fake client lets us reproduce them deterministically:
`vastai create` reporting success:false while leaving a contract, leaving two,
a contract appearing late, two `up` runs overlapping, and a destroy that fails
during cleanup.
"""
import fcntl
import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
spec = importlib.util.spec_from_file_location(
    "provision", ROOT / "tools" / "assetgen" / "provision.py")
provision = importlib.util.module_from_spec(spec)
sys.modules["provision"] = provision
spec.loader.exec_module(provision)


def inst(i, status="running", dph=1.10):
    return {"id": i, "actual_status": status, "dph_total": dph}


class FakeVast:
    """Scriptable stand-in for the vastai CLI.

    `appears` is a list of (poll_index, instance) — the contract becomes
    visible only from that poll onward, which is how delayed appearance and
    late siblings are modelled.
    """

    def __init__(self, existing=(), appears=(), create_result=None,
                 undestroyable=()):
        self.instances = list(existing)
        self.appears = list(appears)
        self.create_result = create_result or {"success": False}
        self.undestroyable = set(str(x) for x in undestroyable)
        self.polls = 0
        self.created_called = 0
        self.destroyed = []

    def list_instances(self):
        snapshot = list(self.instances)
        for when, obj in self.appears:
            if self.polls >= when:
                snapshot.append(obj)
        self.polls += 1
        return snapshot

    def create(self, offer, image, disk):
        self.created_called += 1
        return self.create_result

    def destroy(self, instance_id):
        if str(instance_id) in self.undestroyable:
            return False
        self.destroyed.append(str(instance_id))
        self.appears = [(w, o) for (w, o) in self.appears
                        if str(o.get("id")) != str(instance_id)]
        self.instances = [o for o in self.instances
                          if str(o.get("id")) != str(instance_id)]
        return True


class ProvisionTest(unittest.TestCase):
    def setUp(self):
        self.adopted = []
        self._real_adopt = provision._adopt
        provision._adopt = lambda i: self.adopted.append(str(i))

    def tearDown(self):
        provision._adopt = self._real_adopt

    def run_provision(self, fake, **kw):
        clock = {"t": 0.0}

        def now():
            return clock["t"]

        def sleep(sec):
            clock["t"] += sec

        return provision.provision("offer", "img", 200, client=fake,
                                   sleep=sleep, now=now, **kw)

    # ---------------------------------------------------------------- cases
    def test_success_false_with_one_contract_is_adopted(self):
        """The real incident: create says it failed, but a contract exists."""
        fake = FakeVast(appears=[(1, inst(48070721))],
                        create_result={"success": False, "new_contract": None})
        result = self.run_provision(fake)
        self.assertEqual(result.instance_id, "48070721")
        self.assertEqual(self.adopted, ["48070721"])
        self.assertEqual(fake.destroyed, [])

    def test_two_contracts_are_both_destroyed_and_abort(self):
        """Never guess which to keep -- that is how an orphan bills for hours."""
        fake = FakeVast(appears=[(1, inst(48070660)), (1, inst(48070721))])
        with self.assertRaises(provision.ProvisionError) as ctx:
            self.run_provision(fake)
        self.assertIn("2 contracts", str(ctx.exception))
        self.assertEqual(sorted(fake.destroyed), ["48070660", "48070721"])
        self.assertEqual(self.adopted, [])

    def test_late_sibling_within_settle_window_is_caught(self):
        """A second contract that shows up a few polls later must not be missed."""
        fake = FakeVast(appears=[(1, inst(1001)), (3, inst(1002))])
        with self.assertRaises(provision.ProvisionError):
            self.run_provision(fake, settle=30.0)
        self.assertEqual(sorted(fake.destroyed), ["1001", "1002"])
        self.assertEqual(self.adopted, [])

    def test_delayed_appearance_is_still_adopted(self):
        """Contract visible only after several polls -- adopt, do not abort."""
        fake = FakeVast(appears=[(5, inst(2002))])
        result = self.run_provision(fake, appear_timeout=120.0)
        self.assertEqual(result.instance_id, "2002")
        self.assertEqual(self.adopted, ["2002"])

    def test_no_contract_aborts(self):
        fake = FakeVast()
        with self.assertRaises(provision.ProvisionError) as ctx:
            self.run_provision(fake, appear_timeout=30.0)
        self.assertIn("no contract", str(ctx.exception))
        self.assertEqual(self.adopted, [])

    def test_refuses_when_something_is_already_active(self):
        fake = FakeVast(existing=[inst(9001, "running")])
        with self.assertRaises(provision.ProvisionError) as ctx:
            self.run_provision(fake)
        self.assertIn("already active", str(ctx.exception))
        self.assertEqual(fake.created_called, 0, "must not create a second instance")

    def test_loading_instance_counts_as_active(self):
        """`loading` bills at the hourly rate; it must block a new rental."""
        fake = FakeVast(existing=[inst(9002, "loading")])
        with self.assertRaises(provision.ProvisionError):
            self.run_provision(fake)
        self.assertEqual(fake.created_called, 0)

    def test_cleanup_failure_is_loud_and_names_the_orphans(self):
        """If destroy fails we must say so plainly -- money is still leaking."""
        fake = FakeVast(appears=[(1, inst(3001)), (1, inst(3002))],
                        undestroyable=["3002"])
        with self.assertRaises(provision.ProvisionError) as ctx:
            self.run_provision(fake)
        msg = str(ctx.exception)
        self.assertIn("FAILED TO DESTROY", msg)
        self.assertIn("3002", msg)
        self.assertIn("still billing", msg)
        self.assertEqual(self.adopted, [])

    def test_watchdog_is_armed_before_create(self):
        order = []
        fake = FakeVast(appears=[(1, inst(4004))])
        real_create = fake.create

        def spy_create(*a, **k):
            order.append("create")
            return real_create(*a, **k)

        fake.create = spy_create
        self.run_provision(fake, on_armed=lambda before: order.append("armed"))
        self.assertEqual(order[:2], ["armed", "create"],
                         "watchdog must exist before any contract can")

    # ---------------------------------------------------------------- lock
    def test_overlapping_invocations_are_refused_by_the_lock(self):
        provision.STATE.mkdir(parents=True, exist_ok=True)
        holder = open(provision.LOCK, "w")
        fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            out = subprocess.run(
                [sys.executable, str(ROOT / "tools" / "assetgen" / "provision.py"),
                 "up", "12345"],
                capture_output=True, text=True, timeout=60)
            self.assertEqual(out.returncode, 2)
            self.assertIn("lock held", out.stderr)
        finally:
            fcntl.flock(holder, fcntl.LOCK_UN)
            holder.close()

    # ---------------------------------------------------------------- reconcile
    def test_reconcile_passes_for_exactly_our_instance(self):
        fake = FakeVast(existing=[inst(5005, "running")])
        self.assertEqual(len(provision.reconcile("5005", client=fake)), 1)

    def test_reconcile_fails_on_an_unexpected_extra(self):
        fake = FakeVast(existing=[inst(5005), inst(6006)])
        with self.assertRaises(provision.ProvisionError) as ctx:
            provision.reconcile("5005", client=fake)
        self.assertIn("expected exactly", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
