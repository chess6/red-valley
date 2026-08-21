"""Build the constrained water_can keyframes with ARDY's OWN classes.

Everything goes through ardy.constraints.EndEffectorConstraintSet and
save_constraints_lst -- no hand-written approximate JSON. Poses live on the Core
skeleton and are verified through ardy's own fk.

Why the pour pose is constructed rather than harvested: no existing Core clip
contains the approved pose. The bend clips couple hand-height with 26-47 deg of
trunk lean (they reach by folding the torso), while the approved pose reaches by
extending the arm down-forward at 10-15 deg lean. So the pour pose is built FROM
a real harvested standing frame (water8_00 f0, fk round-trip error 0.000000 m)
by editing a handful of local joint rotations and re-running fk.

Scale note: the approved hand band (0.79-0.85 m) is 1.9 m-character scale. The
Core skeleton's shoulder sits at 1.479 m with a 0.528 m arm, so the SAME pose
(?95% extension, down-forward, 10-15 deg lean) lands the hand at ~0.93-0.97 m.
Rotations, not absolute heights, are what the retarget transfers.

  python3 tools/ardy/build_water_constraints.py <ardy_checkout> <out_json>
"""
import json, math, sys
import numpy as np
import torch

ARDY_SRC, OUT_JSON = sys.argv[1], sys.argv[2]
sys.path.insert(0, ARDY_SRC)
from ardy.skeleton.registry import build_skeleton
from ardy.constraints import EndEffectorConstraintSet, save_constraints_lst, load_constraints_lst
from ardy.motion_rep.tools import compute_heading_angle

SK = build_skeleton(27)
BI = SK.bone_index
NPZ = "art/animation/ardy_pilot/clips_water/water8_00.npz"
FPS, NFRAMES = 20, 160

d = np.load(NPZ)
L0 = torch.tensor(d["local_rot_mats"][0]).clone()      # (27,3,3) standing frame
root0 = torch.tensor(d["root_positions"][0]).clone()

# --- normalize: heading exactly 0, root exactly on the origin (xz) ----------
def fk1(L, root):
    gr, pj, _ = SK.fk(L[None], root[None])
    return gr[0], pj[0]

def Ry(a):
    c, s = math.cos(a), math.sin(a)
    return torch.tensor([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])

_, pj = fk1(L0, root0)
ang = float(compute_heading_angle(pj[None][None], SK)[0])
L0[0] = Ry(-ang) @ L0[0]
root0[0] = 0.0; root0[2] = 0.0
GR_S, PJ_S = fk1(L0, root0)
ang2 = float(compute_heading_angle(PJ_S[None][None], SK)[0])
print("standing pose: heading %.3f -> %.4f deg, root %s" %
      (math.degrees(ang), math.degrees(ang2), np.round(root0.numpy(), 4)))

def lean_deg(pj):
    v = pj[BI["Neck"]] - pj[BI["Hips"]]
    return math.degrees(math.atan2(float(v[[0, 2]].norm()), float(v[1])))

def rot_about_world_axis_at_joint(L, gr, j, axis, deg):
    """Premultiply joint j's GLOBAL rotation by R(axis,deg), expressed locally."""
    a = torch.tensor(axis, dtype=L.dtype); a = a / a.norm()
    th = math.radians(deg)
    K = torch.tensor([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]], dtype=L.dtype)
    R = torch.eye(3, dtype=L.dtype) + math.sin(th) * K + (1 - math.cos(th)) * (K @ K)
    parent = int(SK.joint_parents[j])
    Rp = gr[parent] if parent >= 0 else torch.eye(3, dtype=L.dtype)
    L[j] = Rp.T @ R @ Rp @ L[j]

# --- pour pose: lean the spine to 13 deg visible ----------------------------
LP = L0.clone()
SPINE = [BI[n] for n in ("Spine", "Spine1", "Spine2", "Spine3")]
target_lean = 13.0
step_total = target_lean * 0.55        # visible lean lags applied (hips segment fixed)
for it in range(8):
    gr, pj = fk1(LP, root0)
    err = target_lean - lean_deg(pj)
    if abs(err) < 0.15: break
    for j in SPINE:
        gr, _ = fk1(LP, root0)
        rot_about_world_axis_at_joint(LP, gr, j, (-1.0, 0.0, 0.0), -err * 0.25 * 0.7)
gr, pj = fk1(LP, root0)
print("pour lean: %.2f deg visible (target %.1f)" % (lean_deg(pj), target_lean))

# --- CCD the right arm to the down-forward target ----------------------------
sh = pj[BI["RightArm"]]
reach = float((pj[BI["RightArm"]] - pj[BI["RightForeArm"]]).norm()
              + (pj[BI["RightForeArm"]] - pj[BI["RightHand"]]).norm())
ddir = torch.tensor([-0.10, -0.92, 0.38]); ddir = ddir / ddir.norm()
target = sh + ddir * (reach * 0.95)
print("hand target %s (shoulder %s, reach %.3f)" %
      (np.round(target.numpy(), 3), np.round(sh.numpy(), 3), reach))
CHAIN_J = [BI["RightArm"], BI["RightForeArm"]]
for it in range(40):
    for j in reversed(CHAIN_J):
        gr, pj = fk1(LP, root0)
        h = pj[BI["RightHand"]]
        o = pj[j]
        v1, v2 = h - o, target - o
        if v1.norm() < 1e-6 or v2.norm() < 1e-6: continue
        axis = torch.cross(v1, v2)
        if axis.norm() < 1e-8: continue
        angd = math.degrees(math.acos(float(torch.clamp(
            (v1 @ v2) / (v1.norm() * v2.norm()), -1.0, 1.0))))
        rot_about_world_axis_at_joint(LP, gr, j, tuple(axis.tolist()), min(angd, 14.0))
    gr, pj = fk1(LP, root0)
    if float((pj[BI["RightHand"]] - target).norm()) < 2e-3: break
gr, pj = fk1(LP, root0)
# wrist: pitch the hand down so the pour reads through the retarget
rot_about_world_axis_at_joint(LP, gr, BI["RightHand"], (-1.0, 0.0, 0.0), -32.0)
GR_P, PJ_P = fk1(LP, root0)

hand = PJ_P[BI["RightHand"]]
print("pour achieved: hand (%.3f, %.3f, %.3f)  err %.4f m  lean %.2f deg" %
      (hand[0], hand[1], hand[2], float((hand - target).norm()), lean_deg(PJ_P)))
for side in ("RightFoot", "LeftFoot"):
    dfoot = float((PJ_P[BI[side]] - PJ_S[BI[side]]).norm())
    assert dfoot < 1e-4, "%s moved %.5f m" % (side, dfoot)
print("feet: identical to standing pose (legs untouched); hips drop %.4f m"
      % float(PJ_S[BI["Hips"]][1] - PJ_P[BI["Hips"]][1]))

# --- assemble ARDY constraint sets ------------------------------------------
JOINTS = ["RightHand", "RightFoot", "LeftFoot", "Hips"]
PHASES = [("start", PJ_S, GR_S, [0, 8]),
          ("pour", PJ_P, GR_P, [64, 72, 80]),
          ("return", PJ_S, GR_S, [152, 159])]
sets = []
for name, PJ, GR, frames in PHASES:
    n = len(frames)
    cs = EndEffectorConstraintSet(
        SK,
        torch.tensor(frames),
        PJ[None].repeat(n, 1, 1),
        GR[None].repeat(n, 1, 1, 1),
        None,
        joint_names=JOINTS,
    )
    sets.append(cs)
    print("constraint '%s': frames %s, joints %s" % (name, frames, JOINTS))
save_constraints_lst(OUT_JSON, sets)
print("saved:", OUT_JSON)

# record the achieved pour numbers for the retarget-side validation
meta = {
    "source_standing_frame": {"npz": NPZ, "frame": 0},
    "core_scale_note": "hand heights are Core-skeleton scale (shoulder 1.479 m, arm 0.528 m)",
    "pour": {"hand": [round(float(x), 4) for x in hand],
             "visible_lean_deg": round(lean_deg(PJ_P), 2),
             "hips_y": round(float(PJ_P[BI["Hips"]][1]), 4)},
    "phases": {n: f for n, _, _, f in PHASES},
    "joints": JOINTS,
}
json.dump(meta, open(OUT_JSON.replace(".json", "_meta.json"), "w"), indent=2)
print("BUILD_DONE")
