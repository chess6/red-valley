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
| forearm roll, right, **8 s water take** (source 47.2°) | 25.2° | **47.2°** | ≤ 5% loss |
| forearm roll, left, **8 s water take** (source 23.1°) | 18.3° | **23.1°** | ≤ 5% loss |

> Roll figures are a property of the clip they were measured on and are **not**
> comparable across clips. The 47.2° pair above is the 8 s water take. The
> delivered 1.2 s one-shot has a different source roll range, and its right
> forearm additionally carries the authored pour, so it is reported separately by
> `tools/rvmotion/validate.py` with its source clip named. The earlier claim
> "forearm roll exact on every clip" was wrong and is withdrawn: it holds on
> FK-driven arms, and does not apply to a bone under an authored override.
| twist bones carrying signal | none driven | 5 of 5 channels > 5° | ≥ 2 |
| foot skating, treadmill-corrected | not measured | 8.0 cm/s peak | < 5 cm/s ✗ |
| prop rigid to hand | socket rotated under static fingers | **1.7e-07 m drift** | rigid |
| can/body collisions | 303 tris (wrist) | **0** | zero |
| `prop_socket` in GLB | **absent** | present, tracked in Godot | present |
| one-shot duration | 8.0 s | **1.20 s** | ~1.2 s |
| sync point | none | **0.45 s** | ~0.45 s |

## Correction pass (after visual review)

Visual review caught four defects that every numeric gate had passed. Each is
recorded here because the pattern — metrics green, render wrong — is the single
most persistent failure mode in this pipeline.

| defect (spotted by eye) | cause | fix |
|---|---|---|
| character parked metres off-origin, legs splayed | the torso was referenced against the absolute source hip position while the feet lived in the in-place trajectory's frame — two origins | one `clip_space()` mapping used by every driven control |
| one knee bending backwards, the other fine | Rigify ignores a pole target unless `pole_vector` is on; **every pole keyframe written was inert**, so the solver chose each knee plane itself | enable `pole_vector`; seed poles with the anatomical direction and hold the last well-conditioned one |
| knee locked dead straight for a third of the cycle | goals were built as `rig_rest_foot + source_delta`, but this character's rest foot sits 0.134 m lateral of its hip — 0.875 m from a 0.865 m leg, already past full extension | target **hip-relative**: animated hip + the source's own hip-to-foot vector, so reachability is automatic |
| spout swinging sideways instead of tipping down | the pour rotated `hand_fk.R` while the arm was switched to IK (an inert control), about the world X axis | rotate whichever control drives the hand, about the can's own handle-bar axis, sign chosen by measuring which way the tip drops |

Two of my own "fixes" during this pass were wrong and are recorded as such: a
smooth-locomotion foot shift that made goals unreachable, and a skating metric
that measured deviation from a constant treadmill velocity — which counts the
body's legitimate wobble over a planted foot as sliding.

### Review defects in the validation itself

| defect | fix |
|---|---|
| `planted_targets()` cyclic branch ended in `pass` | wrapped intervals are realigned by one stride, averaged, then sent back |
| wrist RMS sampled the spine transform from whatever frame the scene was left on | per-frame root reference captured in the same loop |
| an overall rotation mean hid task-critical errors | per-critical-bone limits; authored IK overrides reported with magnitude, excluded from the gate rather than averaged away |
| forearm-roll figures compared different clips | roll is reported per clip with its source clip named; 47.2° was the 8 s take, not the 1.2 s one-shot |
| the Godot test walked the bone chain by hand | two real `BoneAttachment3D` nodes, processed; rigidity vs `DEF-hand.R` measured at **0.000000 m** across the clip |
| seam compared against one arbitrary interior sample | every interior transition, with median/p90/max, plus a legal-contact-transition check |

### Measured after correction

| metric | before correction | after |
|---|---|---|
| walk rotation fidelity, mean | 2.15° | **0.74°** |
| walk critical-bone breaches | shin.R 52°, shin.L 21°, thigh.L 14° | **none** |
| water critical-bone breaches | shin.R 108°, shin.L 116° | **none** (right arm is an authored override, reported at 10–58°) |
| walk foot skating, peak | 16.4 cm/s | 7.4 cm/s (still failing) |
| can/body collisions | 303 (v1) → 20 | **7**, all `DEF-forearm.R.001` — the holder's own wrist |
| prop rigidity in Godot | untested | **0.000000 m** vs a hand attachment |

## Second correction pass (arm swing, pelvis, gate honesty)

| defect | cause | fix |
|---|---|---|
| left arm swung far forward and barely back | calibration offsets were computed per side from one source frame, so each arm inherited a *different* constant rotation — up to **40.7°** of left/right disagreement. The rig invented an asymmetry the source does not have | mirror one side's offset onto the other and average; residual asymmetry (17%) now matches the source's own (20%) |
| pelvis protruding backwards while leaning | `DEF-spine` was pitched **32.4°** where the source had **3.0°**: Rigify's `torso` is the master of the whole torso, not the pelvis, so DEF-spine received the torso tilt *plus* its own FK rotation | close the loop on the DEF bones themselves — measure each and correct its driving control until they agree, rather than reverse-engineering Rigify's tweak blending |
| right elbow locked at 179.7° for the whole pour | the spout solve pushed the hand goal past the arm's reach — the arm equivalent of the knee bug | clamp the goal to 97% of arm length; the residual gap is a **source** finding and is now reported instead of solved away |
| 96° "wrist deviation" | the metric measured the absolute angle between two bone axes, which is already 53° at rest on this rig | measure articulation relative to rest; the real figure is 61° |

Gate honesty fixes from review: `walk_loop.json` regenerated (the retired
single-sample interior calculation is gone from `loop.py`, not just from the
artefact); the spout gate now requires the band to **hold across the pour
window** rather than passing if any single frame enters it; and authored-override
bones, while exempt from the fidelity gate, now face explicit **elbow range,
wrist articulation, knee range and joint-jitter** gates — which immediately
caught the locked elbow and a 65°/frame jump that the exemption had been hiding.

## Isolation test (before Kimodo)

Full write-up: `docs/ISOLATION_TEST.md`. Headline: the authored interaction
layers are **innocent** — plain and polished retargets measured identically on
every task-space quantity. Two retargeter defects were real and are fixed: a
spine *shape* error that produced the lower-back arch (rotation-matching is not
direction-matching across skeletons with different rest orientations), and
pelvis placement being corrected before the spine solve moved it. The missing
step and the deep hip hinge are properties of the **source**, and the missing
step traces to a constraint file that pinned both feet.

## Open gate failures (not waived)

1. **Walk foot skating 7.4 cm/s peak** (left) vs a 5 cm/s gate; water 12.5 cm/s
   on a clip where the feet should not move at all. Total slide is small
   (~2.4 cm per foot per walk cycle) and the excess sits at contact-interval
   edges. Contact-edge blending was implemented and did **not** clear it, so the
   remaining cause is not the lock ramp — it is unresolved.
2. **Spout 0.388–0.406 m above the bed across the pour window (0/9 frames in band)** vs the documented 0.15–0.30 m band.
   This is a **source deficiency, not a retarget defect**: the ARDY clip never
   lowers the hand (0.94–1.02 m for all 160 frames), it only leans and reaches.
   With `IK_Stretch` off the arm cannot close the remaining ~0.20 m. An earlier
   build appeared to pass this gate — it was stretching the character's arm.
3. **Jaw/neck blend band strains up to 82%.** See the asset blockers below.
4. **2 triangles of can-vs-wrist contact** on the holder's own forearm. Down
   from 303 in v1, but not zero: it is the proxy can's handle arch against this
   hand, so it is bounded by the prop and hand-topology blockers, not by the
   retargeter.

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
