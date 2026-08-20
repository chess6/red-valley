# Homemade finger rig — ABANDONED (2026-08-19)

Three iterations. Stopped permanently by instruction. Do not attempt a fourth.

## Final state

`tools/ardy/add_fingers.py` builds a symmetric 53-bone rig (23 original + 30
new): three deform bones per digit, five digits per hand, under `hand.R`/`.L`.
No body bone was moved and only weight already on `hand.R`/`hand.L` was
redistributed. The bone *structure* is correct. The *weights* are not.

## Gate results — all four fail

| gate | result |
|---|---|
| every digit controlled base to tip | FAIL — ownership reaches only the distal tips |
| rest-hand geometry unchanged | pass — weights do not move rest vertices |
| left/right weighting symmetric | FAIL — right middle 103 verts vs left middle 30; right thumb 9 vs left thumb 47 |
| no neighbouring-finger contamination | FAIL — `final_weights_outer.png` shows blended ownership across adjacent digits |

The grip was not attempted: the gates gate it.

## Root cause

Reliable automatic digit segmentation is not achievable on this mesh. The
finger geometry is coarser than the gaps between digits, so every automatic
method tried produced plausible numbers and wrong geometry:

- **Mesh connectivity** — GLB UV splits fragment the hand; largest component
  above the knuckle was 87 of ~500 vertices.
- **DBSCAN** — vertex spacing exceeds the inter-digit gap; 4 mm eps returns 107
  singletons, larger eps merges digits.
- **Tip-band gap splitting** — merges pairs (94- and 92-vertex "digits"), and
  gave a thumb of 0.082 m on one hand and 0.0144 m on the other.
- **Straight knuckle-to-tip chains** — the rest fingers are curled, so a
  straight chain passes through air and captures only tips.
- **Tube tracking + adaptive per-cross-section radius** (this iteration) —
  follows the curl, but seeds from tip clusters that are themselves unreliable,
  so the right thumb collapsed to 9 vertices.

Every one of these failed *visually* while producing acceptable-looking counts.
That pattern is the finding: capture counts cannot validate this work.

## Recommended next step: a human places the bones once

The blocker is automatic segmentation, not rigging. Anything that has a person
position finger bones once removes it entirely.

1. **Rigify** — free, local, already ships with Blender 5.1. Its human metarig
   has exactly the needed chains, thumb included. A person aligns the metarig
   fingers to the mesh once, then generates. Note: Rigify's heat-map binding has
   already failed on this mesh's UV-split surfaces earlier in this project; the
   welded-proxy weight-transfer built here is the known workaround. **Best fit:
   free, offline, no upload, no licence question.**
2. **Auto-Rig Pro** — paid Blender addon (~$40), local. Smart finger detection
   and voxel-based binding, materially better than Rigify at this specific task.
   Requires spend approval.
3. **AccuRIG** (Reallusion) — free, full 5-digit hands, but a Windows desktop
   app; needs Windows or Wine.

Mixamo is EVALUATED-NEGATIVE — see `art/animation/mixamo_bench/README.md`.
