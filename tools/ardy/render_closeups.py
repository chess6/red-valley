"""Close-ups for grip and face review, plus the face-deformation measurement.

The face shots deliberately use ONE fixed camera for rest and all three poses,
so any apparent change is deformation, not perspective. The hand shots track the
hand, because the point there is to see the grip.

  blender --background pose_reference.blend --python render_closeups.py -- <outdir>
"""
import math, os, sys
import bpy
from mathutils import Vector

OUT = sys.argv[sys.argv.index("--") + 1:][0]
os.makedirs(OUT, exist_ok=True)
sc = bpy.context.scene
rig = [o for o in bpy.data.objects if o.type == "ARMATURE"][0]
mesh = max([o for o in bpy.data.objects if o.type == "MESH" and len(o.vertex_groups)],
           key=lambda o: len(o.data.vertices))
PB = rig.pose.bones
def w(n): return (rig.matrix_world @ PB[n].matrix).to_translation()

sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x = sc.render.resolution_y = 900
sc.view_settings.view_transform = "Standard"
sc.render.image_settings.file_format = "PNG"
try:
    sc.eevee.use_raytracing = True; sc.eevee.use_shadows = True
except AttributeError: pass

bpy.ops.object.light_add(type="SUN", location=(3, -5, 6))
k = bpy.context.object; k.data.energy = 4.0
k.rotation_euler = (math.radians(42), 0, math.radians(30))
bpy.ops.object.light_add(type="AREA", location=(-3, -4, 2))
f = bpy.context.object; f.data.energy = 220; f.data.size = 5
f.rotation_euler = (math.radians(75), 0, math.radians(-40))
sc.world = sc.world or bpy.data.worlds.new("W")
sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs[0].default_value = (.28, .32, .38, 1)

cd = bpy.data.cameras.new("C"); cam = bpy.data.objects.new("C", cd)
sc.collection.objects.link(cam); sc.camera = cam
def shoot(name, focus, dist, az, el=8.0, lens=85):
    cd.lens = lens
    a, e = math.radians(az), math.radians(el)
    cam.location = Vector(focus) + Vector((math.sin(a) * math.cos(e) * dist,
                                           -math.cos(a) * math.cos(e) * dist,
                                           math.sin(e) * dist))
    cam.rotation_euler = (Vector(focus) - cam.location).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = os.path.join(OUT, name)
    bpy.ops.render.render(write_still=True)

def rest():
    for pb in PB: pb.matrix_basis.identity()
    bpy.context.view_layer.update()

POSES = [(1, "01_start"), (2, "02_pour"), (3, "03_return")]

# ---- face: one camera for everything -----------------------------------
rest()
face_focus = w("head") + Vector((0.0, 0.0, 0.06))
FD, FAZ = 0.62, 0.0
shoot("face_00_rest.png", face_focus, FD, FAZ, el=4, lens=95)
for fr, n in POSES:
    sc.frame_set(fr); bpy.context.view_layer.update()
    shoot("face_%s.png" % n[3:], face_focus, FD, FAZ, el=4, lens=95)

# ---- hand: tracks the hand ---------------------------------------------
for fr, n in POSES:
    sc.frame_set(fr); bpy.context.view_layer.update()
    hf = w("prop_socket.R")
    for az, tag in ((-60.0, "a"), (30.0, "b")):
        shoot("grip_%s_%s.png" % (n[3:], tag), hf, 0.34, az, el=16, lens=80)

# ---- face deformation, measured ----------------------------------------
gi = {g.name: g.index for g in mesh.vertex_groups}
def wt(v, n):
    i = gi.get(n)
    return next((g.weight for g in v.groups if g.group == i), 0.0) if i is not None else 0.0
rest()
hz = w("head").z
face = [v for v in mesh.data.vertices
        if wt(v, "head") > 0.0 and (mesh.matrix_world @ v.co).z > hz
        and (mesh.matrix_world @ v.co).y < w("head").y]
fs = set(v.index for v in face)
edges = [e for e in mesh.data.edges if e.vertices[0] in fs and e.vertices[1] in fs]
def coords():
    dg = bpy.context.evaluated_depsgraph_get(); ev = mesh.evaluated_get(dg); m = ev.to_mesh()
    r = [mesh.matrix_world @ m.vertices[i].co for i in range(len(m.vertices))]
    ev.to_mesh_clear(); return r
rest(); base_co = coords()
base = [(base_co[e.vertices[0]] - base_co[e.vertices[1]]).length for e in edges]
nonrigid = sum(1 for v in face if wt(v, "head") < 0.999)
print("FACE verts=%d  edges=%d  not-rigid-on-head=%d" % (len(face), len(edges), nonrigid))
for fr, n in POSES:
    sc.frame_set(fr); bpy.context.view_layer.update()
    cur = coords()
    d = [abs((cur[e.vertices[0]] - cur[e.vertices[1]]).length - b) / b
         for e, b in zip(edges, base) if b > 1e-6]
    print("FACE_EDGE %s mean %.4f%% max %.4f%%" % (n, 100 * sum(d) / len(d), 100 * max(d)))
print("CLOSEUPS_DONE")
