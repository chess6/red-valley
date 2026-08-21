"""Pre-spend proofs that the saved constraints actually condition generation.

Runs the SAME code path generate.py runs (load_constraints_lst ->
ArdyMotionRep.create_conditions_from_constraints_batched) and asserts, before
any money is spent, that the tensors are real. to_normalize=False here because
the model's stats ship with the checkpoint; normalisation is an elementwise
affine map and changes neither the mask nor finiteness.

  python3 tools/ardy/prove_constraints.py <ardy_checkout> <constraints.json>
"""
import sys
import torch

ARDY_SRC, CJSON = sys.argv[1], sys.argv[2]
sys.path.insert(0, ARDY_SRC)
from ardy.skeleton.registry import build_skeleton
from ardy.constraints import load_constraints_lst
from ardy.motion_rep.reps.ardy_motionrep import ArdyMotionRep

SK = build_skeleton(27)
BI = SK.bone_index
EXPECT_FRAMES = {0, 8, 64, 72, 80, 152, 159}
fails = []

# -- proof 1: reloads non-empty ----------------------------------------------
lst = load_constraints_lst(CJSON, SK)
print("PROOF 1: reloaded %d constraint sets (non-empty: %s)" % (len(lst), bool(lst)))
if not lst: fails.append("empty constraint list")

# -- proof 2: expected types and frames --------------------------------------
frames = set()
for c in lst:
    frames |= set(int(f) for f in c.frame_indices)
    print("  %-28s frames %-18s joints %s" %
          (type(c).__name__, c.frame_indices.tolist(), c.joint_names))
    if type(c).__name__ != "EndEffectorConstraintSet":
        fails.append("unexpected type %s" % type(c).__name__)
    if set(c.joint_names) != {"RightHand", "RightFoot", "LeftFoot", "Hips"}:
        fails.append("unexpected joints %s" % c.joint_names)
print("PROOF 2: constrained frames %s == expected: %s" %
      (sorted(frames), frames == EXPECT_FRAMES))
if frames != EXPECT_FRAMES: fails.append("frame mismatch")

# -- proofs 3+4: the exact conditioning call generate.py makes ---------------
rep = ArdyMotionRep(SK, fps=20)
lengths = torch.tensor([160])
observed, mask = rep.create_conditions_from_constraints_batched(
    lst, lengths, to_normalize=False, device="cpu")
print("PROOF 3: observed_motion %s, motion_mask %s" %
      (tuple(observed.shape), tuple(mask.shape)))
per_frame = mask[0].sum(dim=1)
masked_frames = set(int(i) for i in torch.nonzero(per_frame).flatten())
print("  masked frames: %s (match: %s)" % (sorted(masked_frames), masked_frames == EXPECT_FRAMES))
if masked_frames != EXPECT_FRAMES: fails.append("mask frames mismatch")

# which feature blocks are masked at a pour frame?
f = 72
for name, sl in rep.slice_dict.items():
    n = int(mask[0, f, sl].sum())
    if n: print("    frame %d: %-24s %d masked entries" % (f, name, n))
need = {"root_pos", "global_root_heading", "local_joints_positions", "global_rot_data"}
have = {name for name, sl in rep.slice_dict.items() if mask[0, f, sl].sum() > 0}
if not need <= have: fails.append("missing feature blocks: %s" % (need - have))
# joint-level check: RightHand & both feet position entries present at frame 72
pos_sl = rep.slice_dict["local_joints_positions"]
pm = mask[0, f, pos_sl].reshape(SK.nbjoints - 1, 3)
pos_joints = {j for j in range(1, SK.nbjoints) if pm[j - 1].any()}
expect_pos = set()
for jn in ("RightHand", "RightFoot", "LeftFoot", "Hips"):
    rj, pj_ = SK.expand_joint_names([jn])
    expect_pos |= {BI[x] for x in pj_ if BI[x] != SK.root_idx}
print("  position-masked joints at f72: %s (expected %s: %s)" %
      (sorted(pos_joints), sorted(expect_pos), pos_joints == expect_pos))
if pos_joints != expect_pos: fails.append("pos joints mismatch")

finite = bool(torch.isfinite(observed).all())
nz = float(observed[mask.bool()].abs().sum())
nz_count = int((observed[mask.bool()].abs() > 1e-8).sum())
print("PROOF 4: observed finite: %s | masked entries %d | nonzero among them %d | L1 %.3f" %
      (finite, int(mask.sum()), nz_count, nz))
if not finite or nz <= 0: fails.append("observed not finite/nonzero")

# -- proof 5: generation receives both tensors (source assertion) ------------
import re
src = open(ARDY_SRC + "/scripts/generate.py").read()
ok5 = ("create_conditions_from_constraints_batched" in src
       and re.search(r"motion_mask=motion_mask", src)
       and re.search(r"observed_motion=observed_motion", src)
       and "load_constraints_lst(args.constraints" in src)
print("PROOF 5: generate.py wires load->conditions->model(motion_mask, observed_motion): %s" % bool(ok5))
if not ok5: fails.append("generate.py wiring missing")

print("RESULT:", "ALL PROOFS PASS" if not fails else "FAILED: %s" % fails)
sys.exit(0 if not fails else 1)
