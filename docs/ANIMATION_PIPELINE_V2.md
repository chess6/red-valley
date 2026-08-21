# Animation pipeline v2 — architecture

Status: **bounded comparison, not accepted.** v1 remains on `main`; this is
`animation-retarget-v2`. No promotion to `assets/`, no new motion generated,
$0 cloud spend.

```
  native source            adapter              canonical motion
  ─────────────            ───────              ────────────────
  ARDY Core27       →  tools/rvmotion/     →   RVM/1  (.rvm.npz + .rvm.json)
  (Y-up, 27 joints,     adapters/               Z-up, quaternions, hierarchy,
   local+global rot,    ardy_core27.py          root translation + heading,
   root, contacts)      + .json calibration     contacts, phases, EE targets
        │                                              │
        │ validated BEFORE retargeting                 │  retime / loop close
        ▼                                              ▼
  native_view.py                              retime.py · loop.py
  (orientation triads,                        (crop, slerp resample, seam
   contact labels,                             closure, compression reported)
   anatomy checks)                                     │
                                                       ▼
                                        retarget_rigify_v2.py
                                        ─────────────────────
                                        Rigify CONTROLS, rig intact:
                                          · FK: torso, spine_fk×4, neck, head,
                                            shoulder, upper_arm/forearm/hand
                                          · IK: foot_ik + pole (both legs),
                                            hand_ik + pole when the contract
                                            demands it
                                          · rest-space calibration, pose-matched
                                          · IK_Stretch OFF
                                          · DEF constraints untouched → the rig
                                            distributes twist itself
                                                       │
                                                       ▼
                                        export_glb.py  →  Godot
                                        deform-only + DEF-prop_socket.R,
                                        asserted post-export, then proven
                                        in-engine with BoneAttachment3D
```

## What each layer is not allowed to do

| Layer | Forbidden |
|---|---|
| adapter | inventing motion; Euler component swaps (basis change is `R' = P R Pᵀ`) |
| canonical | source-specific anything; that is what makes a second adapter cheap |
| retime/loop | hiding time compression; fabricating a cycle from mismatched gait phase |
| retarget | stripping rig constraints; direction-only aiming where an orientation exists; IK stretch |
| export | dropping the prop socket; more than one action; non-deform joints |

## Why the v1 architecture had to change

v1 read `posed_joints` only and re-derived each bone's orientation by aiming it
at the next joint with `Vector.rotation_difference`. That is the minimal-arc
rotation between two directions: it has **zero component about its own axis**,
so axial twist is not merely lost, it is unrepresentable. Measured against the
same source, v1 delivered 25.2° of forearm roll where the source had 47.2°.

It then stripped the constraints from all 71 `DEF-` bones and keyed them
directly, which discards the generated rig's entire job — twist distribution,
IK, tweak interpolation — and left `DEF-*.001` twist bones with no local
contribution at all. Root translation was dropped wholesale, so vertical bob and
lateral weight shift did not exist. Foot contact was a sole-height threshold
rather than the source's own labels, which is what produced the false
"flight phase" verdict on a clip ARDY labels as 4.4% airborne.

## Measured v1 → v2

| metric | v1 | v2 | gate |
|---|---|---|---|
| DEF motion-delta error, mean | 1.49° | **0.53°** (water) / 1.65° (walk) | < 2° |
| forearm roll, right (source 47.2°) | 25.2° | **47.2°** | ≤ 5% loss |
| forearm roll, left (source 23.1°) | 18.3° | **23.1°** | ≤ 5% loss |
| twist bones carrying signal | none driven | 5 of 5 channels > 5° | ≥ 2 |
| foot skating, treadmill-corrected | not measured | 8.0 cm/s peak | < 5 cm/s ✗ |
| prop rigid to hand | socket rotated under static fingers | **1.7e-07 m drift** | rigid |
| can/body collisions | 303 tris (wrist) | **0** | zero |
| `prop_socket` in GLB | **absent** | present, tracked in Godot | present |
| one-shot duration | 8.0 s | **1.20 s** | ~1.2 s |
| sync point | none | **0.45 s** | ~0.45 s |

## Open gate failures (not waived)

1. **Walk foot skating 8.0 cm/s peak** vs a 5 cm/s gate. Total slide is 2.4 cm
   per foot per cycle; the excess is concentrated at contact-interval edges,
   where the source's label flips a frame before the foot is really still.
2. **Spout 0.503–0.619 m above the bed** vs the documented 0.15–0.30 m band.
   This is a **source deficiency, not a retarget defect**: the ARDY clip never
   lowers the hand (0.94–1.02 m for all 160 frames), it only leans and reaches.
   With `IK_Stretch` off the arm cannot close the remaining ~0.20 m. An earlier
   build appeared to pass this gate — it was stretching the character's arm.
3. **Jaw/neck blend band strains up to 82%.** See the asset blockers below.

## Criterion changes proposed (not applied without approval)

**Loop seam.** The documented gate is "body-space seam under 1 cm". At 20 fps a
swinging foot travels ~12 cm per frame, and the same extrapolation test applied
*inside* the cycle scores 0.051 m — so a 1 cm absolute gate is stricter than the
motion it is judging and no crop of this source can pass it. Proposed instead:
**the wrap frame must be no more abrupt than a normal frame of the same
motion** (seam ≤ interior extrapolation error). v2 measures 0.037 m seam against
0.051 m interior, so it passes the proposed form and fails the documented one.
Both numbers are reported by `tools/rvmotion/loop.py`; nothing was changed.

## Locomotion speed reconciliation (no gameplay constants touched)

Source stride: **1.45 m/s**. Gameplay `WALK_SPEED = 4.3` m/s (`src/player/player.gd:6`).
Options, for decision:

| option | effect | cost |
|---|---|---|
| A. Play the clip at 2.97× rate | feet stay locked, but a 0.34 s stride reads as a frantic scurry | free |
| B. Lower `WALK_SPEED` to ~1.5–1.8 m/s | matches the animation exactly; changes traversal feel and the labour-budget math | needs approval + a labour-budget recheck |
| C. Scale stride length in the retarget | keeps 4.3 m/s with a plausible cadence (~1.8× rate); feet still lock because locking happens before the in-place shift | free, retarget-side |
| D. Generate a faster source | correct but needs new motion | cloud spend |

**Recommended: C**, with A as a stopgap. Not applied — `WALK_SPEED` is untouched.
