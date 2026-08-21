"""Retarget the constrained water_can Core clip onto Rigify, attach the can,
layer the provisional grip, validate, render, and export deform-only.

  blender --background rv_bound.blend --python build_water_clip.py -- <npz> <outdir>
"""
import json, math, os, sys
import bpy, numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:]
NPZ, OUT = argv[0], argv[1]
os.makedirs(OUT, exist_ok=True)
MAP = json.load(open("art/animation/ardy_pilot/retarget_map.json"))
SRC = {n: i for i, n in enumerate(MAP["source_joint_order"])}
CAN_GLB = "art/animation/ardy_pilot/proxy/watering_can_proxy.glb"
META = json.load(open(CAN_GLB.replace(".glb", ".json")))
GA = Matrix(META["grip_anchor_basis_rows"])
SOIL = 0.22

CHAIN = {
    "DEF-spine": ("Hips", "Spine1"), "DEF-spine.001": ("Spine1", "Spine2"),
    "DEF-spine.002": ("Spine2", "Spine3"), "DEF-spine.003": ("Spine3", "Neck"),
    "DEF-spine.004": ("Neck", "Head"), "DEF-spine.006": ("Head", None),
    "DEF-shoulder.R": ("RightShoulder", "RightArm"),
    "DEF-upper_arm.R": ("RightArm", "RightForeArm"),
    "DEF-forearm.R": ("RightForeArm", "RightHand"),
    "DEF-hand.R": ("RightHand", "RightHandEnd"),
    "DEF-shoulder.L": ("LeftShoulder", "LeftArm"),
    "DEF-upper_arm.L": ("LeftArm", "LeftForeArm"),
    "DEF-forearm.L": ("LeftForeArm", "LeftHand"),
    "DEF-hand.L": ("LeftHand", "LeftHandEnd"),
    "DEF-thigh.R": ("RightUpLeg", "RightLeg"), "DEF-shin.R": ("RightLeg", "RightFoot"),
    "DEF-foot.R": ("RightFoot", "RightToeBase"),
    "DEF-thigh.L": ("LeftUpLeg", "LeftLeg"), "DEF-shin.L": ("LeftLeg", "LeftFoot"),
    "DEF-foot.L": ("LeftFoot", "LeftToeBase"),
}
ORDER = ["DEF-spine", "DEF-spine.001", "DEF-spine.002", "DEF-spine.003",
         "DEF-spine.004", "DEF-spine.006",
         "DEF-shoulder.R", "DEF-upper_arm.R", "DEF-forearm.R", "DEF-hand.R",
         "DEF-shoulder.L", "DEF-upper_arm.L", "DEF-forearm.L", "DEF-hand.L",
         "DEF-thigh.R", "DEF-shin.R", "DEF-foot.R",
         "DEF-thigh.L", "DEF-shin.L", "DEF-foot.L"]
# provisional gameplay-distance grip (accepted limitations recorded)
GRIP = {"f_index": (34, 44, 28), "f_middle": (34, 44, 28),
        "f_ring": (28, 36, 22), "thumb": (30, 34, 24)}

rig = bpy.data.objects["rv_rigify"]
mesh = max([o for o in bpy.data.objects if o.type == "MESH" and len(o.vertex_groups)],
           key=lambda o: len(o.data.vertices))
bpy.context.view_layer.objects.active = rig
if rig.mode != "OBJECT": bpy.ops.object.mode_set(mode="OBJECT")
bpy.ops.object.mode_set(mode="POSE")
PB = rig.pose.bones
for b in PB:
    if b.name.startswith("DEF-"):
        for c in list(b.constraints): b.constraints.remove(c)

d = np.load(NPZ)
J = d["posed_joints"]; FPS = int(d["fps"]); F = J.shape[0]
sc = bpy.context.scene
sc.render.fps = FPS; sc.render.fps_base = 1.0
sc.frame_start, sc.frame_end = 1, F
print("clip: %d frames @ %d fps" % (F, FPS))

def y2z(v): return Vector((float(v[0]), -float(v[2]), float(v[1])))
def upd(): bpy.context.view_layer.update()
def aim(pb, target):
    m = pb.matrix.copy()
    cur = (m.to_3x3() @ Vector((0, 1, 0))).normalized()
    tgt = Vector(target) - m.to_translation()
    if tgt.length < 1e-6: return
    T = Matrix.Translation(m.to_translation())
    pb.matrix = T @ cur.rotation_difference(tgt.normalized()).to_matrix().to_4x4() @ T.inverted() @ m
    upd()

for b in PB: b.rotation_mode = "QUATERNION"
for f in range(F):
    for b in PB: b.matrix_basis.identity()
    upd()
    for name in ORDER:
        a, bj = CHAIN[name]
        if bj is None or name not in PB: continue
        cur = PB[name].matrix.to_translation()
        aim(PB[name], cur + (y2z(J[f, SRC[bj]]) - y2z(J[f, SRC[a]])))
    # grip layer: fingers only, constant, never fighting the body motion
    for dg, (a1, a2, a3) in GRIP.items():
        for jn, ang in zip(("01", "02", "03"), (a1, a2, a3)):
            n = "DEF-%s.%s.R" % (dg, jn)
            if n in PB:
                PB[n].rotation_mode = "XYZ"
                PB[n].rotation_euler = (math.radians(ang), 0,
                                        math.radians(-18) if (dg == "thumb" and jn == "01") else 0)
    for b in PB:
        if b.name.startswith("DEF-"):
            if b.rotation_mode == "QUATERNION":
                b.keyframe_insert("rotation_quaternion", frame=f + 1)
            else:
                b.keyframe_insert("rotation_euler", frame=f + 1)
print("retargeted + grip keyed")

# ---- socket + can at the start pose ----------------------------------------
sc.frame_set(1); upd()
GIx = {g.name: g.index for g in mesh.vertex_groups}
def surf_of(groups, wmin=0.5):
    idx = [GIx.get(g) for g in groups]; idx = [i for i in idx if i is not None]
    dg_ = bpy.context.evaluated_depsgraph_get()
    ev = mesh.evaluated_get(dg_); m = ev.to_mesh()
    pts = [mesh.matrix_world @ m.vertices[v.index].co for v in mesh.data.vertices
           if any(g.group in idx and g.weight > wmin for g in v.groups)]
    ev.to_mesh_clear(); return pts
pads = surf_of(["DEF-f_index.03.R", "DEF-f_middle.03.R", "DEF-f_index.02.R", "DEF-f_middle.02.R"])
palm = surf_of(["DEF-palm.01.R", "DEF-palm.02.R", "DEF-palm.03.R", "DEF-hand.R"], wmin=0.3)
pos = (sum(pads, Vector()) / len(pads) + sum(palm, Vector()) / len(palm)) * 0.5
def wp(n): return (rig.matrix_world @ PB[n].matrix).to_translation()
FORE = (wp("DEF-hand.R") - wp("DEF-forearm.R")).normalized()
BAR = FORE.cross(Vector((0, 0, -1)))
if BAR.length < 1e-4: BAR = Vector((1, 0, 0))
BAR.normalize()
DOWN = Vector((0, 0, -1))
zc = (DOWN - BAR * DOWN.dot(BAR)).normalized()
xc = BAR.cross(zc).normalized()
SOCK = Matrix.Translation(pos) @ Matrix((xc, BAR, zc)).transposed().to_4x4()
bpy.ops.object.mode_set(mode="EDIT")
EB = rig.data.edit_bones
if "prop_socket.R" in EB: EB.remove(EB["prop_socket.R"])
sb = EB.new("prop_socket.R")
inv = rig.matrix_world.inverted()
sb.head = inv @ SOCK.to_translation()
sb.tail = inv @ (SOCK.to_translation() + SOCK.to_3x3() @ Vector((0, 0.05, 0)))
sb.parent = EB["DEF-hand.R"]; sb.use_connect = False; sb.use_deform = False
bpy.ops.object.mode_set(mode="POSE")
PB = rig.pose.bones
before = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=CAN_GLB)
can = [o for o in bpy.data.objects if o not in before and o.type == "MESH"][0]
# Bone parenting attaches at the bone TAIL; assigning matrix_world under a bone
# parent is unreliable mid-script (it produced 0.12 m of anchor drift). Set the
# parent-relative basis explicitly instead: world = parent_world @ basis, so
# basis = parent_world^-1 @ desired, exact by construction and rigid thereafter.
can.parent = rig; can.parent_type = "BONE"; can.parent_bone = "prop_socket.R"
can.matrix_parent_inverse = Matrix.Identity(4)
# Convention-free placement: deriving the bone-parent matrix by formula left a
# constant 0.060 m bias (tail/roll conventions). Instead, read the EVALUATED
# effective parent by setting an identity basis, then solve the basis exactly:
# world = P @ basis  =>  basis = P^-1 @ desired.
can.matrix_basis = Matrix.Identity(4)
upd()
P_eff = can.matrix_world.copy()
can.matrix_basis = P_eff.inverted() @ (SOCK @ GA.inverted())
upd()
_ga = can.matrix_world @ GA
_seat = (_ga.to_translation() - SOCK.to_translation()).length
print("seat check: can anchor vs intended socket = %.9f m" % _seat)
assert _seat < 1e-5, "can not seated where intended"
hand_local = (rig.matrix_world @ PB["DEF-hand.R"].matrix).inverted() @ can.matrix_world
json.dump({"can_local_to_DEF-hand.R": [list(r) for r in hand_local],
           "socket_world_at_start": [list(r) for r in SOCK]},
          open(os.path.join(OUT, "can_attachment.json"), "w"), indent=2)
# Anchor guarantee = two separate facts, measured separately:
#  1. SEAT: the can's grip_anchor coincides with the intended socket frame at
#     placement (asserted above, ~7e-8 m).
#  2. RIGIDITY: the can's transform relative to DEF-hand.R never changes over
#     the clip. (Comparing against the prop_socket.R BONE is wrong -- edit
#     bones are authored in rest space, so the bone reads ~0.06 m off in a
#     posed frame even though the can itself is exact.)
hand_rel0 = None
drift_p = 0.0; drift_r = 0.0
for f_ in (1, 40, 73, 120, 160):
    sc.frame_set(f_); upd()
    rel = (rig.matrix_world @ PB["DEF-hand.R"].matrix).inverted() @ can.matrix_world
    if hand_rel0 is None: hand_rel0 = rel.copy()
    drift_p = max(drift_p, (rel.to_translation() - hand_rel0.to_translation()).length)
    drift_r = max(drift_r, math.degrees(
        rel.to_quaternion().rotation_difference(hand_rel0.to_quaternion()).angle))
sc.frame_set(1); upd()
print("can attached; hand-relative drift across frames: max %.9f m / %.7f deg"
      % (drift_p, drift_r))

# ---- validation -------------------------------------------------------------
OFF = {k: Vector(v) for k, v in META["markers"].items()}
def spout(): return can.matrix_world @ OFF["spout_tip"]
mesh.data.calc_loop_triangles()
GN = {i: n for n, i in GIx.items()}
def dom(vi):
    v = mesh.data.vertices[vi]
    return GN.get(max(v.groups, key=lambda g: g.weight).group) if v.groups else None
HANDK = ("DEF-hand.R", "DEF-f_", "DEF-thumb", "DEF-palm")
BODY_T = [tuple(t.vertices) for t in mesh.data.loop_triangles
          if not any((dom(i) or "").startswith(HANDK) for i in t.vertices)]
def body_can():
    dg_ = bpy.context.evaluated_depsgraph_get()
    ev = mesh.evaluated_get(dg_); m = ev.to_mesh()
    co = [mesh.matrix_world @ v.co for v in m.vertices]
    bt = BVHTree.FromPolygons(co, BODY_T, all_triangles=True)
    cev = can.evaluated_get(dg_); cm = cev.to_mesh(); cm.calc_loop_triangles()
    ct = BVHTree.FromPolygons([can.matrix_world @ v.co for v in cm.vertices],
                              [tuple(t.vertices) for t in cm.loop_triangles], all_triangles=True)
    n = len(ct.overlap(bt)); ev.to_mesh_clear(); cev.to_mesh_clear(); return n

# face rigidity baseline
hz_idx = GIx.get("DEF-spine.006")
face = [v.index for v in mesh.data.vertices
        if any(g.group == hz_idx and g.weight > 0.5 for g in v.groups)]
fs = set(face)
edges = [e for e in mesh.data.edges if e.vertices[0] in fs and e.vertices[1] in fs][:3000]
def coords():
    dg_ = bpy.context.evaluated_depsgraph_get(); ev = mesh.evaluated_get(dg_); m = ev.to_mesh()
    r = [mesh.matrix_world @ m.vertices[i].co for i in range(len(m.vertices))]
    ev.to_mesh_clear(); return r
sc.frame_set(1); upd(); c0 = coords()
base = [(c0[e.vertices[0]] - c0[e.vertices[1]]).length for e in edges]

report = {"frames": {}, "anchor_drift_m": drift_p}
worst_face = 0.0; worst_bc = 0; spout_pour = []
for f in [1, 20, 40, 56, 65, 73, 81, 96, 120, 140, 160]:
    sc.frame_set(f); upd()
    cc = coords()
    wf = max((abs((cc[e.vertices[0]] - cc[e.vertices[1]]).length - b) / b
              for e, b in zip(edges, base) if b > 1e-6), default=0)
    bc = body_can()
    sp = spout()
    hnd = wp("DEF-hand.R")
    report["frames"][f] = {"face_dev": round(wf * 100, 3), "body_can": bc,
                           "spout": [round(x, 3) for x in sp],
                           "hand": [round(x, 3) for x in hnd]}
    worst_face = max(worst_face, wf); worst_bc = max(worst_bc, bc)
    if 60 <= f <= 90: spout_pour.append(sp)
    print("  f=%3d face_dev %.3f%%  body/can %d  spout(%.2f,%.2f,%.2f) hand_z %.3f"
          % (f, wf * 100, bc, sp.x, sp.y, sp.z, hnd.z))
sp_m = sum(spout_pour, Vector()) / max(1, len(spout_pour))
print("VALIDATE face rigidity worst %.3f%% | body/can worst %d" % (worst_face * 100, worst_bc))
print("VALIDATE pour spout mean (%.3f, %.3f, %.3f) -> %.3f above the %.2f bed, fwd %.3f"
      % (sp_m.x, sp_m.y, sp_m.z, sp_m.z - SOIL, SOIL, -sp_m.y))
report["pour_spout_mean"] = [round(x, 4) for x in sp_m]
report["pour_spout_above_bed"] = round(sp_m.z - SOIL, 4)
json.dump(report, open(os.path.join(OUT, "water_validation.json"), "w"), indent=2)
bpy.ops.object.mode_set(mode="OBJECT")
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "water_can.blend"))

# ---- deform-only export (no can, no leftovers, ONE action) ------------------
act = rig.animation_data.action
act.name = "water_can"
for a in list(bpy.data.actions):
    if a is not act: bpy.data.actions.remove(a)
KEEP = {mesh.name, rig.name}
for o in list(bpy.data.objects):
    if o.name not in KEEP: bpy.data.objects.remove(o, do_unlink=True)
for o in bpy.data.objects: o.select_set(o.name in KEEP)
bpy.context.view_layer.objects.active = rig
glb = os.path.join(OUT, "water_can.glb")
bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB", use_selection=True,
                          export_def_bones=True, export_animations=True,
                          export_frame_range=True, export_skins=True, export_morph=False)
print("exported %s  %.1f MB" % (glb, os.path.getsize(glb) / 1048576))
print("WATER_CLIP_DONE")
