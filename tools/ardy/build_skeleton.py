"""Build the shared production skeleton from docs/SKELETON_SPEC.md and bind it.

22 deform bones + prop_socket.R, A-pose rest, +Y up on export, 1.90 m
reference. Joint positions are measured from the mesh; nothing is remeshed,
decimated or repaired, and the delivered master is never written to.

  blender --background --python tools/ardy/build_skeleton.py -- <glb> <outdir>
"""
import json, math, os, sys
import bpy, mathutils
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:]
SRC, OUT = argv[0], argv[1]
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=SRC)
meshes = [o for o in bpy.data.objects if o.type == "MESH"]
if len(meshes) != 1:
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes: o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.join()
    meshes = [bpy.context.view_layer.objects.active]
obj = meshes[0]; obj.name = "player_mesh"
bpy.ops.object.select_all(action="DESELECT")
obj.select_set(True); bpy.context.view_layer.objects.active = obj
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

V = np.array([v.co[:] for v in obj.data.vertices])
zmin, zmax = V[:, 2].min(), V[:, 2].max(); H = zmax - zmin
print("mesh height %.4f m" % H)

def band(lo, hi):
    return V[(V[:, 2] >= zmin + lo*H) & (V[:, 2] < zmin + hi*H)]

def halfwidth(zrel, pct=55):
    b = band(zrel, zrel + 0.02)
    return float(np.percentile(np.abs(b[:, 0]), pct)) if len(b) >= 20 else 0.0

def arm_chain(sign):
    pts = V[(V[:, 2] > zmin + 0.45*H) & (V[:, 2] < zmin + 0.82*H)]
    pts = pts[pts[:, 0] > 0] if sign > 0 else pts[pts[:, 0] < 0]
    out = []
    for t in np.linspace(0.45, 0.80, 30):
        b = pts[(pts[:, 2] >= zmin + t*H) & (pts[:, 2] < zmin + (t+0.02)*H)]
        if len(b) < 8: continue
        far = b[np.abs(b[:, 0]) > np.percentile(np.abs(b[:, 0]), 80)]
        out.append((t, float(far[:, 0].mean()), float(far[:, 1].mean())))
    return out

# The character faces -Y, so its anatomical RIGHT is at -X (right = forward x up
# = (-Y) x (+Z) = -X). Verified by rendering markers on hand.R/hand.L: with .R at
# +X the red marker appeared on the viewer's right, i.e. the character's LEFT.
# ARDY agrees -- its "Right*" joints are also at negative X.
SR, SL = -1.0, +1.0        # sign of X for .R and .L
cr, cl = arm_chain(SR), arm_chain(SL)
def at(chain, t, fb):
    if not chain: return fb
    c = min(chain, key=lambda c: abs(c[0]-t))
    return (c[1], c[2], zmin + c[0]*H)

def Z(r): return zmin + r*H
SH = 0.82
hw = halfwidth(SH - 0.02) or 0.10*H
leg = band(0.35, 0.40)
legx = float(np.percentile(np.abs(leg[:, 0]), 60)) if len(leg) else 0.09*H
ankb = band(0.03, 0.07)
ankx = float(np.percentile(np.abs(ankb[:, 0]), 60)) if len(ankb) else legx

J = {
  "root": (0.0, 0.0, zmin),
  "hips": (0.0, 0.0, Z(0.52)), "spine": (0.0, 0.0, Z(0.62)),
  "chest": (0.0, 0.0, Z(0.72)), "neck": (0.0, 0.0, Z(0.845)),
  "head": (0.0, 0.0, Z(0.90)), "head_end": (0.0, 0.0, Z(1.0)),
  "clavicle.R": (SR*hw*0.30, 0.0, Z(0.80)), "clavicle.L": (SL*hw*0.30, 0.0, Z(0.80)),
  "shoulder.R": (SR*hw*0.98, 0.0, Z(SH)),   "shoulder.L": (SL*hw*0.98, 0.0, Z(SH)),
  "elbow.R": at(cr, 0.63, (SR*hw*1.15, 0.0, Z(0.63))),
  "elbow.L": at(cl, 0.63, (SL*hw*1.15, 0.0, Z(0.63))),
  "wrist.R": at(cr, 0.47, (SR*hw*1.25, 0.0, Z(0.47))),
  "wrist.L": at(cl, 0.47, (SL*hw*1.25, 0.0, Z(0.47))),
  "hand_end.R": None, "hand_end.L": None,
  "hip.R": (SR*legx*0.55, 0.0, Z(0.50)),  "hip.L": (SL*legx*0.55, 0.0, Z(0.50)),
  "knee.R": (SR*legx*0.80, 0.0, Z(0.28)), "knee.L": (SL*legx*0.80, 0.0, Z(0.28)),
  "ankle.R": (SR*ankx, 0.0, Z(0.045)),    "ankle.L": (SL*ankx, 0.0, Z(0.045)),
  "toe.R": (SR*ankx, -0.09*H, Z(0.012)),  "toe.L": (SL*ankx, -0.09*H, Z(0.012)),
  "toe_end.R": (SR*ankx, -0.14*H, Z(0.010)), "toe_end.L": (SL*ankx, -0.14*H, Z(0.010)),
}
for s in ("R", "L"):
    w = mathutils.Vector(J["wrist.%s" % s]); e = mathutils.Vector(J["elbow.%s" % s])
    J["hand_end.%s" % s] = tuple(w + (w - e).normalized() * (H * 0.045))

arm = bpy.data.armatures.new("rv_rig")
rig = bpy.data.objects.new("rv_rig", arm)
bpy.context.collection.objects.link(rig)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode="EDIT")

# (bone, head joint, tail joint, parent)  -- exactly the spec hierarchy
BONES = [
 ("root","root","hips",None),
 ("hips","hips","spine","root"),
 ("spine","spine","chest","hips"),
 ("chest","chest","neck","spine"),
 ("neck","neck","head","chest"),
 ("head","head","head_end","neck"),
 ("clavicle.R","clavicle.R","shoulder.R","chest"),
 ("upperarm.R","shoulder.R","elbow.R","clavicle.R"),
 ("forearm.R","elbow.R","wrist.R","upperarm.R"),
 ("hand.R","wrist.R","hand_end.R","forearm.R"),
 ("clavicle.L","clavicle.L","shoulder.L","chest"),
 ("upperarm.L","shoulder.L","elbow.L","clavicle.L"),
 ("forearm.L","elbow.L","wrist.L","upperarm.L"),
 ("hand.L","wrist.L","hand_end.L","forearm.L"),
 ("thigh.R","hip.R","knee.R","hips"),
 ("shin.R","knee.R","ankle.R","thigh.R"),
 ("foot.R","ankle.R","toe.R","shin.R"),
 ("toe.R","toe.R","toe_end.R","foot.R"),
 ("thigh.L","hip.L","knee.L","hips"),
 ("shin.L","knee.L","ankle.L","thigh.L"),
 ("foot.L","ankle.L","toe.L","shin.L"),
 ("toe.L","toe.L","toe_end.L","foot.L"),
]
made = {}
for name, h, t, _p in BONES:
    b = arm.edit_bones.new(name)
    b.head = mathutils.Vector(J[h]); b.tail = mathutils.Vector(J[t])
    if (b.tail - b.head).length < 1e-4:
        b.tail = b.head + mathutils.Vector((0, 0, 0.02))
    made[name] = b
for name, _h, _t, p in BONES:
    if p: made[name].parent = made[p]; made[name].use_connect = False

# prop socket: child of hand.R, at the grip centre, NOT a deform bone
ps = arm.edit_bones.new("prop_socket.R")
hb = made["hand.R"]
ps.head = hb.head.lerp(hb.tail, 0.55)
ps.tail = ps.head + (hb.tail - hb.head).normalized() * (H * 0.03)
ps.parent = hb; ps.use_connect = False
bpy.ops.object.mode_set(mode="OBJECT")
rig.data.bones["prop_socket.R"].use_deform = False

def weighted(o):
    n = sum(1 for v in o.data.vertices if any(g.weight > 0.001 for g in v.groups))
    return n / max(1, len(o.data.vertices))

bpy.ops.object.select_all(action="DESELECT")
obj.select_set(True); rig.select_set(True)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.parent_set(type="ARMATURE_AUTO")
frac = weighted(obj)
bind = "heat (direct)"
if frac < 0.02:
    # Heat weighting cannot solve on a surface split into UV-seam patches.
    # Weight a welded proxy and transfer back by position; the delivered
    # geometry and its UVs are untouched.
    bind = "heat on welded proxy, transferred by position"
    proxy = obj.copy(); proxy.data = obj.data.copy(); proxy.name = "weld_proxy"
    bpy.context.collection.objects.link(proxy)
    for m in list(proxy.modifiers): proxy.modifiers.remove(m)
    proxy.parent = None
    bpy.ops.object.select_all(action="DESELECT")
    proxy.select_set(True); bpy.context.view_layer.objects.active = proxy
    bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.remove_doubles(threshold=0.0005); bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    proxy.select_set(True); rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    from mathutils import kdtree
    kd = kdtree.KDTree(len(proxy.data.vertices))
    for i, v in enumerate(proxy.data.vertices): kd.insert(v.co, i)
    kd.balance()
    names = {g.index: g.name for g in proxy.vertex_groups}
    for nm in names.values():
        if nm not in obj.vertex_groups: obj.vertex_groups.new(name=nm)
    for v in obj.data.vertices:
        _, idx, _ = kd.find(v.co)
        for g in proxy.data.vertices[idx].groups:
            obj.vertex_groups[names[g.group]].add([v.index], g.weight, "REPLACE")
    bpy.data.objects.remove(proxy, do_unlink=True)
    if not any(m.type == "ARMATURE" for m in obj.modifiers):
        md = obj.modifiers.new("Armature", "ARMATURE"); md.object = rig
    obj.parent = rig
print("bind: %s -> %.1f%% of vertices weighted" % (bind, 100*weighted(obj)))

deform = [b.name for b in rig.data.bones if b.use_deform]
rest = {b.name: {"head": list(b.head_local), "tail": list(b.tail_local),
                 "parent": b.parent.name if b.parent else None,
                 "deform": b.use_deform} for b in rig.data.bones}
json.dump({"height_m": float(H), "bone_count_total": len(rig.data.bones),
           "bone_count_deform": len(deform), "bind_method": bind,
           "weighted_fraction": weighted(obj), "bones": rest},
          open(os.path.join(OUT, "rv_rig.json"), "w"), indent=1)

bpy.ops.object.select_all(action="DESELECT")
obj.select_set(True); rig.select_set(True)
bpy.context.view_layer.objects.active = rig
bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, "rv_player_rigged.glb"),
                          export_format="GLB", use_selection=True,
                          export_skins=True, export_apply=False,
                          export_cameras=False, export_lights=False)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "rv_player_rigged.blend"))
print("deform bones: %d | total: %d" % (len(deform), len(rig.data.bones)))
print("SKELETON_BUILT")
