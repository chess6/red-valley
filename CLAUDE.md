# Red Valley — project instructions

A 3D farming prototype about *thinking like a farmer* — reading land and
weather, making judgment calls under real time pressure — not performing
farming-themed chores. Full design writeup: `README.md`. Toolchain,
onboarding: `docs/SETUP.md`. Current milestone / known problems / what's
next: `docs/STATUS.md`.

## Toolchain (exact versions/paths — this machine)

- Godot **4.7**: `/opt/Godot4/Godot_v4.7-stable_linux.x86_64`
- Blender **5.1**: `/opt/blender/blender`
- Blender MCP is already configured in `.mcp.json` (a local clone at
  `~/tools/blender_mcp`, the blender.org-maintained MCP server — not the
  third-party `ahujasid/blender-mcp`). Verify it's live with `/mcp` before
  relying on it; it requires Blender running with the addon enabled.

## Commands

```bash
# run the game
/opt/Godot4/Godot_v4.7-stable_linux.x86_64 --path .

# unit tests (pure simulation logic, headless, no scene load)
/opt/Godot4/Godot_v4.7-stable_linux.x86_64 --headless --path . --script tests/run_tests.gd

# integration test (drives the real player/Sarah/world through the frost scenario)
/opt/Godot4/Godot_v4.7-stable_linux.x86_64 --headless --path . res://tests/integration.tscn

# regenerate all placeholder assets (writes assets/models/*.glb)
/opt/blender/blender --background --python tools/blender/gen_assets.py

# full verification — run before claiming ANY task complete
tools/verify.sh

# environment sanity check — run at the start of a session, or when something's off
tools/doctor.sh
```

Screenshot harness (headless dev tool): see `README.md` → "Dev screenshot
harness" for the full `RV_SHOT_*` env var list.

**Known Godot quirk:** simply running the Godot binary (even `--headless
--script`) can silently rewrite `project.godot` (re-serializes it, may drop
explicit settings). `tools/verify.sh` handles this: it snapshots the file's
exact bytes before running and restores them afterward if Godot changed it.
That restores your *pre-run* state, so uncommitted `project.godot` edits you
made on purpose are preserved — it does not reset to HEAD.

If you run Godot manually outside that script, check `git diff
project.godot` afterward and don't commit an unintended rewrite. Restore it
with `git checkout -- project.godot` **only** if you have no intentional
uncommitted changes in that file, since checkout discards them.

## Protected design thesis

The simulation is one small causal chain — **weather → soil → crop →
player-time** — with *no scripted events*. Nothing about a scene, a crop
pairing, or a dilemma is hand-authored; it all has to emerge from those four
systems' numbers. When changing gameplay:

- Don't add scripted/triggered story beats. If a situation needs to happen
  (e.g. "player must face a frost dilemma"), it has to emerge from tuning
  the weather model, starting inventory, or action costs — not from an
  `if day == 4: trigger_frost()` special case.
- **The forecast must never be an oracle.** No announced probability —
  however high or low — may deterministically predict the true outcome.
  This has broken twice already from innocent-looking refactors (see git
  history). `tests/run_tests.gd::test_weather_variety_and_forecast` guards
  it over a 3000-day sample in both directions (confident warnings must
  sometimes bust; quiet nights must sometimes bite). Don't weaken that test
  to make a change pass — fix the model instead.
- **The day must stay genuinely finite.** The whole design pitch is "a
  working day is finite; that's the whole game." Before changing action
  costs, farm size, the wake/collapse window, or starting inventory, check
  the labor-budget math actually binds (comfortably doing everything should
  NOT be possible) — this is not currently covered by an automated test, so
  reason about it by hand or write one.
- Any change to `WeatherModel`'s RNG consumption order (the sequence of
  `rng.randf*()` calls) reshuffles the outcome of every seed, including the
  demo seed. If you touch `src/sim/weather_model.gd`, re-run
  `test_documented_demo_seed` and re-pick `RED_VALLEY_SEED` in
  `src/autoload/weather.gd` + `README.md` if it fails — don't just delete
  or loosen the test.

## Architecture rules

- `src/sim/` is **pure simulation logic**: `RefCounted` classes, no `Node`/
  scene references, no autoload lookups, no `get_tree()`. It must stay
  headless-testable via `tests/run_tests.gd` with zero scene load. If new
  logic needs the engine (visuals, input, physics bodies), it belongs in
  `src/world/`, `src/player/`, `src/npc/`, or `src/ui/` instead — those may
  freely reference the engine and call into `src/sim/`.
- `src/autoload/` (Game, Weather, Farm) is the thin integration layer
  between the sim and the scene tree — clock, inventory, plot registry,
  the single per-tick loop. Keep simulation math out of it; it should only
  orchestrate calls into `src/sim/`.
- Never duplicate simulation math in scene/UI code as a shortcut — if a UI
  element needs a number, it should read it from `src/sim/`, not
  recompute an approximation.

## Testing requirements

- Any change to numerical simulation logic (`src/sim/*.gd`) needs a
  corresponding check added to `tests/run_tests.gd` in the same change —
  not a follow-up.
- Any change touching player/Sarah/world interaction (targeting, action
  gating, help mechanics, harvest rules) needs a corresponding check in
  `tests/integration.gd` where feasible.
- **Run `tools/verify.sh` before reporting any task as complete.** It runs
  both suites and absorbs the `project.godot` rewrite quirk. This is not
  optional — code that "should work" has broken the demo seed and the
  targeting raycast in this project before, silently, without it.

## Asset workflow (Blender)

- All placeholder assets are **generated by script** (`tools/blender/gen_assets.py`)
  — no manually authored or downloaded assets. This is a hard project
  constraint, not a preference.
- Never overwrite an approved/committed asset without preserving the
  previous export. If you're iterating on `gen_assets.py`, don't let a
  regenerate silently clobber a hand-tuned result — diff the output
  (triangle count, dimensions, a render) against the previous version
  before treating a regen as a drop-in replacement. If a source `.blend`
  exists for something (as opposed to pure-script generation), version it
  separately from the exported `.glb`.
- Every new or changed 3D asset must be verified, before considered done,
  with: **a viewport render** (screenshot), **triangle count**, **texture
  size(s)**, and a **successful Godot import** (the `.import` file
  generates with no errors — check by loading the scene or running
  `--headless --path . --quit` and inspecting for import errors).
- **Don't let high-fidelity work silently degrade to primitive geometry.**
  If a generation step for a detailed asset (especially the player/Sarah
  character models) fails partway and falls back to a placeholder cube or
  capsule, that failure must be surfaced loudly (raise/print/fail the
  script) — never let it pass silently as "done."

## Process

- Update `docs/STATUS.md` at milestone boundaries — a review finding
  fixed, a feature landed, a balance pass done. It's a *current-state*
  snapshot for picking up the project cold, not a running changelog; keep
  it short and overwrite stale sections rather than appending.
- At the start of a session, run `tools/doctor.sh` before assuming the
  toolchain is intact. If Blender MCP is needed for the task and its tools
  aren't available, say so rather than silently working around it — the
  add-on has to be running inside Blender for them to appear.

  (For the human, not Claude: `/doctor`, `/context`, `/mcp`, and
  `/permissions` are CLI commands you can type to confirm what actually
  loaded this session. Claude can't invoke those itself.)
