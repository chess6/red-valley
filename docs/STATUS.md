# Status

A current-state snapshot — overwrite stale sections as things change,
don't append a changelog here. Full history is in `git log`.

## Where things stand

Two rounds of independent review (one general audit, one focused
gameplay-logic audit) have been fixed and pushed to `main`:

- **Forecast was an oracle.** Fixed twice — the first fix (banded ranges)
  still had a residual 100%-certain top end; the second replaced it with a
  continuous noisy model. `test_weather_variety_and_forecast` now checks
  both directions (confident warnings sometimes bust, quiet nights
  sometimes bite) over a 3000-day sample, and `test_documented_demo_seed`
  pins the specific advertised seed's arc so it can't silently break again
  — it already broke once, from an unrelated RNG-ordering fix.
- **Night didn't actually block field work** in most cases, and had a
  midnight–05:30 gap. Fixed: `_blocked_by_night` now gates every field
  action except covering (frost response is deliberately allowed at
  night) on the single correct `Game.is_night()` check.
- **Targeting used the character's movement-facing direction**, not the
  camera, so mouse-look didn't steer interaction. Fixed: real raycast from
  the camera's view direction.
- **Starting covers matched starting crops 1:1** (plus spare money for
  more), so the frost dilemma the game is built around was skippable.
  Tightened starting inventory, and capped Sarah's help to once/day with
  2 spare covers (previously farmable to 4+ free covers in ~16 game-minutes
  of watering, which fully undid the scarcity).
- **Early-harvest-at-half-value** (documented in the README, missing from
  code) implemented — grown-but-unripe crops can be salvaged via a
  confirm-by-pressing-twice gesture, restricted to the player's own plots
  (doing it to Sarah's would destroy her yield while still crediting the
  player a "help" favour — caught and fixed same round).

Test count: 47 unit + 33 integration, all passing as of `a5ee03e`.

Demo seed is now `11361` (was `1337` — changed when the RNG-ordering fix
reshuffled every seed's outcome). `RED_VALLEY_SEED=11361` gives calm days
1–3, a −4.9 °C frost night on day 4 (warned at 78%), then rain / heavy
rain / rain to test the clay field.

## Known problem — not yet fixed

**The working day is not actually finite**, which is the game's central
pitch ("A working day is finite; that's the whole game" — README). Measured
against the real 20-plot player farm and the 15-hour wake-to-collapse
window:

| action                  | time    | % of usable day |
|--------------------------|---------|------------------|
| water every plot          | 160 min | 18%              |
| cover every plot           | 360 min | 40%              |
| water *and* cover every plot | 520 min | 58%           |

A player can do literally everything with 6+ hours to spare; walking costs
are negligible (~7 sec of walking per action). This isn't fixed because
it's a balance decision with real gameplay consequences (candidates: cut
the workable window, raise action costs, shrink the farm), not something to
make unilaterally. See `CLAUDE.md` → "the day must stay genuinely finite"
for the constraint this needs to satisfy once addressed.

## Scaffold

`CLAUDE.md`, `docs/SETUP.md`, `docs/STATUS.md` (this file),
`.claude/settings.json` (shared permissions, committed),
`tools/doctor.sh`, `tools/verify.sh`. Blender MCP was already configured
and connected (`.mcp.json`, local `blender_mcp` clone) — not re-set-up,
just documented. `.claude/settings.local.json` is personal and gitignored.

Reviewed after the fact; three fixes applied:

- `verify.sh` used `git checkout -- project.godot` to undo the Godot
  rewrite quirk, which resets to HEAD and so would have **destroyed any
  intentional uncommitted edits** to that file — silently, since
  `tools/verify.sh` is on the auto-allow list. It now snapshots the exact
  bytes before the run and restores those, preserving uncommitted work.
- `CLAUDE.md` instructed Claude to run `/doctor`, `/context`, `/mcp`,
  `/permissions`. Those are human-only CLI commands; Claude cannot invoke
  them. Reworded as a human-facing note, with `tools/doctor.sh` as the
  part Claude can actually run.
- `.claude/settings.json` auto-approved `Bash(find .*)` and
  `Bash(sed -n *)`, which cover `find . -delete`, `find . -exec rm ...`,
  and `sed -n -i` — destructive commands needing no shell metacharacters.
  Both removed. The allowlist now only holds commands with no
  self-contained write capability. Discarding-type git commands moved from
  hard `deny` to `ask` so they prompt rather than being impossible (a hard
  deny contradicted the recovery step documented in `CLAUDE.md`).

## Next task

Decide and implement the day-length fix above (see options in that
section), then re-verify the labor-budget math actually binds and re-run
`tools/verify.sh`.
