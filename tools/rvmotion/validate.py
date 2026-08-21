"""Machine-readable validation for a retargeted clip. One script, one JSON.

Covers: DEF rotation fidelity, wrist position/orientation, foot contact honouring
and skating, loop seam, prop rigidity/collisions, spout placement and water
timing, split face-landmark gates, and (separately) GLB round-trip.

  blender --background <clip.blend> --python validate.py -- <base.rvm> <out.json> \
      [--can] [--soil 0.22] [--loop] [--label NAME]
"""
import json, math, os, sys
import bpy, numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

A = sys.argv[sys.argv.index("--") + 1:]
BASE, OUT = A[0], A[1]
HAS_CAN = "--can" in A
IS_LOOP = "--loop" in A
TREADMILL = float(next((A[i + 1] for i, x in enumerate(A) if x == "--treadmill"), 0.0))
TREAD_DIR = next((A[i + 1] for i, x in enumerate(A) if x == "--tread-dir"), "0,1")
SOIL = float(next((A[i + 1] for i, x in enumerate(A) if x == "--soil"), 0.22))
LABEL = next((A[i + 1] for i, x in enumerate(A) if x == "--label"), os.path.basename(BASE))
sys.path.insert(0, os.path.join(os.getcwd(), "tools"))
from rvmotion.canonical import RVMotion, quat_to_mat  # noqa: E402

m = RVMotion.load(BASE)
G = quat_to_mat(m.global_quat); POS = m.positions; JN = m.joints
rig = bpy.data.objects["rv_rigify"]
PB = rig.pose.bones; W = rig.matrix_world
sc = bpy.context.scene
def upd(): bpy.context.view_layer.update()
def np2m(a): return Matrix(tuple(tuple(float(x) for x in r) for r in a))
def angdiff(P, Q):
    q = (P.transposed() @ Q).to_quaternion(); a = abs(q.angle)
    return math.degrees(min(a, 2 * math.pi - a))
def wm(n): return W @ PB[n].matrix

N = sc.frame_end - sc.frame_start + 1
T = min(N, m.num_frames)
SAMPLE = list(range(T))
R = {"label": LABEL, "frames": T, "fps": sc.render.fps}

meshes = [o for o in bpy.data.objects if o.type == "MESH"]
can = next((o for o in meshes if "can" in o.name.lower()), None) if HAS_CAN else None
body = max([o for o in meshes if o is not can], key=lambda o: len(o.data.vertices))

# ---------- 1. rotation fidelity (calibration-independent deltas) ----------
DEF_MAP = {"Spine": "DEF-spine", "Spine1": "DEF-spine.001", "Spine2": "DEF-spine.002",
           "Spine3": "DEF-spine.003", "Neck": "DEF-spine.004", "Head": "DEF-spine.006",
           "RightArm": "DEF-upper_arm.R", "RightForeArm": "DEF-forearm.R",
           "RightHand": "DEF-hand.R", "LeftArm": "DEF-upper_arm.L",
           "LeftForeArm": "DEF-forearm.L", "LeftHand": "DEF-hand.L",
           "RightUpLeg": "DEF-thigh.R", "RightLeg": "DEF-shin.R", "RightFoot": "DEF-foot.R",
           "LeftUpLeg": "DEF-thigh.L", "LeftLeg": "DEF-shin.L", "LeftFoot": "DEF-foot.L"}
TRACK = set(DEF_MAP.values()) | {"DEF-upper_arm.R.001", "DEF-forearm.R.001",
                                 "DEF-upper_arm.L.001", "DEF-forearm.L.001"}
rot, pos = {}, {}
canm = {}
for f in SAMPLE:
    sc.frame_set(sc.frame_start + f); upd()
    for d in TRACK:
        if d in PB:
            mm = wm(d); rot.setdefault(d, {})[f] = mm.to_3x3(); pos.setdefault(d, {})[f] = mm.to_translation()
    if can is not None: canm[f] = can.matrix_world.copy()

err = {}
for j, d in DEF_MAP.items():
    if d not in rot: continue
    for a, b in zip(SAMPLE[:-1], SAMPLE[1:]):
        ds = np2m(G[b, JN.index(j)]) @ np2m(G[a, JN.index(j)]).transposed()
        err.setdefault(d, []).append(angdiff(ds, rot[d][b] @ rot[d][a].transposed()))
R["rotation_fidelity"] = {
    "per_bone_deg": {k: {"mean": round(float(np.mean(v)), 2), "max": round(float(np.max(v)), 2)}
                     for k, v in err.items()},
    "overall_mean_deg": round(float(np.mean([x for v in err.values() for x in v])), 3),
    "overall_max_deg": round(float(np.max([x for v in err.values() for x in v])), 3),
    "gate_mean_lt_2deg": bool(np.mean([x for v in err.values() for x in v]) < 2.0)}

# twist channel actually carrying signal
R["twist_channel"] = {d: {"range_deg": round(float(np.ptp(
    [angdiff(rot[d][SAMPLE[0]], rot[d][f]) for f in SAMPLE])), 2)}
    for d in TRACK if d.endswith(".001") and d in rot}

# ---------- 2. wrist position + orientation --------------------------------
wr = {}
for side, jn, d in (("R", "RightHand", "DEF-hand.R"), ("L", "LeftHand", "DEF-hand.L")):
    if d not in rot: continue
    j = JN.index(jn)
    # scale-normalised position error relative to the hips, both sides
    ph = np.array([list(pos[d][f] - wm("DEF-spine").to_translation()) for f in SAMPLE])
    sh = POS[SAMPLE][:, j] - POS[SAMPLE][:, JN.index("Hips")]
    wr[side] = {"pos_rms_vs_source_m": round(float(np.sqrt(((ph - sh) ** 2).sum(1).mean())), 4),
                "orientation_delta_err_max_deg": round(float(np.max(
                    [angdiff(np2m(G[b, j]) @ np2m(G[a, j]).transposed(),
                             rot[d][b] @ rot[d][a].transposed())
                     for a, b in zip(SAMPLE[:-1], SAMPLE[1:])])), 2)}
R["wrist"] = wr

# ---------- 3. foot contacts + skating -------------------------------------
ch = {n: i for i, n in enumerate(m.contact_channels)}
sk = {}
for side, cn, d in (("L", "LeftFoot", "DEF-foot.L"), ("R", "RightFoot", "DEF-foot.R")):
    if d not in pos: continue
    on = m.contacts[SAMPLE, ch[cn]].astype(bool)
    tot, peak, n_planted = 0.0, 0.0, int(on.sum())
    # In an in-place clip the planted foot SHOULD travel backwards at exactly the
    # locomotion speed -- the ground is what moves. Skating is the residual after
    # that expected treadmill motion is removed; measuring absolute stillness
    # would score the moonwalk bug as perfect.
    tdx, tdy = [float(x) for x in TREAD_DIR.split(",")]
    step = TREADMILL / sc.render.fps
    exp = Vector((-tdx * step, -tdy * step, 0.0))
    for f in range(1, len(SAMPLE)):
        if on[f] and on[f - 1]:
            p0, p1 = pos[d][SAMPLE[f - 1]], pos[d][SAMPLE[f]]
            dv = Vector((p1.x - p0.x, p1.y - p0.y, 0.0)) - exp
            s = dv.length
            tot += s; peak = max(peak, s * sc.render.fps)
    sk[side] = {"planted_frames": n_planted,
                "total_slide_m": round(tot, 4),
                "peak_slide_cm_per_s": round(peak * 100, 2),
                "mean_slide_cm_per_s": round((tot * sc.render.fps / max(1, n_planted)) * 100, 2)}
R["foot_contacts"] = {"source_labels_used": True, "per_foot": sk,
                      "treadmill_speed_mps": TREADMILL,
                      "gate_peak_slide_lt_5cm_s": all(v["peak_slide_cm_per_s"] < 5.0 for v in sk.values())}

# ---------- 4. loop seam (on the delivered rig, not just the source) -------
if IS_LOOP:
    def bsz(f):
        h = pos["DEF-spine"][f]
        return np.array([[p[f].x - h.x, p[f].y - h.y, p[f].z - h.z] for p in pos.values()])
    pred = 2.0 * bsz(SAMPLE[-1]) - bsz(SAMPLE[-2])
    seam = float(np.linalg.norm(bsz(SAMPLE[0]) - pred, axis=1).max())
    inner = float(np.linalg.norm(bsz(SAMPLE[2]) - (2.0 * bsz(SAMPLE[1]) - bsz(SAMPLE[0])), axis=1).max())
    R["loop_seam"] = {"seam_extrapolation_err_m": round(seam, 5),
                      "interior_extrapolation_err_m": round(inner, 5),
                      "gate_documented_lt_1cm": seam < 0.01,
                      "gate_proposed_no_worse_than_interior": seam <= inner}

# ---------- 5. prop: rigidity, spout, collisions ---------------------------
if can is not None:
    META = json.load(open("art/animation/ardy_pilot/proxy/watering_can_proxy.json"))
    TIP = Vector(META["markers"]["spout_tip"])
    hand0 = rot["DEF-hand.R"][SAMPLE[0]].to_4x4()
    hand0.translation = pos["DEF-hand.R"][SAMPLE[0]]
    rel0 = hand0.inverted() @ canm[SAMPLE[0]]
    drift_p = drift_r = 0.0
    tips = []
    for f in SAMPLE:
        hm = rot["DEF-hand.R"][f].to_4x4(); hm.translation = pos["DEF-hand.R"][f]
        rel = hm.inverted() @ canm[f]
        drift_p = max(drift_p, (rel.to_translation() - rel0.to_translation()).length)
        drift_r = max(drift_r, math.degrees(
            rel.to_quaternion().rotation_difference(rel0.to_quaternion()).angle))
        tips.append(canm[f] @ TIP)
    R["prop_rigidity"] = {"max_hand_relative_drift_m": round(drift_p, 9),
                          "max_hand_relative_drift_deg": round(drift_r, 6),
                          "gate_rigid": drift_p < 1e-4 and drift_r < 0.05}
    zs = [t.z - SOIL for t in tips]
    lo = float(min(zs)); hi = float(max(zs))
    R["spout"] = {"min_above_bed_m": round(lo, 4), "max_above_bed_m": round(hi, 4),
                  "documented_band_m": [0.15, 0.30],
                  "frames_in_band": int(sum(1 for z in zs if 0.15 <= z <= 0.30)),
                  "gate_in_band": bool(any(0.15 <= z <= 0.30 for z in zs))}
    # collisions, hand region excluded (that is the grip, judged separately)
    GIx = {g.name: g.index for g in body.vertex_groups}
    GN = {i: n for n, i in GIx.items()}
    body.data.calc_loop_triangles()
    def dom(vi):
        v = body.data.vertices[vi]
        return GN.get(max(v.groups, key=lambda g: g.weight).group) if v.groups else None
    HK = ("DEF-hand.R", "DEF-f_", "DEF-thumb", "DEF-palm")
    NONHAND = [t for t in body.data.loop_triangles
               if not any((dom(i) or "").startswith(HK) for i in t.vertices)]
    coll = {}
    for f in SAMPLE[::max(1, len(SAMPLE) // 12)]:
        sc.frame_set(sc.frame_start + f); upd()
        dg = bpy.context.evaluated_depsgraph_get()
        ev = body.evaluated_get(dg); bm = ev.to_mesh()
        bt = BVHTree.FromPolygons([body.matrix_world @ v.co for v in bm.vertices],
                                  [tuple(t.vertices) for t in NONHAND], all_triangles=True)
        cev = can.evaluated_get(dg); cm = cev.to_mesh(); cm.calc_loop_triangles()
        ct = BVHTree.FromPolygons([can.matrix_world @ v.co for v in cm.vertices],
                                  [tuple(t.vertices) for t in cm.loop_triangles], all_triangles=True)
        ov = ct.overlap(bt)
        parts = {}
        for _c, bi in ov:
            for vi in NONHAND[bi].vertices:
                n = dom(vi); parts[n] = parts.get(n, 0) + 1
        coll[f] = {"tris": len(ov), "by_bone": parts}
        ev.to_mesh_clear(); cev.to_mesh_clear()
    R["collisions"] = {"per_frame": coll,
                       "max_tris": max(v["tris"] for v in coll.values()),
                       "gate_zero": all(v["tris"] == 0 for v in coll.values())}

# ---------- 6. face: rigid core vs blend band, measured separately ---------
GIx = {g.name: g.index for g in body.vertex_groups}
hi_, ni_ = GIx.get("DEF-spine.006"), GIx.get("DEF-spine.004")
def wt(v, gi): return next((g.weight for g in v.groups if g.group == gi), 0.0)
core = [v.index for v in body.data.vertices if wt(v, hi_) > 0.999 and wt(v, ni_) == 0.0]
band = [v.index for v in body.data.vertices if wt(v, hi_) > 0.01 and wt(v, ni_) > 0.01]
cs, bs_ = set(core), set(band)
ec = [e for e in body.data.edges if e.vertices[0] in cs and e.vertices[1] in cs][:4000]
eb = [e for e in body.data.edges if e.vertices[0] in bs_ and e.vertices[1] in bs_][:4000]
def co_():
    dg = bpy.context.evaluated_depsgraph_get(); ev = body.evaluated_get(dg); mm = ev.to_mesh()
    r = [body.matrix_world @ mm.vertices[i].co for i in range(len(mm.vertices))]
    ev.to_mesh_clear(); return r
sc.frame_set(sc.frame_start); upd(); c0 = co_()
bc = [(c0[e.vertices[0]] - c0[e.vertices[1]]).length for e in ec]
bb = [(c0[e.vertices[0]] - c0[e.vertices[1]]).length for e in eb]
wc = wb = 0.0
for f in SAMPLE[::max(1, len(SAMPLE) // 8)]:
    sc.frame_set(sc.frame_start + f); upd(); cc = co_()
    if bc: wc = max(wc, max(abs((cc[e.vertices[0]] - cc[e.vertices[1]]).length - b) / b
                            for e, b in zip(ec, bc) if b > 1e-6))
    if bb: wb = max(wb, max(abs((cc[e.vertices[0]] - cc[e.vertices[1]]).length - b) / b
                            for e, b in zip(eb, bb) if b > 1e-6))
R["face"] = {"rigid_core_verts": len(core), "blend_band_verts": len(band),
             "core_worst_strain_pct": round(wc * 100, 4),
             "band_worst_strain_pct": round(wb * 100, 4),
             "gate_core_rigid_lt_0p5pct": wc * 100 < 0.5,
             "gate_band_lt_25pct": wb * 100 < 25.0,
             "note": "aggregate 'face deviation' retired: it mixed these populations"}

json.dump(R, open(OUT, "w"), indent=2)
print(json.dumps({k: (v if not isinstance(v, dict) or len(str(v)) < 400 else "...")
                  for k, v in R.items()}, indent=2)[:1800])
print("VALIDATE_DONE", OUT)
