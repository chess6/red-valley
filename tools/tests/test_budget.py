#!/usr/bin/env python3
"""Tests for the vast.ai spend guard.

The account auto-refills below $5, so a guard that is wrong in the permissive
direction costs real money. The API is stubbed out here: these tests are about
the arithmetic and the verdicts, and they must never touch the network.

Run:  python3 tools/tests/test_budget.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "assetgen"))

import budget  # noqa: E402


def running(instance_id=1, dph=1.20, storage=0.10):
    return {
        "id": instance_id,
        "actual_status": "running",
        "dph_total": dph,
        "storage_total_cost": storage,
    }


def stopped(instance_id=2, storage=0.10):
    return {
        "id": instance_id,
        "actual_status": "exited",
        "dph_total": 0.0,
        "storage_total_cost": storage,
    }


class BudgetTestCase(unittest.TestCase):
    def situation(self, balance, instances):
        return mock.patch.multiple(
            budget,
            fetch_balance=mock.Mock(return_value=balance),
            fetch_instances=mock.Mock(return_value=instances),
        )


class TestStopLine(BudgetTestCase):
    def test_default_stop_line_sits_above_the_refill_trigger(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(budget.stop_line(), 6.00)

    def test_floor_may_be_raised(self):
        with mock.patch.dict("os.environ", {"RV_VAST_FLOOR_USD": "20"}, clear=True):
            self.assertEqual(budget.stop_line(), 21.00)

    def test_floor_may_not_be_lowered_below_the_refill_trigger(self):
        with mock.patch.dict("os.environ", {"RV_VAST_FLOOR_USD": "1"}, clear=True):
            with self.assertRaises(budget.BudgetError):
                budget.stop_line()

    def test_reserve_may_not_be_shrunk(self):
        with mock.patch.dict("os.environ", {"RV_VAST_RESERVE_USD": "0"}, clear=True):
            self.assertEqual(budget.stop_line(), 6.00)

    def test_nonsense_floor_is_an_error_not_a_default(self):
        with mock.patch.dict("os.environ", {"RV_VAST_FLOOR_USD": "cheap"}, clear=True):
            with self.assertRaises(budget.BudgetError):
                budget.stop_line()


class TestAssess(BudgetTestCase):
    def test_healthy_position_is_safe(self):
        with self.situation(13.00, [running(dph=1.19)]):
            result = budget.assess()
        self.assertTrue(result.safe)
        self.assertAlmostEqual(result.headroom, 7.00, places=2)
        self.assertAlmostEqual(result.runway_hours, 7.00 / 1.19, places=2)

    def test_balance_at_the_stop_line_is_a_breach(self):
        with self.situation(6.00, [running()]):
            result = budget.assess()
        self.assertFalse(result.safe)
        self.assertTrue(any("stop line" in b for b in result.breaches))

    def test_balance_between_floor_and_stop_line_is_a_breach(self):
        # The reserve exists so that compute stops BEFORE the wall, not on it.
        with self.situation(5.50, [running()]):
            result = budget.assess()
        self.assertFalse(result.safe)

    def test_minutes_of_runway_is_a_breach_even_above_the_stop_line(self):
        # $6.10 is above the stop line, but at $1.20/h it is gone in 5 minutes.
        with self.situation(6.10, [running(dph=1.20)]):
            result = budget.assess()
        self.assertFalse(result.safe)
        self.assertTrue(any("runway" in b for b in result.breaches))

    def test_two_running_instances_is_a_violation(self):
        with self.situation(50.00, [running(1), running(2)]):
            result = budget.assess()
        self.assertFalse(result.safe)
        self.assertTrue(any("running at once" in v for v in result.violations))

    def test_idle_account_is_safe(self):
        with self.situation(6.50, []):
            result = budget.assess()
        self.assertTrue(result.safe)
        self.assertEqual(result.burn, 0.0)
        self.assertEqual(result.runway_hours, float("inf"))

    def test_empty_account_below_stop_line_still_breaches(self):
        # Nothing is burning, but nothing may be started either.
        with self.situation(4.00, []):
            result = budget.assess()
        self.assertFalse(result.safe)


class TestParkedStorage(BudgetTestCase):
    """One stopped instance is allowed -- if it is genuinely cheap to hold."""

    def test_one_cheap_parked_instance_is_allowed(self):
        with self.situation(20.00, [stopped(storage=0.01)]):
            result = budget.assess()
        self.assertTrue(result.safe)
        self.assertTrue(any("parked storage" in n for n in result.notes))

    def test_two_parked_instances_is_a_violation(self):
        with self.situation(50.00, [stopped(2, 0.01), stopped(3, 0.01)]):
            result = budget.assess()
        self.assertFalse(result.safe)
        self.assertTrue(any("at most one may be parked" in v for v in result.violations))

    def test_expensive_parked_storage_is_a_violation(self):
        # 300 GB at $0.10/h is $2.40/day: with $7 of headroom that is a
        # three-day fuse, not "storage costs relatively very little".
        with self.situation(13.00, [stopped(storage=0.10)]):
            result = budget.assess(min_hold_hours=72.0)
        self.assertFalse(result.safe)
        self.assertTrue(any("destroy it instead" in v for v in result.violations))

    def test_parked_storage_counts_against_the_floor(self):
        with self.situation(6.20, [stopped(storage=0.10)]):
            result = budget.assess()
        self.assertFalse(result.safe)


class TestPreflight(BudgetTestCase):
    def test_affordable_run_on_an_idle_account_passes(self):
        with self.situation(13.00, []):
            result = budget.preflight(hours=5, dph=1.19)
        self.assertTrue(result.safe)

    def test_run_that_would_cross_the_stop_line_is_refused(self):
        with self.situation(13.00, []):
            result = budget.preflight(hours=20, dph=1.19)
        self.assertFalse(result.safe)
        self.assertTrue(any("below the $6.00 stop line" in v for v in result.violations))

    def test_refusal_reports_the_affordable_budget(self):
        with self.situation(13.00, []):
            result = budget.preflight(hours=20, dph=1.19)
        # ($13.00 - $6.00) / $1.19 = 5.9h
        self.assertTrue(any("5.9h" in v for v in result.violations))

    def test_second_concurrent_instance_is_refused(self):
        with self.situation(500.00, [running()]):
            result = budget.preflight(hours=1, dph=1.19)
        self.assertFalse(result.safe)
        self.assertTrue(any("already running" in v for v in result.violations))

    def test_parked_storage_is_charged_against_a_proposed_run(self):
        # Differential: the same run, the same balance, the only difference
        # being a parked disk billing alongside it.
        with self.situation(12.00, []):
            alone = budget.preflight(hours=5, dph=1.10)
        self.assertTrue(alone.safe, "5h at $1.10 fits in $12.00 on its own")

        with self.situation(12.00, [stopped(storage=0.20)]):
            with_disk = budget.preflight(hours=5, dph=1.10)
        self.assertFalse(with_disk.safe)
        self.assertTrue(any("below the $6.00 stop line" in v for v in with_disk.violations))

    def test_the_stop_line_itself_is_the_last_acceptable_landing(self):
        # $12.00 balance, 5h at $1.20 = $6.00 spend, leaving exactly $6.00.
        # That is allowed: the $1.00 reserve above the $5.00 wall is precisely
        # what absorbs billing lag. A cent worse is not.
        with self.situation(12.00, []):
            self.assertTrue(budget.preflight(hours=5, dph=1.20).safe)
        with self.situation(11.99, []):
            self.assertFalse(budget.preflight(hours=5, dph=1.20).safe)


class TestFailClosed(BudgetTestCase):
    def test_unreadable_balance_is_an_error_not_a_pass(self):
        with mock.patch.object(budget, "fetch_balance", side_effect=budget.BudgetError("api down")):
            with self.assertRaises(budget.BudgetError):
                budget.assess()

    def test_cli_returns_2_when_it_cannot_determine(self):
        with mock.patch.object(budget, "fetch_balance", side_effect=budget.BudgetError("api down")):
            self.assertEqual(budget.main(["assess"]), 2)

    def test_cli_returns_1_on_breach(self):
        with self.situation(2.00, [running()]):
            self.assertEqual(budget.main(["assess"]), 1)

    def test_cli_returns_0_when_safe(self):
        with self.situation(30.00, []):
            self.assertEqual(budget.main(["assess"]), 0)

    def test_cli_preflight_refusal_is_nonzero(self):
        with self.situation(13.00, []):
            self.assertEqual(budget.main(["preflight", "--hours", "20", "--dph", "1.19"]), 1)


class TestInstanceAccounting(unittest.TestCase):
    def test_stopped_instance_still_bills_storage(self):
        self.assertEqual(budget.live_dph(stopped(storage=0.10)), 0.10)

    def test_running_instance_bills_the_total_rate(self):
        self.assertEqual(budget.live_dph(running(dph=1.19, storage=0.10)), 1.19)

    def test_missing_cost_fields_read_as_zero_not_crash(self):
        self.assertEqual(budget.live_dph({"actual_status": "running"}), 0.0)
        self.assertEqual(budget.storage_dph({"actual_status": "exited"}), 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
