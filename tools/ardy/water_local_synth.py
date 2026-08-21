"""Local fallback: synthesize the water_can Core clip from the verified poses.

Used only if the constrained ARDY candidate fails. Same standing and pour poses
that the constraints were built from (constructed and numerically verified in
build_water_constraints.py), interpolated in local-rotation space with
smoothstep easing, run through ardy's own fk. The output npz has the same
layout as an ARDY clip, so build_water_clip.py consumes it unchanged.

  python3 tools/ardy/water_local_synth.py <ardy_checkout> <out_npz>
"""
import math, sys
import numpy as np
import torch

ARDY_SRC, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, ARDY_SRC)
from ardy.skeleton.registry import build_skeleton
from ardy.motion_rep.tools import compute_heading_angle

SK = build_skeleton(27)
BI = SK.bone_index
FPS, F = 20, 160

d = np.load("art/animation/ardy_pilot/clips_water/water8_00.npz")
L0 = torch.tensor(d["local_rot_mats"][0]).clone()
root0 = torch.tensor(d["root_positions"][0]).clone()

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

# Abduct the right arm ~9 deg so the hanging can clears the thigh: the Core
# standing pose holds the arm straight at the side, and the attached can body
# intersected the leg (139 overlap tris at the carry frames).
GR_S, PJ_S = fk1(L0, root0)
def lean_deg(pj_):
    v = pj_[BI["Neck"]] - pj_[BI["Hips"]]
    return math.degrees(math.atan2(float(v[[0, 2]].norm()), float(v[1])))
def rot_at(L, gr, j, axis, deg):
    a = torch.tensor(axis, dtype=L.dtype); a = a / a.norm()
    th = math.radians(deg)
    K = torch.tensor([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]], dtype=L.dtype)
    R = torch.eye(3, dtype=L.dtype) + math.sin(th) * K + (1 - math.cos(th)) * (K @ K)
    p = int(SK.joint_parents[j])
    Rp = gr[p] if p >= 0 else torch.eye(3, dtype=L.dtype)
    L[j] = Rp.T @ R @ Rp @ L[j]

rot_at(L0, GR_S, BI["RightArm"], (0.0, 0.0, 1.0), -9.0)
GR_S, PJ_S = fk1(L0, root0)
print("abducted right hand at carry: x=%.3f (was -0.242)" % float(PJ_S[BI["RightHand"]][0]))

LP = L0.clone()
SPINE = [BI[n] for n in ("Spine", "Spine1", "Spine2", "Spine3")]
for it in range(8):
    gr, pj = fk1(LP, root0)
    err = 13.0 - lean_deg(pj)
    if abs(err) < 0.15: break
    for j in SPINE:
        gr, _ = fk1(LP, root0)
        rot_at(LP, gr, j, (-1.0, 0.0, 0.0), -err * 0.25 * 0.7)
gr, pj = fk1(LP, root0)
sh = pj[BI["RightArm"]]
reach = float((pj[BI["RightArm"]] - pj[BI["RightForeArm"]]).norm()
              + (pj[BI["RightForeArm"]] - pj[BI["RightHand"]]).norm())
ddir = torch.tensor([-0.10, -0.90, 0.435]); ddir = ddir / ddir.norm()
target = sh + ddir * (reach * 0.95)
for it in range(40):
    for j in reversed([BI["RightArm"], BI["RightForeArm"]]):
        gr, pj = fk1(LP, root0)
        h = pj[BI["RightHand"]]; o = pj[j]
        v1, v2 = h - o, target - o
        ax = torch.cross(v1, v2)
        if ax.norm() < 1e-8: continue
        angd = math.degrees(math.acos(float(torch.clamp(
            (v1 @ v2) / (v1.norm() * v2.norm()), -1.0, 1.0))))
        rot_at(LP, gr, j, tuple(ax.tolist()), min(angd, 14.0))
    gr, pj = fk1(LP, root0)
    if float((pj[BI["RightHand"]] - target).norm()) < 2e-3: break
rot_at(LP, gr, BI["RightHand"], (-1.0, 0.0, 0.0), -32.0)

# --- timeline: stand 0-8, ease to pour by 56, hold to 96, ease back by 150 ---
from ardy.geometry import matrix_to_axis_angle, axis_angle_to_matrix
A0 = matrix_to_axis_angle(L0)
AP = matrix_to_axis_angle(LP)
def smoothstep(t): return t * t * (3 - 2 * t)
def blend(w):  # per-joint axis-angle lerp is fine for these small deltas
    return axis_angle_to_matrix(A0 * (1 - w) + AP * w)
frames = []
for f in range(F):
    if f < 8: w = 0.0
    elif f < 56: w = smoothstep((f - 8) / 48.0)
    elif f < 96: w = 1.0
    elif f < 150: w = 1.0 - smoothstep((f - 96) / 54.0)
    else: w = 0.0
    frames.append(blend(w))
L = torch.stack(frames)
roots = root0[None].repeat(F, 1)
GR, PJ, _ = SK.fk(L, roots)
heading = compute_heading_angle(PJ[None], SK)[0]
np.savez(OUT,
         local_rot_mats=L.numpy(), global_rot_mats=GR.numpy(),
         posed_joints=PJ.numpy(), root_positions=roots.numpy(),
         smooth_root_pos=roots.numpy(),
         foot_contacts=np.ones((F, 4), dtype=np.float32),
         global_root_heading=np.stack([np.cos(heading.numpy()), np.sin(heading.numpy())], 1),
         fps=FPS, text=np.array("local synthesis from approved poses"))
print("synthesized %d frames -> %s" % (F, OUT))
print("pour hand:", np.round(PJ[76, BI["RightHand"]].numpy(), 3),
      "lean %.1f deg" % lean_deg(PJ[76]))
