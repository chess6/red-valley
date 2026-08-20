"""Retarget an ARDY .npz clip onto the Red Valley production skeleton.

ARDY supplies global joint rotations on CoreSkeleton27 in a Y-up frame; our rig
is Z-up with its own A-pose rest orientations. For each mapped bone:

    our_world_R(t) = C . ardy_global_R(t) . C^-1 . our_rest_R

where C converts Y-up to Z-up. Root translation is stripped (clips are
in-place by contract) and the measured forward speed is reported instead.

  blender --background --python tools/ardy/retarget.py -- <rig.glb> <clip.npz> <map.json> <out_dir>
"""
import json, math, os, sys
import bpy, mathutils
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:]
RIG_GLB, NPZ, MAP_JSON, OUT = argv[0], argv[1], argv[2], argv[3]
# Thumb-based roll is a PROP feature: it pins the hand so a socketed tool has a
# real orientation. Applied to locomotion it forces the palms into whatever
# roll ARDY's thumb happens to imply, which reads as flared hands. Off unless
# the clip actually holds something.
PROP_CLIP = (len(argv) > 4) and (argv[4].lower() in ("1", "yes", "true", "prop"))
SPINE_DEG = float(argv[5]) if len(argv) > 5 else 0.0
NECK_DEG  = float(argv[6]) if len(argv) > 6 else 0.0
os.makedirs(OUT, exist_ok=True)
CLIP = os.path.splitext(os.path.basename(NPZ))[0]

# Joint order comes from the committed map, not an ardy import: the ardy
# package pulls torch, which Blender's bundled Python does not have.
_M = json.load(open(MAP_JSON))
SRC_NAMES = _M["source_joint_order"]
SRC_IDX = {n: i for i, n in enumerate(SRC_NAMES)}

d = np.load(NPZ, allow_pickle=True)
G = d["global_rot_mats"]          # (F, 27, 3, 3)
J = d["posed_joints"]             # (F, 27, 3)
root = d["root_positions"]
fps = int(d["fps"])
F = G.shape[0]
M = _M["map"]

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=RIG_GLB)
rig = [o for o in bpy.data.objects if o.type == "ARMATURE"][0]
bpy.context.view_layer.objects.active = rig
bpy.context.scene.render.fps = fps
bpy.context.scene.render.fps_base = 1.0
bpy.context.scene.frame_start = 1
bpy.context.scene.frame_end = F

C = mathutils.Matrix.Rotation(math.radians(90), 3, "X")     # Y-up -> Z-up

# Rotation composition needs ARDY's rest pose to be known; it is not, and
# assuming it matches ours produced a T-pose. Aim each bone along the vector
# between its corresponding ARDY joints instead -- immune to rest mismatch.
CHAIN = {
 "hips": ("Hips", "Spine1"),          "spine": ("Spine1", "Spine3"),
 "chest": ("Spine3", "Neck"),         "neck": ("Neck", "Head"),
 "clavicle.R": ("RightShoulder", "RightArm"),
 "upperarm.R": ("RightArm", "RightForeArm"),
 "forearm.R": ("RightForeArm", "RightHand"),
 "hand.R": ("RightHand", "RightHandEnd"),
 "clavicle.L": ("LeftShoulder", "LeftArm"),
 "upperarm.L": ("LeftArm", "LeftForeArm"),
 "forearm.L": ("LeftForeArm", "LeftHand"),
 "hand.L": ("LeftHand", "LeftHandEnd"),
 "thigh.R": ("RightUpLeg", "RightLeg"), "shin.R": ("RightLeg", "RightFoot"),
 "foot.R": ("RightFoot", "RightToeBase"),
 "thigh.L": ("LeftUpLeg", "LeftLeg"),   "shin.L": ("LeftLeg", "LeftFoot"),
 "foot.L": ("LeftFoot", "LeftToeBase"),
}

# Bones whose ROLL matters: the thumb pins the hand's twist, which is what
# orients anything attached to prop_socket.R.
TWIST_REF = {"hand.R": "RightHandThumb1", "hand.L": "LeftHandThumb1"}

# ARDY's walk carries an S-curved trunk: pelvis->chest leans BACK ~11 deg while
# chest->head leans FORWARD ~11 deg, netting upright but reading as a slouch.
# Measurement showed the retarget reproduces the source within 0.4 deg, so the
# posture is the source's, not an artefact. Correct it additively and in equal
# and opposite amounts, so the head stays level and the legs -- and therefore
# foot contacts -- are untouched. Capped deliberately: this shapes posture, it
# does not author motion.
SPINE_CORR_CAP = 8.0
assert abs(SPINE_DEG) <= SPINE_CORR_CAP, "spine correction exceeds the cap"
# With the rest chain aligned to the mesh, the residual head-forward excess is
# in ARDY's NECK, not the trunk: the deformed mesh reads ~+31 deg against the
# mesh's own +18.6 deg baseline. Correcting the neck is smaller and closer to
# the cause than pitching the whole spine.
SPINE_CORR = {}
if SPINE_DEG: SPINE_CORR.update({"spine": +SPINE_DEG, "chest": -SPINE_DEG})
if NECK_DEG:  SPINE_CORR["neck"] = NECK_DEG
assert abs(NECK_DEG) <= SPINE_CORR_CAP, "neck correction exceeds the cap"

def depth(name):
    n, dep = rig.pose.bones[name], 0
    while n.parent: n, dep = n.parent, dep + 1
    return dep
ORDER = sorted([b for b in CHAIN if b in rig.pose.bones], key=depth)
print("apply order:", ORDER)

bpy.ops.object.mode_set(mode="POSE")
for pb in rig.pose.bones:
    pb.rotation_mode = "QUATERNION"

h_src = float(J[:, SRC_IDX["Head"], 1].max() - J[:, SRC_IDX["RightToeBase"], 1].min())
h_dst = 1.9005
scale = h_dst / h_src

def pitch_about_head(pb, degrees):
    """Additive pitch about the bone's own head. +ve leans forward (character
    faces -Y, so a positive rotation about +X tips the top toward -Y)."""
    m = pb.matrix.copy()
    T = mathutils.Matrix.Translation(m.to_translation())
    R = mathutils.Matrix.Rotation(math.radians(degrees), 4, "X")
    pb.matrix = T @ R @ T.inverted() @ m
    bpy.context.view_layer.update()

def set_frame(pb, y_dir, ref_dir):
    """Set a bone's full orientation from two vectors.

    Aiming alone fixes only the bone's direction and leaves roll about that
    axis undetermined -- which is why the watering can's spout pointed in an
    arbitrary direction. The hand's twist is pinned here using the thumb joint
    as a reference, so anything socketed to the hand inherits a real
    orientation."""
    y = mathutils.Vector(y_dir).normalized()
    r = mathutils.Vector(ref_dir)
    z = r - r.dot(y) * y
    if y.length < 1e-6 or z.length < 1e-6:
        return aim(pb, y_dir)
    z.normalize()
    x = y.cross(z)
    m = pb.matrix.copy()
    M = mathutils.Matrix((x, y, z)).transposed().to_4x4()
    M.translation = m.to_translation()
    pb.matrix = M
    bpy.context.view_layer.update()

def aim(pb, direction):
    """Rotate about the bone's own head so its axis follows a world direction."""
    m = pb.matrix.copy()
    cur = (m.to_3x3() @ mathutils.Vector((0, 1, 0))).normalized()
    tgt = mathutils.Vector(direction).normalized()
    if tgt.length < 1e-6:
        return
    R = cur.rotation_difference(tgt)
    T = mathutils.Matrix.Translation(m.to_translation())
    pb.matrix = T @ R.to_matrix().to_4x4() @ T.inverted() @ m
    bpy.context.view_layer.update()

_used = {"twist": False, "spine": False}
for f in range(F):
    for pb in rig.pose.bones:
        pb.matrix_basis.identity()
    bpy.context.view_layer.update()
    for bone in ORDER:
        a, b = CHAIN[bone]
        v = mathutils.Vector((J[f, SRC_IDX[b]] - J[f, SRC_IDX[a]]).tolist())
        ref = TWIST_REF.get(bone) if PROP_CLIP else None
        if ref and ref in SRC_IDX:
            t = mathutils.Vector((J[f, SRC_IDX[ref]] - J[f, SRC_IDX[a]]).tolist())
            set_frame(rig.pose.bones[bone], C @ v, C @ t); _used["twist"] = True
        else:
            aim(rig.pose.bones[bone], C @ v)                # Y-up -> Z-up
        if bone in SPINE_CORR:
            pitch_about_head(rig.pose.bones[bone], SPINE_CORR[bone]); _used["spine"] = True
    for bone in ORDER:
        rig.pose.bones[bone].keyframe_insert(data_path="rotation_quaternion", frame=f + 1)
bpy.ops.object.mode_set(mode="OBJECT")
assert _used["twist"] == PROP_CLIP, (
    "twist wiring wrong: PROP_CLIP=%s but twist used=%s" % (PROP_CLIP, _used["twist"]))
assert _used["spine"] == bool(SPINE_CORR), (
    "spine wiring wrong: SPINE_DEG=%s but correction used=%s" % (SPINE_DEG, _used["spine"]))
print("PROP_CLIP=%s  SPINE_DEG=%s" % (PROP_CLIP, SPINE_DEG))

if rig.animation_data and rig.animation_data.action:
    rig.animation_data.action.name = CLIP

disp = float(np.linalg.norm(root[-1] - root[0])) * scale
dur = (F - 1) / fps
report = {"clip": CLIP, "frames": F, "fps": fps, "duration_s": round(dur, 3),
          "src_height": round(h_src, 4), "scale_to_rig": round(scale, 4),
          "root_displacement_m": round(disp, 4),
          "forward_speed_m_s": round(disp / dur, 4),
          "mapped_bones": len(ORDER)}
json.dump(report, open(os.path.join(OUT, f"{CLIP}_retarget.json"), "w"), indent=2)
print(json.dumps(report))

bpy.ops.object.select_all(action="DESELECT")
for o in bpy.data.objects:
    if o.type in ("ARMATURE", "MESH"): o.select_set(True)
bpy.context.view_layer.objects.active = rig
bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, f"{CLIP}_retargeted.glb"),
                          export_format="GLB", use_selection=True,
                          export_animations=True, export_skins=True,
                          export_cameras=False, export_lights=False)
print("RETARGET_DONE", CLIP)
