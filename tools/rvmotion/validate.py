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
PW = next((A[i + 1] for i, x in enumerate(A) if x == "--pour-window"), None)
POUR_WINDOW = [int(x) for x in PW.split(",")] if PW else None
TREAD_DIR = next((A[i + 1] for i, x in enumerate(A) if x == "--tread-dir"), "0,1")
SOIL = float(next((A[i + 1] for i, x in enumerate(A) if x == "--soil"), 0.22))
LABEL = next((A[i + 1] for i, x in enumerate(A) if x == "--label"), os.path.basename(BASE))
# Bones deliberately overridden by an authored layer (hand IK to reach the spout,
# the wrist pour). Their deviation from source is the POINT, so it is reported
# with its magnitude and excluded from the breach gate rather than averaged away
# or silently tolerated.
AUTHORED = [x for x in (next((A[i + 1] for i, y in enumerate(A) if y == "--authored"), "")).split(",") if x]
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
    # per-frame root reference; sampling this outside the loop compared every
    # wrist against one arbitrary frame's spine and made the RMS meaningless
    pos.setdefault("__root__", {})[f] = wm("DEF-spine").to_translation()
    if can is not None: canm[f] = can.matrix_world.copy()

err = {}
for j, d in DEF_MAP.items():
    if d not in rot: continue
    for a, b in zip(SAMPLE[:-1], SAMPLE[1:]):
        ds = np2m(G[b, JN.index(j)]) @ np2m(G[a, JN.index(j)]).transposed()
        err.setdefault(d, []).append(angdiff(ds, rot[d][b] @ rot[d][a].transposed()))
# Per-critical-bone limits. An overall mean is not a gate: the water clip's
# right arm can be 30 deg wrong while the average stays under 1 deg, because
# 18 well-behaved bones outvote the two that carry the task.
CRITICAL = {"DEF-upper_arm.R": 8.0, "DEF-forearm.R": 8.0, "DEF-hand.R": 8.0,
            "DEF-upper_arm.L": 8.0, "DEF-forearm.L": 8.0, "DEF-hand.L": 8.0,
            "DEF-thigh.R": 12.0, "DEF-shin.R": 12.0, "DEF-foot.R": 12.0,
            "DEF-thigh.L": 12.0, "DEF-shin.L": 12.0, "DEF-foot.L": 12.0,
            "DEF-spine": 10.0, "DEF-spine.003": 10.0}
per_bone = {k: {"mean": round(float(np.mean(v)), 2), "max": round(float(np.max(v)), 2)}
            for k, v in err.items()}
breaches = {k: {"max_deg": per_bone[k]["max"], "limit_deg": lim}
            for k, lim in CRITICAL.items()
            if k in per_bone and per_bone[k]["max"] > lim and k not in AUTHORED}
authored_dev = {k: per_bone[k] for k in AUTHORED if k in per_bone}
R["rotation_fidelity"] = {
    "per_bone_deg": per_bone,
    "overall_mean_deg": round(float(np.mean([x for v in err.values() for x in v])), 3),
    "overall_max_deg": round(float(np.max([x for v in err.values() for x in v])), 3),
    "gate_mean_lt_2deg": bool(np.mean([x for v in err.values() for x in v]) < 2.0),
    "per_bone_limits_deg": CRITICAL,
    "per_bone_breaches": breaches,
    "authored_override_bones": AUTHORED,
    "authored_override_deviation_deg": authored_dev,
    "gate_no_critical_bone_breach": not breaches,
    "note": ("bones driven by IK are expected to deviate where the goal was moved "
             "deliberately; those deviations are listed, never averaged away")}

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
    ph = np.array([list(pos[d][f] - pos["__root__"][f]) for f in SAMPLE])
    sh = POS[SAMPLE][:, j] - POS[SAMPLE][:, JN.index("Hips")]
    wr[side] = {"pos_rms_vs_source_m": round(float(np.sqrt(((ph - sh) ** 2).sum(1).mean())), 4),
                "orientation_delta_err_max_deg": round(float(np.max(
                    [angdiff(np2m(G[b, j]) @ np2m(G[a, j]).transposed(),
                             rot[d][b] @ rot[d][a].transposed())
                     for a, b in zip(SAMPLE[:-1], SAMPLE[1:])])), 2)}
R["wrist"] = wr
def roll_range(jn, dbone, child):
    if dbone not in rot: return None
    js, jc = JN.index(jn), JN.index(child)
    src, tgt = [], []
    for f in SAMPLE:
        ax = POS[f, jc] - POS[f, js]
        nn = np.linalg.norm(ax)
        if nn < 1e-9: continue
        av = Vector((ax / nn).tolist())
        for M, acc in ((np2m(G[f, js]) @ np2m(G[SAMPLE[0], js]).transposed(), src),
                       (rot[dbone][f] @ rot[dbone][SAMPLE[0]].transposed(), tgt)):
            q = M.to_quaternion()
            acc.append(math.degrees(q.to_axis_angle()[1] * (1 if q.axis.dot(av) > 0 else -1)))
    s_, t_ = float(np.ptp(src)), float(np.ptp(tgt))
    return {"source_deg": round(s_, 2), "target_deg": round(t_, 2),
            "loss_pct": round(100 * (1 - t_ / s_), 1) if s_ > 1e-6 else None}
R["forearm_roll"] = {"clip": LABEL, "source_clip": os.path.basename(BASE),
                     "R": roll_range("RightForeArm", "DEF-forearm.R", "RightHand"),
                     "L": roll_range("LeftForeArm", "DEF-forearm.L", "LeftHand"),
                     "note": ("roll range is a property of THIS clip; the 47.2 deg "
                              "figure was measured on the full 8 s water take, not "
                              "on the 1.2 s one-shot crop -- they are not comparable")}

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
    # Skating = how far the planted foot moves relative to the GROUND, recovered
    # by undoing the in-place mapping. Comparing against a constant treadmill
    # velocity was wrong: the body legitimately wobbles over a planted foot, and
    # that wobble appeared in the residual as if the foot were sliding.
    src_j = JN.index(cn)
    hip_j = JN.index("Hips")
    for f in range(1, len(SAMPLE)):
        if on[f] and on[f - 1]:
            p0, p1 = pos[d][SAMPLE[f - 1]], pos[d][SAMPLE[f]]
            # body motion between the two frames, from the rig itself
            b0, b1 = pos["__root__"][SAMPLE[f - 1]], pos["__root__"][SAMPLE[f]]
            # expected ground-relative displacement of a locked foot is zero, so
            # add back the body's own travel to leave the world-space slide
            src_rel0 = POS[SAMPLE[f - 1], src_j] - POS[SAMPLE[f - 1], hip_j]
            src_rel1 = POS[SAMPLE[f], src_j] - POS[SAMPLE[f], hip_j]
            expected = Vector((float(src_rel1[0] - src_rel0[0]),
                               float(src_rel1[1] - src_rel0[1]), 0.0))
            got = Vector((p1.x - p0.x, p1.y - p0.y, 0.0)) - Vector((b1.x - b0.x, b1.y - b0.y, 0.0))
            sdev = (got - expected).length
            tot += sdev; peak = max(peak, sdev * sc.render.fps)
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
    # Compare against EVERY interior transition, not one sample: a single
    # interior frame is not evidence about the cycle, and the earlier version
    # picked frame 2 arbitrarily.
    inner_all = [float(np.linalg.norm(
        bsz(SAMPLE[i + 1]) - (2.0 * bsz(SAMPLE[i]) - bsz(SAMPLE[i - 1])), axis=1).max())
        for i in range(1, len(SAMPLE) - 1)]
    # Contact state must match across the wrap or the loop changes gait phase.
    # The wrap is a one-frame TRANSITION, so demanding identical contact state
    # between the first and last frames is wrong -- they are a frame apart by
    # construction. What must hold is that the transition is a legal one: at most
    # one channel changes, exactly as inside the cycle.
    c0 = m.contacts[SAMPLE[0]].astype(int).tolist()
    cN = m.contacts[SAMPLE[-1]].astype(int).tolist()
    wrap_flips = sum(1 for a_, b_ in zip(c0, cN) if a_ != b_)
    interior_flips = max(
        sum(1 for a_, b_ in zip(m.contacts[SAMPLE[i]].astype(int).tolist(),
                                m.contacts[SAMPLE[i + 1]].astype(int).tolist()) if a_ != b_)
        for i in range(len(SAMPLE) - 1))
    R["loop_seam"] = {"seam_extrapolation_err_m": round(seam, 5),
                      "interior_err_median_m": round(float(np.median(inner_all)), 5),
                      "interior_err_p90_m": round(float(np.percentile(inner_all, 90)), 5),
                      "interior_err_max_m": round(float(np.max(inner_all)), 5),
                      "seam_percentile_within_interior": round(
                          100.0 * float(np.mean([seam > v for v in inner_all])), 1),
                      "contact_state_first_frame": c0,
                      "contact_state_last_frame": cN,
                      "contact_channel_flips_at_wrap": wrap_flips,
                      "max_contact_flips_inside_cycle": interior_flips,
                      "contact_transition_legal": wrap_flips <= max(1, interior_flips),
                      "gate_documented_lt_1cm": seam < 0.01,
                      "gate_proposed_seam_below_interior_median": (
                          seam <= float(np.median(inner_all))
                          and wrap_flips <= max(1, interior_flips))}

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
    # "any frame dipped into the band" is not a pour. The spout has to STAY in the
    # band for the whole pour window, or the water is coming out at the wrong
    # height for most of the shot.
    win = POUR_WINDOW or [0, len(zs) - 1]
    wz = [zs[i] for i in range(win[0], min(win[1] + 1, len(zs)))]
    in_win = [0.15 <= z <= 0.30 for z in wz]
    R["spout"] = {"min_above_bed_m": round(lo, 4), "max_above_bed_m": round(hi, 4),
                  "documented_band_m": [0.15, 0.30],
                  "pour_window_frames": win,
                  "window_min_m": round(float(min(wz)), 4),
                  "window_max_m": round(float(max(wz)), 4),
                  "window_frames_in_band": int(sum(in_win)),
                  "window_frames_total": len(wz),
                  "frames_in_band_whole_clip": int(sum(1 for z in zs if 0.15 <= z <= 0.30)),
                  "gate_in_band_for_whole_pour_window": bool(all(in_win)),
                  "note": ("gate requires the band to HOLD across the pour window; "
                           "an earlier version passed if any single frame entered it")}
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
    # Two different failures were being reported as one number. Can-vs-thigh is a
    # posing defect the retargeter must fix. Can-vs-the-holding-wrist is the
    # proxy handle arch passing through the arm it hangs from -- bounded by the
    # prop and hand-topology blockers, and not fixable by posing. Neither is
    # waived; they are counted separately so each points at its own owner.
    GRIP_REGION = ("DEF-forearm.R.001", "DEF-forearm.R")
    def split(v):
        g = sum(n for b, n in v["by_bone"].items() if b in GRIP_REGION)
        return g, sum(v["by_bone"].values()) - g
    grip_max = max((split(v)[0] for v in coll.values()), default=0)
    body_max = max((split(v)[1] for v in coll.values()), default=0)
    R["collisions"] = {"per_frame": coll,
                       "max_tris": max(v["tris"] for v in coll.values()),
                       "grip_region_vert_hits_max": grip_max,
                       "body_vert_hits_max": body_max,
                       "gate_zero_body_collisions": body_max == 0,
                       "grip_region_blocked_by": ["proxy watering can handle geometry",
                                                  "fused Rodin hand topology"],
                       "gate_zero": all(v["tris"] == 0 for v in coll.values())}

# ---------- 5b. authored motion must still be anatomically legal -----------
# Exempting authored bones from the FIDELITY gate cannot mean exempting them from
# anatomy. These gates apply to the delivered motion regardless of who authored it.
def bang(a, b, c):
    v1, v2 = (a - b), (c - b)
    if v1.length < 1e-9 or v2.length < 1e-9:
        return None
    return math.degrees(v1.angle(v2))

REST_WRIST = {}
for side in ("R", "L"):
    rf = (W @ rig.data.bones["DEF-forearm.%s" % side].matrix_local).to_3x3()
    rh = (W @ rig.data.bones["DEF-hand.%s" % side].matrix_local).to_3x3()
    REST_WRIST[side] = rf.inverted() @ rh

joint_gates = {}
for side in ("R", "L"):
    elb, wri, knee = [], [], []
    for f in SAMPLE:
        sh = pos.get("DEF-upper_arm.%s" % side, {}).get(f)
        el = pos.get("DEF-forearm.%s" % side, {}).get(f)
        ha = pos.get("DEF-hand.%s" % side, {}).get(f)
        if sh and el and ha:
            a_ = bang(sh, el, ha)
            if a_ is not None:
                elb.append(a_)
            # TRUE wrist articulation: how far the hand has rotated relative to
            # the forearm compared with REST. The absolute angle between the two
            # bone axes is already 53 deg at rest on this rig, so measuring it
            # raw reported a legal wrist as a 94 deg impossibility.
            rel = rot["DEF-forearm.%s" % side][f].inverted() @ rot["DEF-hand.%s" % side][f]
            dev = REST_WRIST[side].inverted() @ rel
            q = dev.to_quaternion(); ax = abs(q.angle)
            wri.append(math.degrees(min(ax, 2 * math.pi - ax)))
        hp = pos.get("DEF-thigh.%s" % side, {}).get(f)
        kn = pos.get("DEF-shin.%s" % side, {}).get(f)
        ft = pos.get("DEF-foot.%s" % side, {}).get(f)
        if hp and kn and ft:
            a_ = bang(hp, kn, ft)
            if a_ is not None:
                knee.append(a_)

    def jit(v):
        return round(float(np.max(np.abs(np.diff(v)))), 2) if len(v) > 1 else 0.0
    joint_gates[side] = {
        "elbow_min_deg": round(float(np.min(elb)), 1) if elb else None,
        "elbow_max_deg": round(float(np.max(elb)), 1) if elb else None,
        "elbow_frame_jitter_deg": jit(elb) if elb else None,
        "wrist_deviation_max_deg": round(float(np.max(wri)), 1) if wri else None,
        "knee_min_deg": round(float(np.min(knee)), 1) if knee else None,
        "knee_max_deg": round(float(np.max(knee)), 1) if knee else None,
        "knee_frame_jitter_deg": jit(knee) if knee else None,
    }
LIM = {"elbow_min": 25.0, "elbow_max": 180.0, "wrist_max": 75.0,
       "knee_min": 80.0, "knee_max": 180.5, "jitter_max": 35.0}

def _ok(v, lo=None, hi=None):
    return v is None or ((lo is None or v >= lo) and (hi is None or v <= hi))
R["joint_limits"] = {
    "per_side": joint_gates, "limits": LIM,
    "gate_elbow_range": all(_ok(v["elbow_min_deg"], lo=LIM["elbow_min"])
                            and _ok(v["elbow_max_deg"], hi=LIM["elbow_max"])
                            for v in joint_gates.values()),
    "gate_wrist_deviation": all(_ok(v["wrist_deviation_max_deg"], hi=LIM["wrist_max"])
                                for v in joint_gates.values()),
    "gate_knee_range": all(_ok(v["knee_min_deg"], lo=LIM["knee_min"])
                           and _ok(v["knee_max_deg"], hi=LIM["knee_max"])
                           for v in joint_gates.values()),
    "gate_no_joint_jitter": all(_ok(v["elbow_frame_jitter_deg"], hi=LIM["jitter_max"])
                                and _ok(v["knee_frame_jitter_deg"], hi=LIM["jitter_max"])
                                for v in joint_gates.values()),
    "note": ("applies to authored-override bones too -- exemption from the fidelity "
             "gate is not exemption from anatomy")}

# ---------- 5c. task-space preservation (corrected metrics) ----------------
# Every metric here replaced one that was wrong in a way that flattered the
# result. See tools/rvmotion/metrics.py for what each replaces and why.
from rvmotion.metrics import (heading_frame, spine_profile, per_frame_error,
                              arm_in_chest_frame, detect_steps)

hip_j = JN.index("Hips")
def rig_pel(f):
    return (pos["DEF-thigh.L"][f] + pos["DEF-thigh.R"][f]) * 0.5
def v3(v): return np.array([v.x, v.y, v.z], dtype=float)

RIG_SPINE = ["DEF-spine", "DEF-spine.001", "DEF-spine.002", "DEF-spine.003",
             "DEF-spine.004", "DEF-spine.006"]
SRC_SPINE = ["Spine", "Spine1", "Spine2", "Spine3", "Neck", "Head"]

rig_prof, src_prof, rig_arm_f, src_arm_f, rig_reach, src_reach = [], [], [], [], [], []
for i, f in enumerate(SAMPLE):
    head = float(m.root_heading[f]) if m.root_heading is not None else None
    s_pts = [POS[f, JN.index(n)] for n in SRC_SPINE]
    fwd_s, left_s, up_s = heading_frame(POS[f, hip_j], POS[f, JN.index("Spine3")], head)
    src_prof.append(spine_profile(s_pts, fwd_s, up_s))
    r_pts = [v3(pos[n][f]) for n in RIG_SPINE if n in pos]
    fwd_r, left_r, up_r = heading_frame(v3(rig_pel(f)), v3(pos["DEF-spine.003"][f]), head)
    rig_prof.append(spine_profile(r_pts, fwd_r, up_r))
    # arm in CHEST-local axes: a constant shoulder-wrist length says nothing
    # about whether the arm swings forward from the shoulder
    cb_s = np.stack([fwd_s, left_s, up_s], axis=1)
    src_arm_f.append(arm_in_chest_frame(POS[f, JN.index("RightArm")],
                                        POS[f, JN.index("RightHand")], cb_s))
    cb_r = np.stack([fwd_r, left_r, up_r], axis=1)
    rig_arm_f.append(arm_in_chest_frame(v3(pos["DEF-upper_arm.R"][f]),
                                        v3(pos["DEF-hand.R"][f]), cb_r))
    src_reach.append(float(np.dot(POS[f, JN.index("RightHand")] - POS[f, hip_j], fwd_s)))
    rig_reach.append(float(np.dot(v3(pos["DEF-hand.R"][f]) - v3(rig_pel(f)), fwd_r)))

rig_prof = np.array(rig_prof); src_prof = np.array(src_prof)
n_seg = min(rig_prof.shape[1], src_prof.shape[1])
seg_err = [per_frame_error(rig_prof[:, k], src_prof[:, k]) for k in range(n_seg)]

rig_arm_len = float(rig.data.bones["upper_arm_fk.R"].length + rig.data.bones["forearm_fk.R"].length)
src_arm_len = float(np.linalg.norm(POS[0, JN.index("RightForeArm")] - POS[0, JN.index("RightArm")])
                    + np.linalg.norm(POS[0, JN.index("RightHand")] - POS[0, JN.index("RightForeArm")]))
rr = np.array(rig_reach) / rig_arm_len
sr = np.array(src_reach) / src_arm_len
reach_err = per_frame_error(rr, sr)
ratio = float(np.ptp(rr) / max(1e-9, np.ptp(sr)))

flex_err = per_frame_error([a["flexion_deg"] for a in rig_arm_f],
                           [a["flexion_deg"] for a in src_arm_f])

# steps as EVENTS, in the ground frame, from the source's own contact labels
ch2 = {n: i for i, n in enumerate(m.contact_channels)}
steps = {}
for side, cn in (("L", "LeftFoot"), ("R", "RightFoot")):
    on = (m.contacts[SAMPLE, ch2[cn]] | m.contacts[SAMPLE, ch2[cn.replace("Foot", "ToeBase")]])
    d = "DEF-foot.%s" % side
    rig_xy = np.array([[pos[d][f].x, pos[d][f].y] for f in SAMPLE])
    src_xy = POS[SAMPLE][:, JN.index(cn), :2]
    steps[side] = {"rig": detect_steps(on, rig_xy, cyclic=IS_LOOP),
                   "src": detect_steps(on, src_xy, cyclic=IS_LOOP)}

R["task_space"] = {
    "forward_reach_normalised": {
        "rig_range": round(float(np.ptp(rr)), 4), "src_range": round(float(np.ptp(sr)), 4),
        "range_ratio": round(ratio, 3),
        "per_frame_rmse": round(reach_err["rmse"], 4),
        "per_frame_max_abs": round(reach_err["max_abs"], 4),
        "constant_bias": round(reach_err["bias"], 4),
        "per_frame_rmse_debiased": round(reach_err["rmse_debiased"], 4),
        "per_frame_max_abs_debiased": round(reach_err["max_abs_debiased"], 4),
        "bias_note": ("a constant offset is expected from A-pose/T-pose rest "
                      "calibration and is not a tracking failure; the debiased "
                      "figures are the dynamics")},
    "shoulder_flexion_deg": {
        "rig_range": round(float(np.ptp([a["flexion_deg"] for a in rig_arm_f])), 1),
        "src_range": round(float(np.ptp([a["flexion_deg"] for a in src_arm_f])), 1),
        "per_frame_rmse": round(flex_err["rmse"], 2),
        "per_frame_max_abs": round(flex_err["max_abs"], 2),
        "constant_bias_deg": round(flex_err["bias"], 2),
        "per_frame_max_abs_debiased": round(flex_err["max_abs_debiased"], 2)},
    "arm_chest_local_fwd_m": {
        "rig_range": round(float(np.ptp([a["local"][0] for a in rig_arm_f])), 4),
        "src_range": round(float(np.ptp([a["local"][0] for a in src_arm_f])), 4)},
    "spine_signed_pitch_per_frame_err_deg": [
        {"rmse": round(e["rmse"], 2), "max_abs": round(e["max_abs"], 2)} for e in seg_err],
    "spine_signed_pitch_rig_max_deg": [round(float(x), 1) for x in rig_prof.max(axis=0)],
    "spine_signed_pitch_src_max_deg": [round(float(x), 1) for x in src_prof.max(axis=0)],
    "step_events": {k: {"rig_count": v["rig"]["count"], "src_count": v["src"]["count"],
                        "rig_advance_m": v["rig"]["total_advance_m"],
                        "src_advance_m": v["src"]["total_advance_m"]}
                    for k, v in steps.items()},
    "gate_reach_preserved": (abs(ratio - 1.0) <= 0.10
                             and reach_err["max_abs_debiased"] <= 0.10),
    "gate_shoulder_flexion": flex_err["max_abs_debiased"] <= 12.0,
    "gate_step_events_match": all(v["rig"]["count"] == v["src"]["count"] for v in steps.values()),
    "gate_spine_shape": max(e["max_abs"] for e in seg_err) <= 4.0 if seg_err else True,
    "note": ("reach gate is +-10% of range AND <=0.10 arm-lengths per-frame max; "
             "spine uses SIGNED sagittal pitch compared frame by frame; steps are "
             "detected as release->swing->forward landing events, not displacement")}

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
