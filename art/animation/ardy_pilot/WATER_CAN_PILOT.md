# water_can pilot — result

**All three seeds fail. No candidate retargeted.** Cost **$0.09** of a $0.10
cap, one instance, destroyed, account clean.

Baseline in use: `derived/rv_player_proportioned.glb` (accepted). Rodin master
untouched and checksum-verified.

## Target (approved)

spout 0.15–0.30 m above the 0.22 m bed, angled down, not touching · mostly
upright, 8–24° forward lean · hip drop < 0.10 m · both feet planted · right arm
down and forward, can clear of the thigh · left arm relaxed.

Encoded in `tools/ardy/judge_raw.py`, which runs on the raw `.npz` **before**
any retargeting. Sanity-checked: it rejects `bend8_s0` (hip drop 0.301 m,
lean +33.2°, hand 0.092 m from the hip).

## Result — judged raw

| clip | hip drop | trunk lean | hand height | lateral | forward | verdict |
|---|---|---|---|---|---|---|
| water8_00 | 0.003 m | **−15.3°** | **1.052 m** | 0.210 | −0.043 m | FAIL |
| water8_01 | 0.008 m | **−9.2°** | **1.089 m** | 0.224 | +0.014 m | FAIL |
| water8_02 | 0.006 m | **−2.9°** | **1.033 m** | 0.213 | +0.251 m | FAIL |

**They fail the opposite way from the last attempt.** `bend8_s0` was too deep a
crouch; these do not bend at all — hip drop is 3–8 mm, and the trunk leans
*backward* (negative) rather than forward. The right hand never drops below
1.03 m in any frame of any clip, where the target band is 0.55–0.85 m. There is
no pour to crop.

What did work: the hand is held 0.21–0.22 m clear of the hip in all three, so
the "can away from the thigh" requirement is satisfied, and the feet stay
planted 100% of frames.

## Reading

Two attempts now bracket the target without hitting it: prompt for a bend and
ARDY folds to the floor; prompt for a slight lean and it stands upright. This
is consistent with NVIDIA's own statement that **ARDY is not object-aware** —
there is no watering can in the model's world, so "pour onto the soil" carries
no spatial meaning. The pose is defined by *where the hand must be*, and text
cannot specify that.

The next attempt, if any, should drive `water_can` with **end-effector
constraints** rather than wording: ARDY takes reference poses
(`local_joints_rot` + `root_positions` per frame) plus the joints to constrain.
`bend8_s0` and these three now provide real posed clips to build a constraint
from — a hand held at ~0.70 m, forward of the toes, with the trunk at ~15°.

Not attempted here: that is a new generation and needs approval.

## Cost

$0.09 of $0.10. One instance (48170277), destroyed, 0 remaining, balance $9.72.
Prefetching the 16 GB Llama encoder took 17 of the 34 available minutes, which
is why only a single 3-sample batch fit; `--num_samples 3` was used so the
encoder loaded once rather than three times.
