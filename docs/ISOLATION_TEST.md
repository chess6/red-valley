# Isolation test: native source vs plain retarget vs polished v2

Run before any Kimodo work, to answer one question: **when the delivered water
clip looks wrong, is the source at fault, the retargeter, or the authored
interaction layers?**

Method: the same task-space quantities measured on all three, with the authored
layers (`HAND_CLEAR`, `HAND_FWD`, spout solve, pour rotation, arm IK) fully
disabled for the "plain" build. Tooling: `tools/rvmotion/isolate_measure.py`.

## Result: the authored layers are innocent; two retargeter defects were real

| quantity | source | plain retarget | polished v2 | verdict |
|---|---|---|---|---|
| wrist forward reach (normalised by arm length) | 0.623 | — | 0.508 (0.82×) | **preserved** |
| wrist forward reach, raw | 0.329 m | 0.445 m (135%) | 0.366 m (111%) | preserved; raw ratio tracks the 1.35× arm-length ratio |
| shoulder→wrist extension | 0.513–0.524 m (constant) | — | — | the source's arm does **not** extend |
| trunk lean | 1.1–22.6° | 0.0–23.0° | 0.0–23.0° | faithful, 1.07× |
| spine per-segment pitch | [9.7, 25.1, 32.4, 39.1]° | **[18.7, 23.9, 25.6, 25.3]°** | same | **DEFECT — retargeter** |
| pelvis excursion | 0.075 m | **0.121 m (1.62×)** | same | **DEFECT — retargeter** |
| lead-foot travel | 0.018/0.022 m | **0.107/0.102 m (4.7–6.1×)** | same | consequence of the pelvis defect |

Plain and polished were **identical on every one of these**, which is what
exonerates the authored layers: whatever they do, they do not remove the reach
or create the arch.

### Defect 1 — the arch was a spine *shape* error, invisible to a rotation metric

The retargeter matched DEF-bone **rotations**, which is correct for limbs. But
the two skeletons have different rest orientations, so equal rotations do not
mean equal bone **directions** — and the silhouette follows directions. Measured
per-segment pitch came out nearly flat, with the lumbar base almost doubled
(9.7° → 18.7°) and the upper spine cut by a third (39.1° → 25.3°): a lower-back
arch under a torso that fails to curve over. Fixed by closing the loop on
segment direction, with roll inherited from the rotation transfer. Spine shape
error is now **[0.0, 0.0, 0.0, 0.0]°**.

### Defect 2 — pelvis placement was corrected too early

The torso was positioned so the pelvis landed on target, then the spine solve
rotated controls the pelvis hangs from and moved it again. Pelvis excursion was
1.62× the source, and the feet — targeted from the animated hip — inherited that
error four to six fold. Fixed by making pelvis placement the last word in the
frame. Pelvis is now **1.00×** and foot travel is *below* source.

## What is genuinely the source's, not the pipeline's

- **No step.** The source's feet move 1.2–1.6 cm. That is not a retarget loss —
  the constraint file used for that ARDY run pinned **both feet**, so the
  generator was told to keep them planted. A stagger toward the watering side
  needs a constraint change and a new generation, not a retarget fix.
- **Reach by hip hinge, not arm extension.** Shoulder→wrist stays at
  0.513–0.524 m for the whole clip: the arm never extends. All 33 cm of forward
  reach comes from the trunk hinging 1.1° → 22.6°. The mechanic the reference
  describes — reach from the shoulder, pelvis under the torso — is absent from
  the source and cannot be retargeted into existence.

## New gates

`forward reach preserved` (normalised by arm length), `step displacement matches
source` (pelvis-relative, so an in-place loop is judged fairly), and `spine shape
preserved` (per-segment pitch within 4°). All three pass on both clips except the
water step ratio, which sits at 1.36 on a 2 cm absolute difference and is
reported rather than tuned away.

## Conclusion for the generator decision

The pipeline is **not** distorting this source in the ways suspected. The
remaining unnatural read — planted feet and a deep hip hinge — is in the motion
itself, and half of it traces to a constraint file that pinned both feet. That
makes a Kimodo comparison meaningful now: it will be judged through a pipeline
whose task-space behaviour is measured, and against a constraint set that should
**not** pin both feet if a stagger is wanted.
