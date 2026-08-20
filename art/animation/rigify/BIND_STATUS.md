# Iteration 2 — bind complete, pinky FAILED

## Welded-proxy bind: worked

The weld collapsed **70,042 vertices to 24,980 — 64.3% were seam duplicates**,
which is precisely why Blender's bone-heat solver fails on the original mesh.
Bound the welded copy, transferred weights back by position.

| check | result |
|---|---|
| proxy bind | 71 DEF groups, 122 unweighted of 24,980 |
| weight transfer | all 70,042 verts, 0 without an exact weld partner |
| vertex positions | **max drift 0.000000000 m** |
| verts / polys | 70,042 / 49,994 unchanged |
| UV layers / material | `UVMap` / `model` unchanged |
| shape keys | all four present and unchanged |
| face rigidity | 8,846 verts rigid on `DEF-spine.006`, neck blend below jaw z=1.7104 |
| unweighted after bind | 0 |

23 superseded vertex groups from the old rig were removed; the mesh now carries
only the 71 `DEF-` groups.

## Thumb: corrected

The input-rig defect is resolved. Thumb bones now dominate **337 vertices (R)
and 319 (L)** — against **9** on the abandoned custom rig. Residual forearm
share averages 0.15 (R) / 0.11 (L), with 85/47 vertices above 0.25; acceptable
blend at the wrist, worth a look if the thumb base pinches under load.

## FAILED REGION: pinky, both hands

`DEF-f_pinky.*` carries **exactly zero weight** — not low, zero. That is the
bone-heat solver declining to solve for that chain, not a weak result.

    f_pinky   verts_any_weight=0     total weight 0.00
    f_ring    verts_any_weight=261   total weight 87.07
    f_middle  verts_any_weight=576   total weight 197.15
    f_index   verts_any_weight=1316  total weight 330.13
    thumb     verts_any_weight=2204  total weight 393.91

Cause: the pinky chain is **not inside the pinky digit**. Its base sits 16.5 mm
from the nearest surface, which is impossible inside a digit roughly 10 mm
thick — the chain lies in the palm interior. So the pinky mesh stays owned by
`DEF-hand.R`/`.L` and does not curl. `deform/hand_fist_a.png` shows three digits
curling and one rigid.

Two attempts were made. The first left a 7.6 mm chain (a fixed 12 mm pullback on
a ~19 mm chord removed 63% of it); the pullback is now proportional and the
chain is 38 mm, but it is still in the wrong place. The plate reading for the
pinky is what is wrong, not the chain construction.

**Not compensated for with geometry edits, per instruction.** Reported instead.

Also outstanding: `f_ring` is weak at 83 (R) / 112 (L) dominated vertices
against index's 388/393, and 26 vertices remain unweighted.

## What passed

Finger curl, fist, thumb opposition, wrist flex/extend on index, middle, ring
and thumb; elbow, shoulder, knee and crouch on the body. Renders in `deform/`.

## Hand-correction pass (2026-08-20): unweighted resolved, pinky still FAILED

### "0 vs 26 unweighted" — explained and fixed

`bind_rigify` counted `v.groups` while the 23 legacy groups from the old rig
were still attached, so vertices whose **only** weight was legacy looked
weighted. Dropping the legacy groups exposed 26 of them. They are now filled
from the nearest weighted neighbour. **Final unweighted count: 0.**

### Pinky: NOT repositioned — the region cannot be selected reliably

Three independent findings, in order:

1. **`fing`-depth cuts can never isolate the pinky.** It is curled so far that it
   has no extent past the palm along the finger axis: cutting at `fing > +6`
   removes the pinky entirely, and the three surviving components span bar
   −37…+44. Across every cut from −6 to +20, on both hands, the maximum was
   **three** components, never four.
2. **Welding drops the pinky region below the weight threshold.** `hand.R >= 0.4`
   selects 1126 vertices on the raw mesh but only **262** on the welded one,
   because `remove_doubles` averages weights across merged duplicates. The
   welded hand region therefore spans bar −45…+56 and excludes the pinky, which
   the plates place at bar −60…−48.
3. **The frame is not the problem.** Plate, raw and welded bases agree exactly —
   `dot(bar, plate_bar) = +1.0000`, centres within 0.6 mm. The earlier
   sign-flip hypothesis is disproved.

So the pinky chain still owns zero vertices on both hands, and both hands still
fail the fist test — `hands/fist_R.png` and `hands/fist_L.png` each show one
digit remaining extended.

Ring is unchanged and still weak: 83 (R) / 112 (L) against index's 388 / 393.

### The blocker, stated precisely

Every method tried selects the hand **by vertex weight**, and the weights are
exactly what is unreliable here — they are the defect this pass set out to
correct, and welding degrades them further. Selecting by weight to find the
region, then binding to produce weights, is circular.

**Proposed fix, not applied:** select the hand region purely geometrically —
distance from the `hand.R` bone head plus a cut past the wrist station — with no
weight test anywhere. That removes the circularity and should let the welded
surface's own topology separate all five digits, which it already does cleanly
for the other four.

Not attempted here rather than guessed at, per the standing instruction.
