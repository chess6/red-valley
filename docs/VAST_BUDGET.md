# Paid compute: the $5 floor

This account **auto-refills when the balance drops below $5**. That makes $5 a
wall rather than a budget: reaching it does not stop the work, it charges the
card. The rule follows directly — while any agent-driven compute is running,
the projected balance must never reach it.

Compute stops at **$6**, not $5:

| | |
|---|---|
| **floor** | **$5.00** — the auto-refill trigger. Hard. `RV_VAST_FLOOR_USD` may raise it, never lower it. |
| **reserve** | **$1.00** — billing lag, bandwidth, rounding. |
| **stop line** | **$6.00** — the number every check is written against. |

## Project, don't observe

The guard works on projected balance. A $8 balance with a $1.20/h GPU and six
hours left on the clock is already a breach: that money is committed, it just
has not left the account yet. Checking the current balance and feeling
reassured is the failure mode this exists to prevent.

Runway is the useful number: `(balance − stop line) ÷ burn rate`. When it
drops under 15 minutes the guard destroys rather than coasting into the wall,
because there is no useful work left in that window anyway.

## Storage is not free, and this is the part that surprises people

`dph_total` splits into two parts. For the instance this pilot has been using:

```
dph_base            $1.089/h   the GPU — stops when the instance stops
storage_total_cost  $0.100/h   the 300 GB disk — bills until the instance is DESTROYED
dph_total           $1.189/h
```

**A stopped instance still costs $0.10/h — $2.40/day, about $72/month.** So
"offline storage is fine, it costs relatively very little" holds only for
small disks. At 300 GB it burns through $7 of headroom in three days, with
nothing running and nobody watching.

The guard therefore treats a parked instance as a live cost:

- at most **one** stopped instance may be parked;
- it must be affordable to hold for **72 hours** without reaching the stop
  line, otherwise it is a slow leak and should be **destroyed, not stopped**;
- its burn is charged against any new run proposed alongside it.

Destroying ends all billing. Stopping does not. When in doubt, destroy — the
generation pipeline can be re-provisioned, and re-downloading weights costs
less than a week of idle disk.

## What enforces this

`tools/assetgen/budget.py` — the arithmetic and the verdicts. Exit codes are
`0` safe, `1` refused or breached, `2` could not determine. **`2` is treated
as unsafe everywhere**: not knowing the balance while sitting next to a hard
floor is not a neutral state.

```bash
tools/assetgen/vast.sh guard                              # current position
python3 tools/assetgen/budget.py preflight --hours 6 --dph 1.19
python3 tools/assetgen/budget.py assess --json            # for scripts
```

`tools/assetgen/vast.sh up` refuses to create anything while the guard is
unhappy. Because this CLI version's `search offers 'id=…'` filter returns no
rows, an offer cannot be priced before it exists — so `up` prices the instance
the moment it is created and **destroys it immediately** if it cannot finish
its budget above the stop line. That costs seconds of billing instead of
hours.

`tools/assetgen/watchdog.sh` runs detached and destroys the instance when
**either** limit is hit: the time budget expires, or the spend guard breaches.
The second limit is the one that matters when an estimate was wrong — a time
budget only bounds cost if the hourly rate is what you assumed, while the
balance check bounds it whatever the rate turns out to be, and catches
spending this pilot knows nothing about. If the guard is unreadable for 20
minutes it destroys anyway rather than fly blind next to the floor.

`tools/tests/test_budget.py` covers the arithmetic with the API stubbed, in
both directions — affordable runs pass, and each way of reaching the wall is
refused.

## What an agent must never do

Never widen a limit to make a job fit: not the watchdog budget, not the floor,
not the instance count. If it does not fit, it does not run — say so and stop.

Never top up the balance, change billing settings, or add a payment method.

Never call `vastai create` directly. Every guarantee above lives in the
wrapper; the raw CLI has none of it.
