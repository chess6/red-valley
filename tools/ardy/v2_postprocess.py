"""Part A: run ARDY's OWN motion correction on the already-generated clip.

No model is constructed, no text encoder is loaded, no motion is regenerated --
this calls ardy.postprocess.post_process_motion on tensors read straight out of
the existing npz, exactly as scripts/generate.py would have done without
--no-postprocess. Costs nothing and touches no network.

  python3 tools/ardy/v2_postprocess.py <ardy_checkout> <in.npz> <out.npz> <report.json>
"""
import json, sys
import numpy as np
import torch

ARDY, INP, OUTP, REPORT = sys.argv[1:5]
sys.path.insert(0, ARDY)
from ardy.skeleton.registry import build_skeleton
from ardy.postprocess import post_process_motion
from ardy.constraints import load_constraints_lst

SK = build_skeleton(27)
BI = SK.bone_index
d = dict(np.load(INP, allow_pickle=True))
T = lambda k: torch.tensor(d[k]).float()

local = T("local_rot_mats")[None]        # (1,T,J,3,3)
root = T("root_positions")[None]         # (1,T,3)
contacts = T("foot_contacts")[None]      # (1,T,4)
cons = load_constraints_lst("art/animation/ardy_pilot/constraints/water_constraints.json", SK)
print("input: %d frames, %d joints, %d constraint sets"
      % (local.shape[1], local.shape[2], len(cons)))

out = post_process_motion(local, root, contacts, SK, constraint_lst=cons)
print("corrected keys:", sorted(out.keys()))

before_pj = d["posed_joints"]
after_pj = out["posed_joints"][0].numpy()

# --- end-effector error against the constraint targets ---------------------
EE = ["RightHand", "RightFoot", "LeftFoot", "Hips"]
rows = []
for c in cons:
    tgt = c.global_joints_positions
    for i, f in enumerate(c.frame_indices.tolist()):
        for jn in EE:
            j = BI[jn]
            if tgt is None: continue
            t = tgt[i, j].numpy()
            rows.append({"frame": int(f), "joint": jn,
                         "before_m": float(np.linalg.norm(before_pj[f, j] - t)),
                         "after_m": float(np.linalg.norm(after_pj[f, j] - t))})
summary = {}
if rows:
    for jn in EE:
        b = [r["before_m"] for r in rows if r["joint"] == jn]
        a = [r["after_m"] for r in rows if r["joint"] == jn]
        if b:
            summary[jn] = {"before_mean_m": round(float(np.mean(b)), 4),
                           "after_mean_m": round(float(np.mean(a)), 4),
                           "before_max_m": round(float(np.max(b)), 4),
                           "after_max_m": round(float(np.max(a)), 4)}

# --- foot skating: horizontal travel of a foot while ARDY says it is planted
def skate(pj, fc):
    per = {}
    for name, ch in (("LeftFoot", 0), ("RightFoot", 2)):
        j = BI[name]
        planted = fc[:, ch].astype(bool)
        tot, mx = 0.0, 0.0
        for f in range(1, len(planted)):
            if planted[f] and planted[f - 1]:
                s = float(np.linalg.norm(pj[f, j, [0, 2]] - pj[f - 1, j, [0, 2]]))
                tot += s; mx = max(mx, s * 20.0)   # cm/s uses fps=20
        per[name] = {"total_slide_m": round(tot, 4), "peak_slide_cm_s": round(mx * 100, 2)}
    return per
fc = d["foot_contacts"]
before_sk = skate(before_pj, fc)
after_sk = skate(after_pj, out["foot_contacts"][0].numpy() if "foot_contacts" in out else fc)

rep = {"input": INP, "output": OUTP,
       "method": "ardy.postprocess.post_process_motion (official), local CPU, no model load",
       "end_effector_error": summary,
       "foot_skating_before": before_sk, "foot_skating_after": after_sk,
       "max_joint_displacement_m": round(float(np.abs(after_pj - before_pj).max()), 4)}
json.dump(rep, open(REPORT, "w"), indent=2)
print(json.dumps(rep, indent=2))

for k, v in out.items():
    d[k] = v[0].numpy() if hasattr(v, "numpy") else v
np.savez(OUTP, **d)
print("wrote", OUTP)
