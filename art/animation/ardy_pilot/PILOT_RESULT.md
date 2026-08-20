# ARDY two-clip pilot — result

**Verdict: the retarget path works; the two generated clips do not.**
Both are near-static standing poses. Cost **$0.05**, 0.23 h rented, one
instance, destroyed.

## What ran

| Item | Value |
|---|---|
| Hardware | Rented RTX 3090 24 GB (offer 36757265, $0.157/h) — the local 3060 has 12 GB and the LLM2Vec encoder needs ~14 GB |
| Checkpoint | `nvidia/ARDY-Core-RP-20FPS-Horizon40` @ `abe6c43b` |
| Code | `nv-tlabs/ardy` @ `693f74d1` |
| Text encoder | LLM2Vec over `meta-llama/Meta-Llama-3-8B-Instruct` |
| Clips | `walk_fwd`, `water_can` — 40 frames @ 20 fps (2.0 s), seed 0, `--model core` |
| Checksums | verified on copy-back, both OK |

## Measurements — from the raw .npz, before any retargeting

| Signal | walk_fwd | water_can | Expected |
|---|---|---|---|
| Forward speed (normalised to 1.90 m) | **0.30 m/s** | 0.01 m/s | walk ≈ 1.4 m/s; game `WALK_SPEED` 4.3 |
| Hip vertical range | 0.034 m | **0.001 m** | walk 0.03–0.05 m; a deep bend ≈ 0.30 m |
| Right hand lowest point | 0.900 | 0.877 | must reach ≈ 0.45 m to pour onto a 0.22 m bed |
| Foot contacts (of 40 frames) | 28–31 per foot | **40/40** | a walk alternates; 40/40 means never lifted |

`water_can` never bends: hips move 1 mm across the whole clip and both feet stay
planted for every frame. `walk_fwd` is a shuffle, not a gait.

Confirmed independently after retargeting: `hips_z` is constant at 0.9883 across
all 48 frames while `upperarm.R` varies by ~8 mm. The motion is real but
micro-scale.

## The retarget path — works

Three defects were mine, all fixed and recorded:

1. **Rotation composition assumed ARDY's rest pose matched ours.** It does not,
   and the result was a T-pose. Replaced with **position-based aiming**: each
   bone is aimed along the vector between its corresponding ARDY joints, which
   is immune to rest-pose mismatch.
2. **Pose bones were written in dictionary order.** `pb.matrix` is
   armature-space, so a parent written after its child silently invalidates the
   child. Now strictly parent-first.
3. **The acceptance harness read un-evaluated pose data.** `rig.pose` is not
   updated by `frame_set` alone; it must read the depsgraph-evaluated object.

Also recorded: Blender 5.x replaced `Action.fcurves` with layers/slots, and
`ardy.skeleton` pulls torch (absent from Blender's Python), so the joint order
is committed as data in `retarget_map.json` instead of imported.

## Acceptance criteria

| Criterion | walk_fwd | water_can |
|---|---|---|
| Root translation zero (in-place) | PASS | PASS |
| Grip holds on socket | PASS (0.0000 m) | PASS (0.0000 m) |
| Foot slide < 3 cm/step | PASS — but trivially, nothing moves | PASS — trivially |
| Spout within ±5 cm of soil | **FAIL** — 0.406 m above | **FAIL** — 0.247 m above |

The locomotion criteria pass only because the clip is static. They are not
meaningful until a clip with real motion exists.

## Most likely cause, untested

**Duration.** ARDY is autoregressive with a 40-frame horizon, and 2.0 s is
exactly one horizon window — likely dominated by settling from a neutral start.
Upstream's own example uses `--duration 8.0`. A longer generation, cropped to a
clean cycle, is the obvious next test and costs about **$0.05**.

Not yet attempted, per the "exactly two clips before any expansion" instruction.

## What this does not yet show

Nothing about ARDY's ceiling. A 2-second text-only sample from an autoregressive
model is close to its worst case, and the `water_can` result in particular was
predicted: NVIDIA states ARDY is not object-aware, so a grip-and-pour needs
end-effector constraints. Those constraints require reference **poses**
(`local_joints_rot` + `root_positions` per frame), not bare target points — so
they need a usable first pass to build from.

---

# Final bounded diagnostic — 8 s, Core defaults, seeds 0-2

**Result: ARDY is NOT rejected. The 2-second duration was the fault.**
Cost **$0.12** of a $0.15 cap, one instance, destroyed.

## Conditioning check (ran first; abort-on-fail)

Embeddings for "stand still", "walk forward", "bend toward the ground":
shape `(3, 1, 4096)` matching the config's `llm_shape`, all finite, norms
132-138, pairwise cosine 0.66-0.69 (distances 0.31-0.34, threshold 0.01).
**Text conditioning is live and discriminative** — so the static output at 2 s
was never a conditioning failure.

Deviation from the plan, stated plainly: this check could not run before
renting. It needs the 8 B encoder (~16 GB) and this machine has 15 GB RAM /
12 GB VRAM. A local 4-bit approximation would have tested a different code path
and still needed a 16 GB download, so it ran as step 1 on the instance with
abort-and-destroy on failure — same protection, real path, ~$0.005.

## Raw Core motion, judged before retargeting

| clip | m/s | hip range | hand lowest | alternations | verdict |
|---|---|---|---|---|---|
| **walk8_s1** | **1.228** | 0.069 | - | **12** | **PASS** |
| **bend8_s0** | - | **0.301** | **0.153** | - | **PASS** |
| bend8_s1 | - | 0.204 | 0.251 | - | PASS |
| walk8_s0 | 0.077 | 0.040 | - | 2 | FAIL |

Seed 2 was not obtained: each `generate.py` call reloads the 8 B encoder, so six
generations did not fit under the cap. Four of six outputs. `walk8_s2.npz` was
fetched mid-write and came back zero-byte; it is quarantined as
`.truncated` and is **not** counted as a result.

## Cropping

- `walk8_s1`: **no settling to crop** — sustained single-support from frame 0,
  1.228 m/s across the full 7.95 s.
- `bend8_s0`: settles for 0.55 s, hips drop 0.295 m by frame 31, recovers by
  frame 102. Cropped to frames 5-115 (5.5 s).

Nothing was repaired or interpolated.

## Prop

The can was attached **only after** the bend motion existed, and only to the
bend clip; locomotion is judged bare-handed.

## What this changes

1.228 m/s is a believable walking speed — and it is well below the game's
`WALK_SPEED = 4.3`, which reinforces that 4.3 is jogging.
