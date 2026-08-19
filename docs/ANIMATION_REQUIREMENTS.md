# Red Valley — animation requirements

Derived strictly from confirmed gameplay in `docs/GAMEPLAY_VISION.md`, and
from the scope decisions recorded in "Answered scope decisions" below.

**Nothing here is inferred from asset names.** `crate.glb` exists and the
player never carries a crate; `well.glb` exists and is never used; `bin.glb`
exists and has no mechanic at all.

---

## Standing constraints that shape every clip

| Constraint | Consequence |
|---|---|
| Movement is code-driven (`velocity` + `move_and_slide`) | **All locomotion clips in-place. No root motion.** |
| The model rotates to face its travel direction | **No strafe or backpedal clips.** One forward set covers all directions |
| No jump action exists in the input map | **No jump / fall / land clips** |
| Third-person orbit camera ~5.2 m back | Hands and silhouette carry everything; facial detail is never seen in play |
| Actions are instantaneous in code; only the *clock* advances | Clips are cosmetic — **gameplay must never wait on clip length** |
| Plots are a fixed 0.22 m soil bed on flat ground | A fixed crouch-and-reach lands correctly **without hand IK** |
| Tool switching costs no game time | **No tool-swap / holster clips** |

---

## Answered scope decisions

1. **Visible props are part of the intended presentation.** Tools must **not**
   be architected as permanently abstract. P0 implements **hand sockets** and
   a real **watering can**. Row-cover work manipulates the **existing plot
   cover prop** rather than a carried one. Seeds and soil amendments may
   **temporarily share one hand-scatter motion**; five unique prop variants
   are explicitly *not* required before the motion pilot.
2. **Sarah shares the player's skeleton**, with **per-task work clips** rather
   than one generic bent-over loop.
3. **Carrying is undecided.** Build P0 assuming no carried produce; revisit if
   hauling replaces auto-sell.
4. **ARDY** is **NVIDIA ARDY** — a text- and kinematic-constraint-driven human
   *motion* generator. It produces skeletal motion only, never rigs or meshes.

---

## 1. Implemented now

**Nothing.** Characters are rigless; all current motion is procedural code:

| Actor | Current motion | Source |
|---|---|---|
| Player | vertical bob + z-tilt while moving | `player.gd::_physics_process` |
| Sarah | vertical bob walking; x-lean (0.25 rad + sine) working | `sarah.gd::_work`, `_face_move` |

---

## 2. Minimum set required by confirmed gameplay

**12 clips, 8 at P0**, plus one rig requirement. This covers every action the
game can currently perform — not a wish list.

### Rig prerequisites (blocking, P0)

| Requirement | Note |
|---|---|
| **One shared production skeleton** for player and Sarah | Defined by us, **not** dictated by ARDY |
| **Right-hand prop socket** | Watering can at P0; must generalise to other tools later |
| Character scale ~1.90 m | Matches the validated Rodin master |

### Player clips

| # | Clip | Type | Root motion | Prop | Contact/IK | Reuse | Priority |
|---|---|---|---|---|---|---|---|
| 1 | `idle` | loop | none | — | — | Sarah IDLE | **P0** |
| 2 | `walk_fwd` | loop | **in-place** | — | foot plant | Sarah WALK | **P0** |
| 3 | `run_fwd` | loop | **in-place** | — | foot plant | — | **P0** |
| 4 | `water_can` | one-shot ~1.2 s | none | **watering can (hand socket)** | can spout toward soil | Sarah water task | **P0** |
| 5 | `scatter_hand` | one-shot ~1.2 s | none | none (**temporary**) | hand sweep at soil height | **shared by seeds / compost / manure / mulch** | **P0** |
| 6 | `harvest_pick` | one-shot ~1.2 s | none | none | hands to crop height | Sarah harvest task | **P0** |
| 7 | `cover_place` | one-shot ~2.0 s | none | **existing plot cover prop** | two-handed, wider stance | Sarah cover task | **P0** |
| 8 | `inspect_crouch` | one-shot + hold | none | — | crouch, look down | — | **P0** |
| 9 | `clear_pull` | one-shot ~1.2 s | none | — | pulling motion | may reuse #6 | P1 |
| 10 | `uncover_gather` | one-shot ~1.2 s | none | plot cover prop | — | may reuse #7 reversed | P1 |
| 11 | `wait_breather` | one-shot ~2 s | none | — | — | — | P2 |
| 12 | `talk_idle` | loop | none | — | — | — | P2 |

**#5 is explicitly provisional.** Seeds, compost, manure and mulch are
mechanically distinct but physically similar, and at third-person distance one
scatter motion reads correctly for all four. It is a deliberate temporary
share, to be split into prop variants once the motion pilot proves out — the
hand socket exists from P0 precisely so that split costs nothing structural.

### Sarah

Shares the skeleton; **no unique clips**, but her WORK state now resolves
per task rather than playing one generic loop:

| Sarah state | Clip |
|---|---|
| IDLE | #1 `idle` |
| WALK | #2 `walk_fwd` |
| WORK — water | #4 `water_can` |
| WORK — cover | #7 `cover_place` |
| WORK — harvest | #6 `harvest_pick` |

### Explicitly out of scope

No jump, fall, land, climb, swim, strafe, backpedal, turn-in-place, carry,
haul, push, throw, tool-swap, holster, vehicle, combat, sit, eat or death
clips. None corresponds to any implemented or confirmed mechanic.

---

## 3. ARDY motion pilot — constraints

NVIDIA ARDY generates **motion data only** (joint transforms, NPZ) on NVIDIA's
**Core/G1** skeletons. It supplies no rig and no mesh.

| Constraint | Requirement |
|---|---|
| **ARDY must not dictate the production skeleton** | Define ours first; ARDY output is retargeted *onto* it |
| Output format | NPZ joint transforms → needs an import/convert step into Godot-usable clips |
| Skeleton mismatch | Core/G1 → Red Valley rig: bone mapping, rest-pose alignment, scale normalisation to 1.90 m |
| Locomotion | ARDY motion will carry world displacement — must be **converted to in-place** |
| **Pilot scope** | **Exactly two clips: one locomotion (`walk_fwd`) and one farming interaction (`water_can`)**, evaluated before any expansion |

### Licence gate — check before generating

ARDY is NVIDIA-licensed. This project has already lost a full pipeline to
exactly this: the Pixal3D/TRELLIS pilot was abandoned after `nvdiffrast` was
found in the *geometry* path under the Nvidia Source Code License, whose
commercial permission runs one way — to NVIDIA. **ARDY's licence and its
checkpoints' terms must be read and recorded before a single clip is
generated**, and the result written into the provenance record the same way
SPAR3D's `commercial_under_1m` status was.

---

## 4. Still unconfirmed

| Open question | What it changes |
|---|---|
| Does the player ever carry harvested produce? | Adds carry-idle + carry-walk (a second locomotion set) and deposit clips |
| Will hauling/storage replace auto-sell? | Same as above; also a gameplay change, not just animation |
| Is sleeping ever shown? | Adds an enter-bed one-shot; currently an instant clock jump |
| Is dialogue embodied? | Promotes #12 from P2 and may add gestures |
| Will terrain gain relief? | Flat ground needs no foot IK; sloped ground does |
| Does the day-length fix alter action costs? | Changes clip *durations* only, never the set |

---

## Sequencing

1. Define the shared production skeleton + hand socket (blocking).
2. Read and record ARDY's licence (blocking).
3. ARDY pilot: `walk_fwd` + `water_can`, retargeted and evaluated.
4. Only then, the remaining P0 clips.

Nothing is generated, rigged or retargeted before steps 1–2 are settled.
