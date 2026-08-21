# Manual grip — what to do in `MANUAL_GRIP.blend`

Automated closure search is closed as **diminishing returns**. Three attempts got
the middle finger to clean contact (0.3 mm, zero penetration) and eliminated all
can-body collisions, but thumb, index and ring still pass through the handle.
The remaining work is a few minutes of human judgement, not more search.

Open: `art/animation/rigify/grip/MANUAL_GRIP.blend`

> **Corrected 2026-08-20.** The first checkpoint had the arm rotated behind the
> body with the hand at 1.234 m and 0.428 m *behind* the hips — an arm FK sign
> error, the same class of mistake as the finger curl. The arm is now solved with
> IK: hand at 0.820 m, 0.300 m forward, 0.200 m lateral, can upright at 9.1 deg.

## What is already set up

- The realistic can is **rigidly parented to a real `prop_socket.R` bone**, itself
  a child of `DEF-hand.R`. Anything you do to the hand carries the can with it.
- The handle is already seated in the palm channel (49.7 mm channel, 22 mm bar).
- **Only 12 bones are selectable** — `thumb`, `f_index`, `f_middle`, `f_ring`,
  joints `.01/.02/.03`, right side. Everything else is hidden and locked, so you
  cannot disturb the body pose, the mesh or the weights by accident.
- Three cameras: `CAM_PALM`, `CAM_SIDE`, `CAM_THREEQUARTER`.
- The automated pose is the starting point, not a blank hand.

## What to do

In Pose Mode, rotate mainly about **local X** (the curl axis; +X curls, −X opens):

| control | current state | what it needs |
|---|---|---|
| `f_middle.01/.02/.03` | already correct — 0.3 mm contact, no penetration | leave alone, use as reference |
| `f_index.01/.02/.03` | 1.1 mm away but 17 tris penetrating | open slightly until the pad rests on the bar |
| `thumb.01/.02/.03` | 0.6 mm away, 48 tris penetrating (worst) | open, then bring across the bar to oppose the fingers. `thumb.01` also uses **Z** for the sweep across the palm |
| `f_ring.01/.02/.03` | 6.1 mm away, 7 tris penetrating | close a little; its weights are weak so it moves about half as far per degree |
| `f_pinky.*` | unweighted, hidden | nothing — it cannot move and is invisible at gameplay distance |

**Honest estimate: 10–20 minutes.** Four digits, three joints each, judged by eye
against three cameras. The hard part — where the bar sits relative to the palm —
is already solved; this is fine adjustment only.

Do not move the character mesh, and do not touch weights.

## When you are done

Tell me, and I will save the selected finger transforms as a reusable one-frame
pose asset named **`grip_water_can.R`** containing only the 12 finger bones —
no body, no wrist, no root.

## Export / runtime contract

`grip_water_can.R` is a **finger-only additive layer**:

- **Scope:** exactly the 12 right-hand finger bones. It never writes to
  `DEF-hand.R`, the arm, or anything else, so it cannot fight body motion.
- **Application order:** body motion first (ARDY `water_can`, retargeted onto the
  DEF skeleton), then this pose applied to the finger bones only. The wrist and
  arm trajectory belong entirely to the body clip.
- **The can:** parented to `prop_socket.R` under `DEF-hand.R`. It follows the
  wrist rigidly and needs no animation of its own. Measured anchor drift on the
  automated pose: **4.2e-08 m, 0.0000000 deg**.
- **In Godot:** a second `AnimationTree` blend targeting only the finger tracks,
  or simply bake the finger pose into each `water_can` clip at export. The
  contract is the same either way: fingers are static, the arm is animated.

## Superseded: the twisted arm, and what caused it

The user reported the arm and hand looked "all twisted weirdly". They were right.
Three compounding faults, all mine:

1. **Hand targeted below reach.** I aimed the wrist at 0.82 m, but a fully
   extended arm from a 1.558 m shoulder reaches only 0.843 m standing. IK
   therefore locked the elbow straight at **179.9 deg**.
2. **The can hung along the palm normal.** Making it look upright then required
   rolling the wrist ~127 deg. A real can hangs from its bar under gravity,
   independent of hand roll, so the socket's body axis must be **world-down**,
   not the palm normal.
3. **My wrist metric was wrong.** It compared raw forearm and hand matrices,
   whose rest orientations differ by construction, so it reported ~170 deg on a
   perfectly neutral wrist. It now measures deviation from the REST relationship.

`tools/ardy/carry_pose.py` builds the corrected pose:

| measure | before | after |
|---|---|---|
| elbow angle | 179.9 deg (locked) | **142.4 deg** |
| wrist deviation from rest | 127.1 deg | **0.0 deg** |
| can tilt off vertical | 86.4 deg | **0.0 deg** |
| hand/can intersecting tris | 79 | 140 |

The bar axis is now derived as horizontal and perpendicular to the forearm,
rather than from a PCA of the palm slab which could come out near-vertical and
made the world-down projection degenerate.

Finger closure uses **fixed anatomical angles, not a search** — the bar sits in
the grip channel, which is exactly where the fingers are, so any search anchored
at zero closure begins already in contact. 140 intersecting triangles remain.
