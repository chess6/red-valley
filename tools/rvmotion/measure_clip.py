"""Measure any animated rv_rigify blend against the canonical source it claims
to reproduce. Works on v1 and v2 output alike, so the two are comparable.

  blender --background <clip.blend> --python measure_clip.py -- <base.rvm> <out.json> [label]
"""
import json, math, os, sys
import bpy, numpy as np
from mathutils import Matrix, Vector

A = sys.argv[sys.argv.index("--") + 1:]
BASE, OUT = A[0], A[1]
LABEL = A[2] if len(A) > 2 else os.path.basename(BASE)
sys.path.insert(0, os.path.join(os.getcwd(), "tools"))
from rvmotion.canonical import RVMotion, quat_to_mat  # noqa: E402

m = RVMotion.load(BASE)
G = quat_to_mat(m.global_quat); POS = m.positions; JN = m.joints; T = m.num_frames
rig = bpy.data.objects["rv_rigify"]
PB = rig.pose.bones; W = rig.matrix_world
sc = bpy.context.scene
def upd(): bpy.context.view_layer.update()
def np2m(a): return Matrix(tuple(tuple(float(x) for x in r) for r in a))
def angdiff(P, Q):
    q = (P.transposed() @ Q).to_quaternion(); a = abs(q.angle)
    return math.degrees(min(a, 2 * math.pi - a))

DEF_MAP = {"Spine": "DEF-spine", "Spine1": "DEF-spine.001", "Spine2": "DEF-spine.002",
           "Spine3": "DEF-spine.003", "Neck": "DEF-spine.004", "Head": "DEF-spine.006",
           "RightArm": "DEF-upper_arm.R", "RightForeArm": "DEF-forearm.R",
           "RightHand": "DEF-hand.R", "LeftArm": "DEF-upper_arm.L",
           "LeftForeArm": "DEF-forearm.L", "LeftHand": "DEF-hand.L",
           "RightUpLeg": "DEF-thigh.R", "RightLeg": "DEF-shin.R", "RightFoot": "DEF-foot.R",
           "LeftUpLeg": "DEF-thigh.L", "LeftLeg": "DEF-shin.L", "LeftFoot": "DEF-foot.L"}
# the clip may be a crop of the source; align by length
n = min(T, sc.frame_end - sc.frame_start + 1)
SAMPLE = list(range(0, n, max(1, n // 40)))
got = {}
for f in SAMPLE:
    sc.frame_set(sc.frame_start + f); upd()
    for d in set(DEF_MAP.values()) | {"DEF-upper_arm.R.001", "DEF-forearm.R.001"}:
        if d in PB: got.setdefault(d, {})[f] = (W @ PB[d].matrix).to_3x3()

err = {}
for j, d in DEF_MAP.items():
    if d not in got: continue
    for a, b in zip(SAMPLE[:-1], SAMPLE[1:]):
        ds = np2m(G[b, JN.index(j)]) @ np2m(G[a, JN.index(j)]).transposed()
        dt = got[d][b] @ got[d][a].transposed()
        err.setdefault(d, []).append(angdiff(ds, dt))

def roll_range(jn, dbone, child):
    if dbone not in got: return None
    js, jc = JN.index(jn), JN.index(child)
    s, t = [], []
    for f in SAMPLE:
        ax = POS[f, jc] - POS[f, js]
        nn = np.linalg.norm(ax)
        if nn < 1e-9: continue
        av = Vector((ax / nn).tolist())
        for src, dst in ((np2m(G[f, js]) @ np2m(G[SAMPLE[0], js]).transposed(), s),
                         (got[dbone][f] @ got[dbone][SAMPLE[0]].transposed(), t)):
            q = src.to_quaternion()
            dst.append(math.degrees(q.to_axis_angle()[1] * (1 if q.axis.dot(av) > 0 else -1)))
    return {"source_deg": round(float(np.ptp(s)), 2), "target_deg": round(float(np.ptp(t)), 2)}

# twist-bone activity: a static twist bone is the v1 signature
twist_activity = {}
for d in ("DEF-upper_arm.R.001", "DEF-forearm.R.001"):
    if d in got:
        vals = [angdiff(got[d][SAMPLE[0]], got[d][f]) for f in SAMPLE]
        twist_activity[d] = {"range_deg": round(float(np.ptp(vals)), 3)}

rep = {"label": LABEL, "frames_measured": len(SAMPLE),
       "def_motion_delta_error_deg": {k: {"mean": round(float(np.mean(v)), 2),
                                          "max": round(float(np.max(v)), 2)}
                                      for k, v in err.items()},
       "worst_delta_err_deg": round(max(max(v) for v in err.values()), 2) if err else None,
       "mean_delta_err_deg": round(float(np.mean([x for v in err.values() for x in v])), 2) if err else None,
       "forearm_roll_range_deg": {"R": roll_range("RightForeArm", "DEF-forearm.R", "RightHand"),
                                  "L": roll_range("LeftForeArm", "DEF-forearm.L", "LeftHand")},
       "twist_bone_activity": twist_activity}
json.dump(rep, open(OUT, "w"), indent=2)
print(json.dumps(rep, indent=2)[:1400])
print("MEASURE_DONE")
