# Rigify production-rig candidate

Separate from the accepted mesh and the frozen diagnostic rig; neither is
modified by anything here.

## Done

**Rigify enabled** (bundled with Blender 5.1.2). Its human metarig carries 159
bones including all 30 finger bones — `thumb.01/02/03`, `f_index`, `f_middle`,
`f_ring`, `f_pinky`, three each, both hands. That is exactly the structure the
custom rig could not produce.

**Orthographic hand plates** for explicit joint placement — `hand_palm.png` and
`hand_edge.png`, with `hand_ortho_mapping.json` giving an exact pixel-to-world
mapping so joints are read off rather than inferred:

    P = centre + right*((px/1400 - 0.5)*0.15) + up*((0.5 - py/1400)*0.15)

    centre  (-0.405972, -0.018986, 0.856489)
    palm    right = bar  (-0.171, -0.952,  0.252),  up = fing (-0.332, -0.186, -0.925)
    edge    right = nrm  ( 0.928, -0.242, -0.284),  up = fing (-0.332, -0.186, -0.925)

Two render problems were fixed to make these usable: the palm-side camera sat
inside the thigh (the palm faces the leg), so the hand is isolated first; and
the first edge plate was blown out to a single white mass, so exposure was cut.

The palm plate resolves all five digits. The edge plate shows the curl profile
and the thumb branching clear of the fingers.

## Remaining

1. Align the metarig — body from ortho body views, every finger and thumb read
   off the plates above. No automatic digit segmentation.
2. Generate the control rig.
3. Bind through the welded proxy; transfer weights to the UV-split mesh.
4. Preserve face rigidity (rigid on `head`, neck blending below the jaw) and the
   three proportion shape keys.
5. Add `prop_socket.R` on the verified palm contract (grip_anchor coincident,
   drift 1.5e-08 m).
6. Export deform bones plus root/socket only; exclude Rigify ctrl/mech bones.
7. Retarget the accepted walk; build one closed grip via finger and hand IK.
8. Validate shoulder, neck, fingers, face, foot contacts, Godot import, grip.
9. Render walk and grip beside the diagnostic rig.

## Iteration 1 — halted before alignment (2026-08-20)

Plates were improved substantially, and improving them surfaced a defect in the
accepted rig that blocks explicit finger placement. No metarig alignment and no
rig generation were performed, so the four overlay renders do not exist yet.

### Plates now available

| file | content |
|---|---|
| `hand_palm_grid.png` / `hand_edge_grid.png` | shaded, mm grid |
| `hand_palm_depth_grid.png` | colour = `nrm` offset (blue −30 / green 0 / yellow +30 mm) |
| `hand_edge_depth_grid.png` | colour = `bar` offset (blue −45 / green 0 / yellow +45 mm) |

Depth coding was added because the curled phalanges overlap in every plain view,
so no single silhouette can carry joint depth. Exposure was cut (the first edge
plate was a featureless white mass) and the camera no longer sits inside the
thigh.

### Defect found in the accepted rig

Of the vertices standing more than 14 mm proud of the palm — the thumb and
thenar mass — **254 of 549 are dominated by `forearm.R`, not `hand.R`**.

Isolating the hand on hand-weight alone therefore deletes the thumb entirely,
which is what the first strict plate showed. It also explains why the abandoned
custom rig's right thumb collapsed to 9 vertices: the thumb was never on the
hand bone to begin with. The plates now include forearm-dominated vertices past
the wrist station, which recovers the thumb and drops the arm shaft.

This is recorded as a finding about the accepted rig. Nothing was modified.

### Remaining uncertainty — do not guess past this

1. **Finger identity and spacing.** The four finger lobes read at bar −52, −41,
   −19 and +18 mm, giving gaps of 11, 22 and 37 mm. Evenly spaced fingers should
   be roughly 15–20 mm apart, so at least one lobe is two digits merged, or one
   digit is hidden behind another by the curl. Lobe widths (15, 17, 22, 27 mm)
   point the same way — 27 mm is too wide for one finger.
2. **Phalangeal joints.** Only each digit's base and tip are readable. There are
   no knuckle-crease landmarks at this mesh density, so MCP/PIP/DIP stations
   could only be assumed at anatomical 45/30/25 proportions, not measured.
3. **Thumb axis.** Position is now clear (bar ≈ +28, `nrm` ≈ +25 mm, fing −45 to
   −8). Its metacarpal base is not, because that region blends into the palm.

Item 1 must be resolved before alignment; placing a chain that spans two digits
would repeat exactly the failure that ended the custom rig.

## Iteration 1 COMPLETE (2026-08-20)

### Digit identification — resolved geometrically

The axial plate (`hand_axial_depth_grid.png`), looking straight down the finger
axis, separates all five digits into distinct lobes. Identity is read from
geometry, not assumed and not taken from vertex weights.

| digit | bar (mm) | nrm (mm) | tip fing (mm) |
|---|---|---|---|
| pinky | −54 | +7 | +2 |
| ring | −39 | +16 | +30 |
| middle | −20 | +22 | +41 |
| index | +7 | +28 | +40 |
| thumb | +30 | +36 | ≈ −20 |

Bar spacing is genuinely uneven (15 / 19 / 27 mm) — the index is abducted. The
monotonic `nrm` rise (+7, +16, +22, +28) independently confirms the ordering.

### Generated rig

403 bones: 71 DEF, 65 ORG, 136 MCH, 131 control. **30 deform finger bones**,
three per digit, five digits, both hands.

| check | result |
|---|---|
| deform finger bones | 30 / 30, L=3 R=3 per digit |
| handedness (.R at −X) | 0 violations |
| symmetry | 6 bones >4 mm, worst 5.9 mm |
| mesh vertices / tris | 70,042 / 49,994 — unchanged |
| shape keys | all 4 present, unchanged |
| UV layers / materials | 1 / 1 — unchanged |

### Faults found and fixed during this iteration

- **Face-bone filter deleted both forearms.** `"forearm"` contains `"ear"`, so a
  keyword filter removed them. Face bones are now defined as the descendants of
  `spine.006`.
- **World-space mirroring is wrong for the left hand.** The left hand is not the
  X-mirror of the right; mirroring put its finger chains outside the mesh. Each
  hand now gets its own measured frame and the digit table is applied in that
  frame with `bar` negated.
- **`hand.L` in the accepted rig has a 0.322 m tail** pointing into empty space.
  Inheriting it produced a 32 cm "hand" bone protruding from the character. Both
  hand bones are now derived from their own middle-finger knuckle: 0.0469 m (R)
  and 0.0494 m (L).
- **Finger chains overshot the fingertips** by 7–14 mm. Per-digit pullback added.

### Cautions for the next stage

1. **The inside/outside ray-parity test is unreliable on this mesh.** It reports
   11 of 15 finger-bone heads outside on *both* hands while the overlay plainly
   shows the chains inside the digits. The mesh is Rodin output and not
   watertight, so parity counting is meaningless here. Do not use it as a gate;
   trust the overlays.
2. **Residual symmetry offset up to 5.9 mm** on `forearm.R`, `hand.R` and the
   four `palm.*.R` bones. This traces to genuine mesh asymmetry — the right hand
   carries 1076 vertices against the left's 972 — not to placement.
3. **Thumb chain is the least certain digit.** Its position is clear but its
   metacarpal base blends into the palm, so the base station is an estimate.
4. **`hand.R`'s proxy protrudes through the palm** in the overlay. That is a
   6 mm visualisation cylinder in a thin palm, not necessarily a misplaced bone,
   but it should be confirmed during binding.

Recorded for the binding stage: the accepted rig weights much of the thumb and
thenar mass to `forearm.R` (254 of 549 vertices standing proud of the palm).
Correct this during welded-proxy binding. It did not block metarig placement.
