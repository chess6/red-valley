"""Acceptance gate for ARDY pilot clips.

A static pose must FAIL. The earlier version measured only sliding, drift and
alignment, so a clip in which nothing moved scored a perfect zero on every
motion criterion and passed. Liveness is now checked explicitly:

  * minimum root speed        (locomotion must actually travel)
  * alternating foot contacts (a walk lifts each foot in turn)
  * minimum joint excursion   (something must move through a real range)

Positional criteria (grip, spout, slide) are still measured, but a clip that
fails liveness is rejected regardless of them.

  blender --background --python acceptance.py -- <rigged.glb> <can.glb> <clip.npz> <kind>
      kind: locomotion | interaction
"""
import json, math, os, sys
import bpy, mathutils
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:]
RIG_GLB, CAN_GLB, NPZ = argv[0], argv[1], argv[2]
KIND = argv[3] if len(argv) > 3 else "locomotion"

TOL_POS      = 0.05     # +-5 cm alignment tolerance
SOIL_HEIGHT  = 0.22     # plot bed top (src/world/plot.gd)
SYNC_WATER   = 0.45     # seconds
RIG_HEIGHT   = 1.9005

# liveness thresholds
MIN_ROOT_SPEED     = 0.80   # m/s -- below this it is not locomotion
MIN_ALTERNATIONS   = 2      # left-only <-> right-only contact swaps per clip
MIN_HIP_RANGE_LOCO = 0.020  # m of vertical hip travel in a gait
MIN_HIP_DROP_INTER = 0.100  # m -- an interaction that bends must drop the hips
MIN_HAND_EXCURSION = 0.250  # m of hand travel in an interaction

d = np.load(NPZ, allow_pickle=True)
J   = d["posed_joints"]
root = d["root_positions"]
fc  = d["foot_contacts"]          # [L-heel, L-toe, R-heel, R-toe]
fps_src = int(d["fps"])
F = len(J)
dur = (F - 1) / fps_src
MAP = json.load(open(os.path.join(os.path.dirname(NPZ), "..", "retarget_map.json")))
ORDER = MAP["source_joint_order"]
SI = {n: i for i, n in enumerate(ORDER)}
scale = RIG_HEIGHT / float(J[:, SI["Head"], 1].max() - J[:, SI["RightToeBase"], 1].min())

res = {"clip": os.path.splitext(os.path.basename(NPZ))[0], "kind": KIND,
       "frames": F, "fps": fps_src, "duration_s": round(dur, 3)}
fails = []

# ---- liveness 1: root speed
speed = float(np.linalg.norm(root[-1] - root[0])) * scale / dur
res["root_speed_m_s"] = round(speed, 4)
if KIND == "locomotion":
    res["root_speed_ok"] = speed >= MIN_ROOT_SPEED
    if not res["root_speed_ok"]:
        fails.append("root speed %.2f m/s below %.2f (not locomotion)" % (speed, MIN_ROOT_SPEED))

# ---- liveness 2: alternating foot contacts
left  = fc[:, 0] | fc[:, 1]
right = fc[:, 2] | fc[:, 3]
state = np.where(left & ~right, -1, np.where(right & ~left, 1, 0))
swaps, last = 0, 0
for s in state:
    if s != 0 and s != last:
        if last != 0: swaps += 1
        last = s
res["both_feet_planted_frames"] = int((left & right).sum())
res["single_support_frames"] = int((state != 0).sum())
res["contact_alternations"] = swaps
if KIND == "locomotion":
    res["contacts_alternate_ok"] = swaps >= MIN_ALTERNATIONS
    if not res["contacts_alternate_ok"]:
        fails.append("only %d contact alternations (need %d): feet never take turns"
                     % (swaps, MIN_ALTERNATIONS))

# ---- liveness 3: joint excursion
hips_y = J[:, SI["Hips"], 1] * scale
hand_y = J[:, SI["RightHand"], 1] * scale
hand_travel = float(np.linalg.norm(J[:, SI["RightHand"]] - J[0, SI["RightHand"]], axis=1).max()) * scale
res["hip_vertical_range_m"] = round(float(hips_y.max() - hips_y.min()), 4)
res["hand_travel_m"] = round(hand_travel, 4)
res["hand_lowest_m"] = round(float(hand_y.min()), 4)
if KIND == "locomotion":
    res["hip_range_ok"] = res["hip_vertical_range_m"] >= MIN_HIP_RANGE_LOCO
    if not res["hip_range_ok"]:
        fails.append("hip vertical range %.3f m below %.3f (no gait bounce)"
                     % (res["hip_vertical_range_m"], MIN_HIP_RANGE_LOCO))
else:
    res["hip_drop_ok"] = res["hip_vertical_range_m"] >= MIN_HIP_DROP_INTER
    res["hand_excursion_ok"] = hand_travel >= MIN_HAND_EXCURSION
    if not res["hip_drop_ok"]:
        fails.append("hip drop %.3f m below %.3f (never bends)"
                     % (res["hip_vertical_range_m"], MIN_HIP_DROP_INTER))
    if not res["hand_excursion_ok"]:
        fails.append("hand travel %.3f m below %.3f (no reach)"
                     % (hand_travel, MIN_HAND_EXCURSION))

# ---- positional criteria, measured on the retargeted rig
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=RIG_GLB)
rig = [o for o in bpy.data.objects if o.type == "ARMATURE"][0]
before = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=CAN_GLB)
can = [o for o in bpy.data.objects if o not in before and o.type == "MESH"][0]
OFF = {k: mathutils.Vector(v) for k, v in
       json.load(open(CAN_GLB.replace(".glb", ".json")))["markers"].items()}
can.parent = rig; can.parent_type = "BONE"; can.parent_bone = "prop_socket.R"
BONE_FROM_PROP = mathutils.Matrix.Rotation(math.radians(90), 4, "X")

act = rig.animation_data.action if rig.animation_data else None
f0, f1 = (int(round(v)) for v in act.frame_range) if act else (1, 1)

def ev_bone(name):
    dg = bpy.context.evaluated_depsgraph_get()
    e = rig.evaluated_get(dg)
    return (e.matrix_world @ e.pose.bones[name].matrix).to_translation()

spouts, grips, roots = [], [], []
for f in range(f0, f1 + 1):
    bpy.context.scene.frame_set(f)
    bpy.context.view_layer.update()
    sock_m = rig.matrix_world @ rig.evaluated_get(
        bpy.context.evaluated_depsgraph_get()).pose.bones["prop_socket.R"].matrix
    can.matrix_world = sock_m @ BONE_FROM_PROP
    bpy.context.view_layer.update()
    grips.append((can.matrix_world @ OFF["grip_origin"]) - sock_m.to_translation())
    spouts.append(can.matrix_world @ OFF["spout_tip"])
    roots.append(ev_bone("root"))

res["root_translation_max_m"] = round(max((r - roots[0]).length for r in roots), 5)
res["root_in_place"] = res["root_translation_max_m"] < 1e-4
res["grip_to_socket_max_m"] = round(max(g.length for g in grips), 5)
res["grip_holds"] = res["grip_to_socket_max_m"] < 1e-3
if not res["root_in_place"]: fails.append("root motion present (clips must be in-place)")
if not res["grip_holds"]:    fails.append("grip drifts off the socket")

if KIND == "interaction":
    n = int(round(SYNC_WATER * fps_src))
    s = spouts[min(n, len(spouts) - 1)]
    res["spout_at_sync"] = {"height_above_soil_m": round(s.z - SOIL_HEIGHT, 4),
                            "within_tolerance": abs(s.z - SOIL_HEIGHT) <= TOL_POS}
    res["spout_lowest_above_soil_m"] = round(min(p.z for p in spouts) - SOIL_HEIGHT, 4)
    if not res["spout_at_sync"]["within_tolerance"]:
        fails.append("spout %.3f m off the soil at the sync point (tolerance %.2f)"
                     % (res["spout_at_sync"]["height_above_soil_m"], TOL_POS))

res["FAILURES"] = fails
res["VERDICT"] = "PASS" if not fails else "FAIL"
print(json.dumps(res, indent=2))
print("VERDICT:", res["VERDICT"], "" if not fails else "-- " + "; ".join(fails))
