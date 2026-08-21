# ADR 0001 — Generators for locomotion, keyframes for interactions

**Status:** accepted · **Date:** 2026-08-21 · **Branch:** `animation-retarget-v2`

## Decision

1. Keep the canonical motion representation, the adapters, the control-driven
   Rigify retargeter and the validation gates. They are generator-agnostic and
   `walk_fwd` demonstrates they work.
2. Use motion generators for **locomotion and ambient body motion**.
3. **Hand-author the interaction one-shots** — `water_can`, `harvest_pick`,
   `cover_place`, `scatter_hand`.
4. **Stop the ARDY/Kimodo A/B.** It does not gate the milestone.

## What forced this

The evidence separates cleanly by clip type:

| | `walk_fwd` | `water_can` |
|---|---|---|
| effort | generated first try, minimal iteration | 2 paid runs, ~15 contract revisions |
| result | reads as a natural walk | still not a convincing pour |
| what the clip needs | plausible cyclic motion | exact placement against a fixed prop and a 0.22 m bed |

Generative motion models are strong at the first and weak at the second. A pour is
defined almost entirely by *where the spout is*. The tighter that is constrained,
the smaller the generator's contribution becomes — until it is interpolating
between keyframes that were authored by hand anyway.

By the end of the second run the "contract" contained foot swing arcs, a lift
profile chosen for continuous derivatives, knee-direction steering, a spine-lean
ramp, carry-to-pour blend weights and a wrist tilt curve. **That is keyframe
animation.** An IK posing tool had been built and then a generator was paid to
reproduce its output.

## Cost of learning it late

$0.90 across two runs, both with their conclusions withdrawn:

- **Run 1** ($0.16): the contract serialised target *positions* while the format
  stores *rotations*, so it encoded "rest pose, translated" and neither generator
  was asked to step. A generator result was never in the data.
- **Run 2** ($0.74, over a $0.20 cap because the cap priced GPU-hours and ignored
  ~33 GB of bandwidth): both generators stepped and hit their targets to within
  millimetres — but the contract placed the bed 0.36 m from the world origin, of
  which the step consumed 0.26 m, so the request itself was not watering.

The signal was present after run 1. Each failure was treated as a contract bug
rather than as evidence that the approach did not fit the problem.

## What is kept, and what it is worth

Not wasted, and it stays in use:

- **RVM/1 canonical representation** — quaternions, hierarchy, contacts, phases.
- **Two adapters** (ARDY Core27, Kimodo SOMA30/77), proving the boundary is real.
- **Control-driven retargeter** — full orientation transfer, twist preserved
  exactly, rig constraints intact, IK feet and hands, `IK_Stretch` off.
- **Task-space gates** — signed sagittal spine shape, contact-event step
  detection, path-based stability, joint limits, prop rigidity, GLB round-trip.
- **Free pre-flight** — `prove_contract.py` and the contract preview render, both
  of which caught defects that two paid runs did not.

## Consequences

- Interaction clips gain frame-level control and stop depending on a rented GPU.
- Locomotion keeps its generator path; `walk_fwd` is unaffected.
- The generator question is deferred, not answered. If a future clip needs
  plausible non-cyclic full-body motion, the adapter boundary makes revisiting it
  cheap.

## What actually gates the milestone

None of it is motion:

1. **Rodin character licence is unrecorded** — blocks any promotion to `assets/`.
2. **Fused hand topology** — recorded blocker; MPFB CC0 control character first.
3. **Jaw/neck blend weights** strain to 80%.
