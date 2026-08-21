"""Crop the retargeted walk to a contiguous stride cycle and export deform-only.

No pose repair and no invented interpolation: keyframes are copied verbatim from
the chosen source interval and renumbered.

  blender --background <walk_rigify.blend> --python crop_cycle.py -- <cycle.json> <outdir>
"""
import json, math, os, sys
import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
CJ, OUT = argv[0], argv[1]
os.makedirs(OUT, exist_ok=True)
C = json.load(open(CJ))
A, B = C["start"], C["end"]
N = B - A + 1
rig = bpy.data.objects["rv_rigify"]
mesh = max([o for o in bpy.data.objects if o.type == "MESH" and len(o.vertex_groups)],
           key=lambda o: len(o.data.vertices))
PB = rig.pose.bones
DEF = [b.name for b in rig.data.bones if b.name.startswith("DEF-")]
sc = bpy.context.scene

# sample the interval verbatim
poses = []
for f in range(A, B + 1):
    sc.frame_set(f); bpy.context.view_layer.update()
    poses.append({n: PB[n].matrix_basis.copy() for n in DEF})
print("captured %d contiguous frames (%d..%d)" % (N, A, B))

# rewrite the action with only those frames, renumbered from 1
if rig.animation_data and rig.animation_data.action:
    rig.animation_data.action_slot = None if hasattr(rig.animation_data, "action_slot") else None
    rig.animation_data.action = None
for b in PB:
    b.rotation_mode = "QUATERNION"
sc.frame_start, sc.frame_end = 1, N
sc.render.fps = 20; sc.render.fps_base = 1.0
for i, snap in enumerate(poses):
    for n in DEF:
        PB[n].matrix_basis = snap[n]
    bpy.context.view_layer.update()
    for n in DEF:
        PB[n].keyframe_insert("rotation_quaternion", frame=i + 1)
        PB[n].keyframe_insert("location", frame=i + 1)
print("rekeyed to frames 1..%d at 20 fps" % N)

# Export ONLY the mesh and its own rig. The scene still holds the leftover
# rv_rig (23 bones) and rv_metarig (65) from the build chain, plus ~130 WGT-*
# Rigify widget meshes. Exporting everything produced three skins, and Godot
# bound the mesh to the OLD 23-bone rig instead of the deform skeleton.
KEEP = {mesh.name, rig.name}
doomed = [o for o in bpy.data.objects if o.name not in KEEP]
print("excluding %d objects from export (%d armatures, %d widget meshes)"
      % (len(doomed),
         len([o for o in doomed if o.type == "ARMATURE"]),
         len([o for o in doomed if o.type == "MESH"])))
for o in doomed:
    bpy.data.objects.remove(o, do_unlink=True)
for o in bpy.data.objects:
    o.select_set(o.name in KEEP)
bpy.context.view_layer.objects.active = rig

glb = os.path.join(OUT, "walk_fwd.glb")
bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB", use_selection=True,
                          export_def_bones=True, export_animations=True,
                          export_frame_range=True, export_skins=True, export_morph=False)
print("exported %s  %.1f MB" % (glb, os.path.getsize(glb) / 1048576))
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "walk_fwd.blend"))

# ---- validation on the cropped clip ----------------------------------------
def P(f):
    sc.frame_set(f); bpy.context.view_layer.update()
    return {n: (rig.matrix_world @ PB[n].matrix).to_translation() for n in DEF}
S = {f: P(f) for f in range(1, N + 1)}
zR = [S[f]["DEF-foot.R"].z for f in S]; zL = [S[f]["DEF-foot.L"].z for f in S]
loR, loL = min(zR), min(zL)
conR = [z < loR + 0.020 for z in zR]; conL = [z < loL + 0.020 for z in zL]
print("VALIDATE frames=%d  duration %.2f s @20fps" % (N, N / 20.0))
print("  contacts: right %d frames, left %d frames, both-airborne %d frames"
      % (sum(conR), sum(conL), sum(1 for a, b in zip(conR, conL) if not a and not b)))
print("  alternating: %s" % ("yes" if sum(conR) and sum(conL) else "NO"))
seam_pose = max((S[1][n] - S[N][n]).length for n in DEF)
v1 = {n: S[2][n] - S[1][n] for n in DEF}
vN = {n: S[N][n] - S[N - 1][n] for n in DEF}
seam_vel = max((v1[n] - vN[n]).length for n in DEF)
worst = max(DEF, key=lambda n: (S[1][n] - S[N][n]).length)
print("  loop seam: pose %.4f m (worst bone %s), velocity %.4f m/frame"
      % (seam_pose, worst, seam_vel))
lean = [math.degrees(math.atan2(-(S[f]["DEF-spine.004"] - S[f]["DEF-spine"]).y,
                                 (S[f]["DEF-spine.004"] - S[f]["DEF-spine"]).z)) for f in S]
print("  posture: trunk lean %.1f..%.1f deg" % (min(lean), max(lean)))
gap = min(min((S[f]["DEF-forearm.%s" % s] - S[f]["DEF-spine.002"]).length for f in S)
          for s in ("R", "L"))
print("  arm clearance: min forearm->chest %.4f m" % gap)
# planted-foot horizontal travel per frame = the in-place "treadmill" speed
def slide(con, side):
    v = []
    for i in range(1, N):
        if con[i] and con[i - 1]:
            d = S[i + 1]["DEF-foot.%s" % side] - S[i]["DEF-foot.%s" % side]
            v.append(math.hypot(d.x, d.y))
    return v
sR, sL = slide(conR, "R"), slide(conL, "L")
if sR and sL:
    print("  planted-foot travel: right %.4f m/frame, left %.4f m/frame (should match)"
          % (sum(sR) / len(sR), sum(sL) / len(sL)))
print("CROP_DONE")
