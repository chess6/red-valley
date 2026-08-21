"""Retarget an accepted ARDY clip onto the Rigify DEFORM skeleton.

No regeneration and no cloud compute: this consumes an existing .npz.

Rotation-only aiming, so the result is in-place by construction -- world
displacement is never applied rather than being applied and then stripped.
DEF-bone constraints are removed first so the deform skeleton can be posed
directly, which is also exactly what gets exported.

  blender --background <rv_bound.blend> --python retarget_rigify.py -- <npz> <outdir>
"""
import json, math, os, sys
import bpy, numpy as np
from mathutils import Vector, Matrix

argv = sys.argv[sys.argv.index("--") + 1:]
NPZ, OUT = argv[0], argv[1]
os.makedirs(OUT, exist_ok=True)
MAP = json.load(open("art/animation/ardy_pilot/retarget_map.json"))
SRC = {n: i for i, n in enumerate(MAP["source_joint_order"])}

# Rigify DEF chain: bone -> (joint at its head, joint at its tail)
CHAIN = {
    "DEF-spine":     ("Hips", "Spine1"),
    "DEF-spine.001": ("Spine1", "Spine2"),
    "DEF-spine.002": ("Spine2", "Spine3"),
    "DEF-spine.003": ("Spine3", "Neck"),
    "DEF-spine.004": ("Neck", "Head"),
    "DEF-spine.006": ("Head", None),
    "DEF-shoulder.R": ("RightShoulder", "RightArm"),
    "DEF-upper_arm.R": ("RightArm", "RightForeArm"),
    "DEF-forearm.R": ("RightForeArm", "RightHand"),
    "DEF-hand.R":   ("RightHand", "RightHandEnd"),
    "DEF-shoulder.L": ("LeftShoulder", "LeftArm"),
    "DEF-upper_arm.L": ("LeftArm", "LeftForeArm"),
    "DEF-forearm.L": ("LeftForeArm", "LeftHand"),
    "DEF-hand.L":   ("LeftHand", "LeftHandEnd"),
    "DEF-thigh.R":  ("RightUpLeg", "RightLeg"),
    "DEF-shin.R":   ("RightLeg", "RightFoot"),
    "DEF-foot.R":   ("RightFoot", "RightToeBase"),
    "DEF-thigh.L":  ("LeftUpLeg", "LeftLeg"),
    "DEF-shin.L":   ("LeftLeg", "LeftFoot"),
    "DEF-foot.L":   ("LeftFoot", "LeftToeBase"),
}
# parent-first: a parent's rotation moves its children, so order matters
ORDER = ["DEF-spine", "DEF-spine.001", "DEF-spine.002", "DEF-spine.003",
         "DEF-spine.004", "DEF-spine.006",
         "DEF-shoulder.R", "DEF-upper_arm.R", "DEF-forearm.R", "DEF-hand.R",
         "DEF-shoulder.L", "DEF-upper_arm.L", "DEF-forearm.L", "DEF-hand.L",
         "DEF-thigh.R", "DEF-shin.R", "DEF-foot.R",
         "DEF-thigh.L", "DEF-shin.L", "DEF-foot.L"]

rig = bpy.data.objects["rv_rigify"]
mesh = max([o for o in bpy.data.objects if o.type == "MESH"],
           key=lambda o: len(o.data.vertices))
bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode="POSE")
PB = rig.pose.bones

removed = 0
for b in PB:
    if b.name.startswith("DEF-"):
        for c in list(b.constraints):
            b.constraints.remove(c); removed += 1
print("cleared %d constraints from DEF bones" % removed)

d = np.load(NPZ, allow_pickle=True)
J = d["posed_joints"]
FPS = int(d["fps"])
F = J.shape[0]
contacts = d["foot_contacts"] if "foot_contacts" in d.files else None
print("clip: %d frames @ %d fps (%.2f s)" % (F, FPS, F / float(FPS)))

sc = bpy.context.scene
sc.render.fps = FPS
sc.render.fps_base = 1.0
sc.frame_start, sc.frame_end = 1, F

# ARDY's CoreSkeleton27 is Y-UP (retarget.py reads height from index 1);
# Blender is Z-up. Aiming with raw source vectors puts the feet at chest height.
def y2z(v):
    return Vector((float(v[0]), -float(v[2]), float(v[1])))

def upd(): bpy.context.view_layer.update()
def aim(pb, target):
    m = pb.matrix.copy()
    cur = (m.to_3x3() @ Vector((0, 1, 0))).normalized()
    tgt = (Vector(target) - m.to_translation())
    if tgt.length < 1e-6: return
    tgt.normalize()
    T = Matrix.Translation(m.to_translation())
    pb.matrix = T @ cur.rotation_difference(tgt).to_matrix().to_4x4() @ T.inverted() @ m
    upd()

for b in PB:
    b.rotation_mode = "QUATERNION"

for f in range(F):
    for b in PB:
        b.matrix_basis.identity()
    upd()
    for name in ORDER:
        a, bj = CHAIN[name]
        if name not in PB or bj is None: continue
        if a not in SRC or bj not in SRC: continue
        pa = y2z(J[f, SRC[a]])
        pb_ = y2z(J[f, SRC[bj]])
        # aim in the SOURCE frame: direction only, so scale is irrelevant and no
        # world displacement can leak in
        cur = PB[name].matrix.to_translation()
        aim(PB[name], cur + (pb_ - pa))
    for b in PB:
        if b.name.startswith("DEF-"):
            b.keyframe_insert("rotation_quaternion", frame=f + 1)
print("keyed %d frames on %d DEF bones" % (F, len([b for b in PB if b.name.startswith('DEF-')])))

bpy.ops.object.mode_set(mode="OBJECT")
glb = os.path.join(OUT, "walk8_s1_rigify.glb")
bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB", use_selection=False,
                          export_def_bones=True, export_animations=True,
                          export_frame_range=True, export_anim_slide_to_zero=False,
                          export_skins=True, export_morph=False)
print("exported", glb, "%.1f MB" % (os.path.getsize(glb) / 1048576))
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "walk_rigify.blend"))
print("RETARGET_DONE")
