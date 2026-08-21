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
