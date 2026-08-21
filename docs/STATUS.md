# Red Valley — status

## Current: animation pipeline v2 under review (branch `animation-retarget-v2`)

v1 (`main`, `3f3292f`) is **not accepted as final**. A bounded v2 correction of
the retarget/contact architecture is complete and awaiting review. $0 cloud
spend; the constrained ARDY result is preserved and reused, not regenerated.

All ten reported v1 findings were **confirmed from code and assets** before any
change was made — evidence in `art/animation/v2/baseline/audit.json`.

Architecture: `docs/ANIMATION_PIPELINE_V2.md`.
Asset blockers: `docs/ASSET_BLOCKERS.md`.
Machine-readable evidence: `art/animation/v2/V2_VALIDATION.json`.
Gates: `tests/anim_clips_v2.sh` (fails on v1 by construction).

### What v2 fixes, measured

Full orientation transfer (forearm roll 25.2° → 47.2° against a 47.2° source),
rig left intact so twist distributes through `DEF-*.001`, root bob and weight
shift preserved, source contact labels driving foot IK locks, prop rigid to the
hand (1.7e-07 m drift, zero collisions), prop socket present and proven in
Godot with `BoneAttachment3D`, one-shot retimed to 1.20 s with a 0.45 s sync.

### What still fails (not waived)

1. Walk foot skating 8.0 cm/s peak vs a 5 cm/s gate.
2. Spout 0.50–0.62 m above the bed vs the documented 0.15–0.30 m band — a
   **source deficiency**: this ARDY clip never lowers the hand.
3. Jaw/neck blend band strains to 82% — a weighting defect on the mesh.

### Decisions needed

- Loop-seam criterion: the documented 1 cm absolute gate is stricter than the
  motion itself; a resolution-independent replacement is proposed, not applied.
- Locomotion speed: source 1.45 m/s vs `WALK_SPEED = 4.3`. Four options costed;
  no gameplay constant was changed.
- Hand topology: retopologise the Rodin hands, or build a CC0 MPFB control
  baseline first. Recommendation in `docs/ASSET_BLOCKERS.md`.
- Rodin licence still unrecorded — blocks any promotion to `assets/`.

## Known problems

- Diagnostic watering can is `NOT_FOR_SHIPPING`; a cleared prop is still needed.
- Pinky unweighted, ring weak (asset blocker, not a rig defect).

## What's next (after review)

1. Review the before/after videos and pick the recommendation in
   `docs/ANIMATION_PIPELINE_V2.md` §recommendation.
2. Resolve the three open gate failures or accept them explicitly.
3. Only then: promotion, further clips, or a Kimodo benchmark through the same
   canonical adapter.
