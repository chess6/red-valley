# Red Valley — status

## Decision: generators for locomotion, keyframes for interactions

See `docs/decisions/0001-generators-for-locomotion-keyframes-for-interactions.md`.

`walk_fwd` generated well first try; `water_can` took two paid runs ($0.90, both
conclusions withdrawn) and ~15 contract revisions and still was not convincing.
A pour is defined by exact placement against a fixed prop, which is what
generative models are worst at. The A/B is stopped; it does not gate the
milestone.

| clip type | path | state |
|---|---|---|
| locomotion (`walk_fwd`) | generated -> RVM/1 -> Rigify controls | provisional, passes all gates but foot skating |
| interactions (`water_can`, ...) | **authored keyframes** -> Rigify IK -> same export | first authored clip built |

Authoring: `tools/rvmotion/author_interaction.py` + a JSON spec in
`tools/rvmotion/clips/`. Runs locally in seconds, no GPU, no generator. Iterating
the pose is now editing numbers rather than renting a machine.

## What actually gates the milestone (none of it is motion)

1. ~~Rodin character licence unrecorded~~ — **RESOLVED 2026-08-21.** Hyper3D
   Rodin, paid Creator plan; ToS s5(a) and s2 recorded and archived in
   `art/character/SOURCE_LICENSES.md` + `licence_evidence/`. Classified
   **commercial_use: allowed (plan-dependent)**, NOT copyright transfer.
   Provenance entry staged for the moment of promotion.
2. **Fused hand topology** — blocker; MPFB CC0 control character recommended first.
3. **Jaw/neck blend weights** strain to 80%.

## Known problems

- Diagnostic watering can is `NOT_FOR_SHIPPING`; a cleared prop is still needed.
- Pinky unweighted, ring weak (asset blocker, not a rig defect).

## What's next (after review)

1. Review the before/after videos and pick the recommendation in
   `docs/ANIMATION_PIPELINE_V2.md` §recommendation.
2. Resolve the three open gate failures or accept them explicitly.
3. Only then: promotion, further clips, or a Kimodo benchmark through the same
   canonical adapter.
