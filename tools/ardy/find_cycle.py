"""Find a genuine stride-cycle interval in the retargeted walk.

Contiguous source frames only -- no pose repair, no invented interpolation. The
cycle is chosen by minimising the POSE and VELOCITY seam between the first and
last frame, restricted to candidates that are a true same-foot stride apart.

  blender --background <walk_rigify.blend> --python find_cycle.py -- <json_out>
"""
import json, math, sys
import bpy
from mathutils import Vector

OUT = sys.argv[sys.argv.index("--") + 1:][0]
rig = bpy.data.objects["rv_rigify"]
PB = rig.pose.bones
sc = bpy.context.scene
DEF = [b.name for b in rig.data.bones if b.name.startswith("DEF-")]
F0, F1 = int(sc.frame_start), int(sc.frame_end)

def sample(f):
    sc.frame_set(f); bpy.context.view_layer.update()
    return {n: (rig.matrix_world @ PB[n].matrix).to_translation() for n in DEF}

P = {f: sample(f) for f in range(F0, F1 + 1)}
zR = {f: P[f]["DEF-foot.R"].z for f in P}
zL = {f: P[f]["DEF-foot.L"].z for f in P}
loR, loL = min(zR.values()), min(zL.values())
thr = 0.020
conR = {f: zR[f] < loR + thr for f in P}
conL = {f: zL[f] < loL + thr for f in P}

def rising_edges(con):
    e = []
    fs = sorted(con)
    for i in range(1, len(fs)):
        if con[fs[i]] and not con[fs[i - 1]]: e.append(fs[i])
    return e
eR, eL = rising_edges(conR), rising_edges(conL)
print("right-foot contact starts: %s" % eR)
print("left-foot contact starts:  %s" % eL)

def pose_seam(a, b):
    return max((P[a][n] - P[b][n]).length for n in DEF)
def vel_seam(a, b):
    va = {n: P[min(a + 1, F1)][n] - P[a][n] for n in DEF}
    vb = {n: P[b][n] - P[max(b - 1, F0)][n] for n in DEF}
    return max((va[n] - vb[n]).length for n in DEF)

cands = []
for i in range(len(eR) - 1):
    for j in range(i + 1, len(eR)):
        a, b = eR[i], eR[j] - 1          # inclusive interval, one full stride
        if b - a < 12: continue
        cands.append((pose_seam(a, b) + 4.0 * vel_seam(a, b), a, b,
                      pose_seam(a, b), vel_seam(a, b)))
cands.sort()
if not cands:
    print("NO CYCLE CANDIDATES"); raise SystemExit
print("best stride-cycle candidates (contiguous, same-foot to same-foot):")
for s, a, b, ps, vs in cands[:5]:
    n = b - a + 1
    print("   frames %3d..%3d  (%3d frames, %.2f s)  pose seam %.4f m  vel seam %.4f m"
          % (a, b, n, n / 20.0, ps, vs))
_, A, B, ps, vs = cands[0]
json.dump({"start": A, "end": B, "frames": B - A + 1,
           "seconds": round((B - A + 1) / 20.0, 3),
           "pose_seam_m": round(ps, 5), "vel_seam_m": round(vs, 5),
           "right_contact_starts": eR, "left_contact_starts": eL},
          open(OUT, "w"), indent=2)
print("CHOSEN %d..%d" % (A, B))
