# Red Valley — status

## Current milestone: animation pipeline — DELIVERED, awaiting visual review

Two validated clips on the accepted `rv_player_proportioned.glb` baseline,
driving the Rigify deform skeleton (71 DEF bones, deform-only exports, one
animation each, Godot-verified, playback-tested by `tests/anim_clips.sh`):

| clip | length | source | state |
|---|---|---|---|
| `walk_fwd` | 1.00 s loop @ 20 fps, in-place | ARDY `walk8_s1`, contiguous stride cycle | provisional (metric reports flight phases; visually clean at 5.2 m) |
| `water_can` | 8.0 s @ 20 fps | **constrained** ARDY run ($0.08, seed 0) + local layers | delivered |

**Pipeline decision (final): ARDY for general motion and for constrained
interactions.** Constraint files are built with ARDY's own classes and proven
locally before any spend. Text-only interaction prompting is prohibited.
Details: `docs/ANIMATION_REQUIREMENTS.md`; provenance:
`art/animation/rigify/CLIPS_PROVENANCE.json`.

Accepted limitations (gameplay camera, 5.2 m / fov 65): finger-handle
penetration, weak ring, stiff pinky, can-arch-on-wrist during the pour tilt.

## Blockers before production promotion (assets/)

- **Rodin character licence terms are not recorded in-repo** — the asset gate
  requires provenance; resolve before any clip or the mesh enters `assets/`.
- Clips live under `art/animation/rigify/` (hygiene-allowlisted) pending the
  user's visual review.

## Known problems

- Walk cycle loop seam 0.06 m (body) — invisible at gameplay distance, listed
  for honesty; regenerating a longer take would fix it properly.
- The diagnostic watering can is NOT_FOR_SHIPPING; a provenance-cleared prop is
  still to be sourced (same attachment contract: `can_attachment.json`).

## What's next (after review)

1. User visual review of both clips (videos under `art/animation/rigify/*/`).
2. Resolve + record Rodin licence; promote approved clips to `assets/anim/`.
3. Remaining P0 clips through the same constrained-ARDY pipeline.
