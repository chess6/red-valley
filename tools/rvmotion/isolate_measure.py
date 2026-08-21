"""Isolation measurements: is a missing reach / added arch coming from the
adapter+retargeter, or from the authored interaction layers?

Measures the SAME task-space quantities on the rig that were measured on the
source, so the two are directly comparable.

  blender --background <clip.blend> --python isolate_measure.py -- <base.rvm> <out.json> <label>
"""
import json, math, os, sys
import bpy, numpy as np
from mathutils import Vector

A = sys.argv[sys.argv.index("--") + 1:]
BASE, OUT, LABEL = A[0], A[1], A[2]
sys.path.insert(0, os.path.join(os.getcwd(), "tools"))
from rvmotion.canonical import RVMotion  # noqa: E402

m = RVMotion.load(BASE); POS = m.positions; JN = m.joints
rig = bpy.data.objects["rv_rigify"]; PB = rig.pose.bones; W = rig.matrix_world
sc = bpy.context.scene
def upd(): bpy.context.view_layer.update()
def wp(n): return (W @ PB[n].matrix).to_translation()
T = min(sc.frame_end - sc.frame_start + 1, m.num_frames)

rows = []
for f in range(T):
    sc.frame_set(sc.frame_start + f); upd()
    pel = (wp("DEF-thigh.L") + wp("DEF-thigh.R")) * 0.5
    chest = wp("DEF-spine.003")
    neck = wp("DEF-spine.004")
    wr = wp("DEF-hand.R"); sh = wp("DEF-upper_arm.R")
    lf, rf = wp("DEF-foot.L"), wp("DEF-foot.R")
    v = neck - pel
    rows.append({
        "wrist_fwd_rel_pelvis": -(wr.y - pel.y),
        "wrist_z_rel_pelvis": wr.z - pel.z,
        "shoulder_to_wrist": (wr - sh).length,
        "trunk_lean_deg": math.degrees(math.atan2(Vector((v.x, v.y)).length, v.z)),
        "pelvis_y": pel.y, "pelvis_z": pel.z,
        "lfoot_y": lf.y, "rfoot_y": rf.y,
        # lumbar shape: pitch of each spine segment, so an ARCH shows up as a
        # segment bending the opposite way to its neighbours
        "seg_pitch": [math.degrees(math.atan2(Vector(((b - a).x, (b - a).y)).length, (b - a).z))
                      for a, b in ((wp("DEF-spine"), wp("DEF-spine.001")),
                                   (wp("DEF-spine.001"), wp("DEF-spine.002")),
                                   (wp("DEF-spine.002"), wp("DEF-spine.003")),
                                   (wp("DEF-spine.003"), wp("DEF-spine.004")))],
    })

def col(k): return np.array([r[k] for r in rows])
segs = np.array([r["seg_pitch"] for r in rows])
# source equivalents
s_hip = POS[:T, JN.index("Hips")]
s_wr = POS[:T, JN.index("RightHand")]; s_sh = POS[:T, JN.index("RightArm")]
s_nk = POS[:T, JN.index("Neck")]
s_fwd = -(s_wr[:, 1] - s_hip[:, 1])
s_ext = np.linalg.norm(s_wr - s_sh, axis=1)
s_v = s_nk - s_hip
s_lean = np.degrees(np.arctan2(np.linalg.norm(s_v[:, :2], axis=1), s_v[:, 2]))
s_seg = []
for a, b in (("Spine", "Spine1"), ("Spine1", "Spine2"), ("Spine2", "Spine3"), ("Spine3", "Neck")):
    d = POS[:T, JN.index(b)] - POS[:T, JN.index(a)]
    s_seg.append(np.degrees(np.arctan2(np.linalg.norm(d[:, :2], axis=1), d[:, 2])))
s_seg = np.array(s_seg).T
s_lf = POS[:T, JN.index("LeftFoot")]; s_rf = POS[:T, JN.index("RightFoot")]

rep = {"label": LABEL, "frames": T,
  "wrist_forward_reach": {
      "rig_min": round(float(col("wrist_fwd_rel_pelvis").min()), 4),
      "rig_max": round(float(col("wrist_fwd_rel_pelvis").max()), 4),
      "rig_range": round(float(np.ptp(col("wrist_fwd_rel_pelvis"))), 4),
      "src_min": round(float(s_fwd.min()), 4), "src_max": round(float(s_fwd.max()), 4),
      "src_range": round(float(np.ptp(s_fwd)), 4),
      "reach_preserved_pct": round(100.0 * float(np.ptp(col("wrist_fwd_rel_pelvis")) / np.ptp(s_fwd)), 1)},
  "shoulder_to_wrist": {
      "rig_min": round(float(col("shoulder_to_wrist").min()), 4),
      "rig_max": round(float(col("shoulder_to_wrist").max()), 4),
      "src_min": round(float(s_ext.min()), 4), "src_max": round(float(s_ext.max()), 4)},
  "trunk_lean_deg": {
      "rig_min": round(float(col("trunk_lean_deg").min()), 1),
      "rig_max": round(float(col("trunk_lean_deg").max()), 1),
      "src_min": round(float(s_lean.min()), 1), "src_max": round(float(s_lean.max()), 1),
      "lean_amplification": round(float(np.ptp(col("trunk_lean_deg")) / max(1e-6, np.ptp(s_lean))), 2)},
  # like-for-like: excursion vs excursion. An earlier version compared the rig's
  # max excursion against the source's endpoint-to-endpoint delta and made a
  # faithful pelvis look like a 2.7x over-translation.
  "pelvis_translation": {
      "rig_excursion_y_m": round(float(np.ptp(col("pelvis_y"))), 4),
      "src_excursion_y_m": round(float(np.ptp(s_hip[:, 1])), 4),
      "rig_excursion_z_m": round(float(np.ptp(col("pelvis_z"))), 4),
      "src_excursion_z_m": round(float(np.ptp(s_hip[:, 2])), 4),
      "ratio_y": round(float(np.ptp(col("pelvis_y")) / max(1e-6, np.ptp(s_hip[:, 1]))), 2)},
  "lead_foot_displacement": {
      "rig_left_m": round(float(np.ptp(col("lfoot_y"))), 4),
      "rig_right_m": round(float(np.ptp(col("rfoot_y"))), 4),
      "src_left_m": round(float(np.ptp(s_lf[:, 1])), 4),
      "src_right_m": round(float(np.ptp(s_rf[:, 1])), 4),
      "ratio_left": round(float(np.ptp(col("lfoot_y")) / max(1e-6, np.ptp(s_lf[:, 1]))), 2),
      "ratio_right": round(float(np.ptp(col("rfoot_y")) / max(1e-6, np.ptp(s_rf[:, 1]))), 2)},
  "spine_segment_pitch_deg": {
      "rig_per_segment_max": [round(float(x), 1) for x in segs.max(axis=0)],
      "src_per_segment_max": [round(float(x), 1) for x in s_seg.max(axis=0)],
      "rig_minus_src": [round(float(a - b), 1) for a, b in zip(segs.max(axis=0), s_seg.max(axis=0))]},
}
json.dump(rep, open(OUT, "w"), indent=2)
print(json.dumps(rep, indent=2))
print("ISOLATE_DONE")
