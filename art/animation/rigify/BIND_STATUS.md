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

## FINAL: automated Rigify hand binding is INCONCLUSIVE (2026-08-20)

### The geometry-only selection worked

Replacing weight-based selection with geometry alone was the right fix for the
circularity. A wrist plane perpendicular to the forearm axis, a flood fill
through mesh adjacency from a palm seed, and a 0.16 m bound used only to reject
the thigh captured **299 (R) / 322 (L) welded vertices — the complete hand**,
with no vertex-weight test anywhere.

### But the digits still do not separate

With a correct region, the hand's own topology yields **three to four connected
components, never five**, at every distance threshold from 10 mm to 46 mm, on
both hands.

    R: dist>36..42 mm -> 3 comps;  dist>44 mm -> 4 comps [78, 51, 36, 25]
    L: dist>30..34 mm -> 3 comps;  dist>36..44 mm -> 4 comps [87, 60, 51, 43]

`fusion/fusion_palm.png` shows it directly: four coloured digit components and
the grey palm. The fifth digit never appears as its own component.

Two things are true of this mesh at once:

1. **The pinky is too short and too curled to separate.** It merges into the
   palm at every threshold that still separates the other digits.
2. **One digit pair remains fused** even at the fingertips — four components for
   five digits at the most distal cut.

This is a property of the character geometry, not of the rigging method. Rodin
produced a hand whose digits are not five topologically distinct protrusions.
No automated binder can assign a pinky chain that the surface does not
distinguish.

**Marked INCONCLUSIVE. No further segmentation method will be attempted.**

### What is nonetheless sound

The body rig and bind are good and should not be discarded:

- 71 deform bones, handedness clean, symmetry within 5.9 mm
- welded-proxy bind with **max vertex drift 0.000000000 m**
- geometry, UVs, material, all four shape keys and face rigidity preserved
- **zero unweighted vertices**
- thumb corrected: 337 (R) / 319 (L) dominated vertices, against 9 on the
  abandoned custom rig
- index, middle and thumb curl correctly; elbow, shoulder, knee and crouch pass

Failing: pinky (zero weight, both hands) and ring (weak at 83 / 112).

### The decision this now needs

The blocker is the hand geometry, so the remedy is an asset decision, not a
rigging one. Either the hands are repaired so the five digits are separate
surfaces, or the character ships with a hand that cannot form a true fist and
the watering can is held with a simplified grip. That call is the user's.

## CORRECTION: the fingers were being curled backwards (2026-08-20)

Caught by the user. Every deformation render I judged had the **right hand
hyperextending**, not curling.

Rigify mirrors the finger controls, so a curl is **+X on the right hand and −X
on the left**. I applied the same sign to both hands, so one of them always bent
backwards. Measured tip travel along the palm normal:

| master rotation | right | left |
|---|---|---|
| x = −88° (what I used) | **−60.5 mm, hyperextends** | +33.0 mm, curls |
| x = +88° | +17.4 mm, curls | **−49.7 mm, hyperextends** |

That `+nrm` is the palm side is confirmed independently: at rest the fingertips
sit +24 mm along `nrm` from their own bases (a normal relaxed curl), and the
thumb mass sits +37 mm on the same side, which is where an opposing thumb
belongs.

### What this invalidates

Every right-hand curl and fist render before this, including the ones behind
"one digit stays extended in the fist". That evidence was a backwards hand and
cannot support any conclusion. `hands/*.png` are re-rendered with per-hand signs
and the right fist now closes properly.

### What still stands

The pinky weight measurements are pose-independent and unaffected:
`DEF-f_pinky.*` carries zero weight on both hands, and ring is weak at 83 / 112.
The topology finding also stands: the region never splits into five components.

### What must be re-examined

The INCONCLUSIVE verdict was reached partly on visual evidence that is now known
to be wrong. The weight and topology findings still support it, but the visual
half of the case needs redoing against correctly-curled renders before that
verdict should be relied on.

## Curl direction and refinement — both hands (2026-08-20)

### The mirrored-sign conclusion was itself wrong

I previously reported that the curl sign is opposite per hand. It is not. That
test measured **both** hands against the **right** hand's palm normal taken from
`hand_ortho_mapping.json`; for the left hand that normal points the wrong way,
so the sign of the dot product lied.

Re-measured against each hand's own palm normal — derived from its own thumb
mass, which cannot suffer a mirroring error — **both hands curl at +X**:

| rotation | right | left |
|---|---|---|
| x = +88° | +39.6 mm, CURL | +36.9 mm, CURL |
| x = −88° | −47.1 mm, hyperextend | −51.8 mm, hyperextend |

### Curl refined

A fist is not one rotation. Driving only `*_master` gives a uniform arc that
reads as a claw, so the three joints are now driven separately:

    fist   MCP 50 deg, PIP 68 deg, DIP 42 deg
    curl   MCP 32 deg, PIP 40 deg, DIP 22 deg

**X does not mirror between hands, but Z does.** Applying one Z to both thumbs
left them 4.5 mm and 8.5 mm out of step; mirrored, they agree within 1 mm.

### Verified on the mesh, not the bones

Displacement of the actual deformed surface toward the palm, in a full fist:

| digit | right | left |
|---|---|---|
| index | +9.4 mm | +9.5 mm |
| middle | +10.7 mm | +10.5 mm |
| ring | +4.6 mm | +4.3 mm |
| thumb | +1.3 mm | +0.3 mm |
| **pinky** | **no surface** | **no surface** |

Both hands are now symmetric to within 0.3 mm on the working digits, and both
fists close.

Unchanged: no vertex carries more than 0.5 weight on any pinky bone, so the
pinky has no surface to move. Ring curls at less than half the index/middle
travel, consistent with its weak 83 / 112 vertex ownership.
