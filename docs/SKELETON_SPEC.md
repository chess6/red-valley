# Red Valley — shared production skeleton

The single skeleton the player and Sarah both use, and the target every ARDY
clip is retargeted **onto**. Defined here independently so that no generator
dictates it.

Status: **specification only.** No rig has been built and no mesh has been
skinned against it.

---

## Why it is specified before the pilot

ARDY emits motion on NVIDIA's Core/G1 skeletons. If the production skeleton
were derived from whatever ARDY happens to output, the generator would be
choosing the game's rig — and swapping motion source later would mean
re-rigging both characters. Defining it first makes ARDY one interchangeable
motion supplier among several.

---

## Global conventions

| Property | Value | Reason |
|---|---|---|
| Up axis | **+Y up, −Z forward** | glTF convention; Godot imports it directly |
| Units | metres, 1.0 scale | Godot works in metres |
| Reference height | **1.90 m** | The validated Rodin master measures 1.90 m |
| Rest pose | **A-pose, arms ~45° down from horizontal** | Matches the concept turnaround the character was generated from; avoids the shoulder distortion a T-pose bakes in |
| Root at origin | `root` at (0, 0, 0), on the ground plane between the feet | Locomotion is in-place; the root never translates in a clip |
| Naming | `snake_case` with `.L` / `.R` suffixes | Matches Godot and Blender retarget conventions |
| Bone roll | Y down the bone, Z forward | Keeps limb bends on a single predictable axis |

---

## Bone hierarchy (24 deform bones + 1 prop socket)

```
root
└── hips
    ├── spine
    │   └── chest
    │       ├── neck
    │       │   └── head
    │       ├── clavicle.L → upperarm.L → forearm.L → hand.L
    │       └── clavicle.R → upperarm.R → forearm.R → hand.R
    │                                                  └── prop_socket.R
    ├── thigh.L → shin.L → foot.L → toe.L
    └── thigh.R → shin.R → foot.R → toe.R
```

| Group | Bones | Count |
|---|---|---|
| Spine chain | `root`, `hips`, `spine`, `chest`, `neck`, `head` | 6 |
| Arms | `clavicle`, `upperarm`, `forearm`, `hand` × 2 | 8 |
| Legs | `thigh`, `shin`, `foot`, `toe` × 2 | 8 |
| **Deform total** | | **22** |
| Non-deform | `prop_socket.R` | 1 |

### Deliberately excluded

**No finger bones.** The camera sits ~5.2 m back and no mechanic requires
articulated digits; the Rodin mesh's fingers are modelled but need not be
animated. A rigid hand plus a prop socket is sufficient for the watering can.
Fingers can be added later without invalidating any clip, since adding leaf
bones does not alter existing channels.

**No twist, IK, pole or helper bones** in the deform hierarchy. If hand IK
becomes necessary (see the alignment contract), it is added as a control layer
that drives `forearm`/`hand`, not as new deform bones.

---

## Prop socket

| Property | Value |
|---|---|
| Name | `prop_socket.R` |
| Parent | `hand.R` |
| Purpose | Attachment point for held tools — watering can at P0 |
| Transform | Positioned at the grip centre of the closed right hand, oriented so a prop's local −Z runs along the forearm |
| Deform | **No** — excluded from skinning |

A tool mesh is authored with **its grip at the origin**, which is what makes
"swap the mesh, keep the clip" possible when seeds/compost/manure/mulch get
their own props later.

### Attachment convention (verified)

Parenting with an identity local transform does **not** work: Blender bone
parenting uses the bone *tail* as the child origin and applies
`matrix_parent_inverse` in an order that leaves the prop at the armature
origin. Set the world matrix explicitly, with one corrective rotation:

```python
sock = rig.matrix_world @ rig.pose.bones["prop_socket.R"].matrix
prop.matrix_world = sock @ Matrix.Rotation(radians(90), 4, "X")
```

Blender bones run along their local **+Y**, while props are authored with
local **−Z** down the forearm. Rotating +90° about X maps prop −Z onto bone +Y.

Verified against the diagnostic proxy: **grip-to-socket distance 0.0000 m**,
with the can hanging body-down and spout forward.

### Export note

Blender's glTF exporter adds a **`neutral_bone`** to the exported skeleton
(24 bones out of 23 authored) because `prop_socket.R` is non-deforming. It is
an exporter artifact, carries no animation, and should be ignored by the
retarget map rather than treated as a joint.

---

## Retarget requirements (ARDY → production skeleton)

| Step | Requirement |
|---|---|
| Bone mapping | Explicit Core/G1 → production name map, committed as data, not inferred by string matching |
| Rest-pose alignment | ARDY's rest pose is corrected to this A-pose before transfer, or every clip inherits a constant offset |
| Scale normalisation | ARDY output normalised to the 1.90 m reference height |
| **Root motion strip** | ARDY locomotion carries world displacement. It must be **converted to in-place**: root translation removed, forward speed measured and handed to code |
| Foot contact | Measure foot sliding after in-place conversion; a locomotion clip whose stride speed disagrees with `WALK_SPEED` 4.3 / `RUN_SPEED` 7.0 m/s will visibly skate |
| End-effector constraints | ARDY is **not object-aware**. `water_can` must be constrained at the hand/end-effector, not prompted for |

---

## Acceptance criteria for the two-clip pilot

`walk_fwd`:
- root translation is zero across the clip
- foot sliding under 3 cm/step at 4.3 m/s
- loops seamlessly (first and last pose match within tolerance)

`water_can`:
- grip holds the watering-can mesh without drift through the clip
- spout tip passes within the alignment tolerance (**±5 cm**) of the plot soil
  surface at the 0.45 s sync point
- no foot slide during the plant-and-pour

Failing the `water_can` spout criterion is the defined trigger for making hand
IK a P0 requirement.
