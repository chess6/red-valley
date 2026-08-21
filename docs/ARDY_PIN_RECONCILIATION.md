# ARDY pin reconciliation — the constraint path exists and we never used it

## Pin vs upstream

| | |
|---|---|
| pinned in `tools/ardy/water_remote.sh` | `693f74d13b3d04a0a22ce127ee79c929dd89756b` |
| upstream `nv-tlabs/ardy` HEAD | `693f74d13b3d04a0a22ce127ee79c929dd89756b` |
| commits from pin to HEAD | **0** |

The repository has exactly one commit, "Initial commit", 2026-07-09. **The pin is
not stale and needs no change.** No upstream patch was applied and the pin was
not modified.

## Why local `scripts/generate.py` appeared to lack `--constraints`

It never lacked it. I asserted that from the flags *our own* `water_remote.sh`
passes (`--model`, `--duration`, `--seed`, `--num_samples`), not from ARDY's
source. That was an unfounded inference and it was wrong.

The pinned code carries the entire documented API:

```
scripts/generate.py
  --constraints     "Saved constraint list"
  --cfg_weight      one float (text) or two floats [text_weight, constraint_weight]

ardy/constraints.py
  load_constraints_lst(path_or_data, skeleton)
  save_constraints_lst(path, constraints_lst)
  TYPE_TO_CLASS = root2d, fullbody, left-hand, right-hand,
                  left-foot, right-foot, end-effector
```

and `generate.py` wires it through end to end:

```
216  if args.constraints:
217      constraint_lst = load_constraints_lst(args.constraints, model.skeleton)
244      observed_motion, motion_mask = model.motion_rep.\
             create_conditions_from_constraints_batched(...)
258      motion_mask=motion_mask,
259      observed_motion=observed_motion,
```

**Consequence:** the two earlier `water_can` failures were text-only *by our
choice*, not by ARDY's limitation. The conclusion recorded in
`WATER_CAN_PILOT.md` — that end-effector constraints were "the remaining lever"
— was right, and that lever was available the whole time.

## Local capability, verified without renting anything

- `torch 2.1.2+cu121`, CUDA available
- `ardy.constraints` imports directly from a plain checkout
- the Core skeleton ships in-repo (`ardy/assets/skeletons/cskel27/joints.p`),
  so no checkpoint download is needed to build or validate a constraint file
- `build_skeleton(27)` returns `CoreSkeleton27`, 27 joints, root index 0,
  `RightHand`=10, `RightFoot`=21, `LeftFoot`=25 — matching the joint order
  already committed in `art/animation/ardy_pilot/retarget_map.json`
- `expand_joint_names(["RightHand"])` -> rot `['RightHand']`,
  pos `['RightHand', 'RightHandEnd']`

## Constraint construction requirement

`EndEffectorConstraintSet(skeleton, frame_indices, global_joints_positions,
global_joints_rots, root_2d, *, joint_names)` serialises as `local_joints_rot`
(axis-angle) plus `root_positions`, and `from_dict` rebuilds it through
`skeleton.fk(...)`.

So a constraint keyframe needs a **complete Core-skeleton pose**, not a bare
hand position. Supplying identity rotations would encode the rest pose, not the
watering pose.
