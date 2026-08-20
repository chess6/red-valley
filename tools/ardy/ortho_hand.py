"""Orthographic hand plates with an exact pixel->world mapping.

Used to place finger joints explicitly by eye. Automatic digit segmentation has
failed five different ways on this mesh; these plates let joints be read off
directly instead.

  blender --background --python ortho_hand.py -- <rig.glb> <outdir>
"""
import json, math, os, sys
import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
GLB, OUT = argv[0], argv[1]
os.makedirs(OUT, exist_ok=True)
RES, SCALE = 1400, 0.15

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)
rig = [o for o in bpy.data.objects if o.type == "ARMATURE"][0]
obj = max([o for o in bpy.data.objects if o.type == "MESH" and len(o.vertex_groups)],
          key=lambda o: len(o.data.vertices))
for o in list(bpy.data.objects):
    if o.type == "MESH" and o is not obj:
        bpy.data.objects.remove(o, do_unlink=True)

PB = rig.pose.bones
GI = {g.name: g.index for g in obj.vertex_groups}
def wt(v, n):
    i = GI.get(n)
    return next((g.weight for g in v.groups if g.group == i), 0.0) if i is not None else 0.0

SIDE = "R"
hv = [v for v in obj.data.vertices if wt(v, "hand." + SIDE) >= 0.4]
co = [obj.matrix_world @ v.co for v in hv]
hm = rig.matrix_world @ PB["hand." + SIDE].matrix
fing = (hm.to_3x3() @ Vector((0, 1, 0))).normalized()
o = hm.to_translation()
t = [(c - o).dot(fing) for c in co]
lo, hi = min(t), max(t)
palm = [c for c, tt in zip(co, t) if lo + 0.20 * (hi - lo) <= tt <= lo + 0.55 * (hi - lo)]
pc = sum(palm, Vector()) / len(palm)
u = Vector((0, 0, 1)).cross(fing)
if u.length < 1e-6: u = Vector((1, 0, 0)).cross(fing)
u.normalize(); v2 = fing.cross(u).normalized()
sxx = syy = sxy = 0.0
for c in palm:
    d = c - pc; a, b = d.dot(u), d.dot(v2)
    sxx += a * a; syy += b * b; sxy += a * b
th = 0.5 * math.atan2(2 * sxy, sxx - syy)
e1 = (u * math.cos(th) + v2 * math.sin(th)).normalized()
e2 = fing.cross(e1).normalized()
v1 = sum(((c - pc).dot(e1)) ** 2 for c in palm)
v2v = sum(((c - pc).dot(e2)) ** 2 for c in palm)
bar, nrm = (e1, e2) if v1 > v2v else (e2, e1)
if nrm.dot(Vector((0, -1, 0))) < 0: nrm = -nrm

centre = sum(co, Vector()) / len(co)

# Isolate the hand. The palm faces the thigh, so a camera on the palm side sits
# inside the leg and renders trousers; and the forearm occludes the edge view.
import bmesh
keep = set(v.index for v in obj.data.vertices
           if wt(v, "hand." + SIDE) >= 0.15 or (obj.matrix_world @ v.co - centre).length < 0.075)
bm = bmesh.new(); bm.from_mesh(obj.data); bm.verts.ensure_lookup_table()
doomed = [v for v in bm.verts if v.index not in keep]
bmesh.ops.delete(bm, geom=doomed, context="VERTS")
bm.to_mesh(obj.data); bm.free()
obj.data.update()
print("isolated hand: %d verts remain" % len(obj.data.vertices))
for m in list(obj.modifiers): obj.modifiers.remove(m)

# clay material so geometry reads, not texture
for m in list(obj.data.materials): pass
obj.data.materials.clear()
clay = bpy.data.materials.new("clay"); clay.use_nodes = True
b = clay.node_tree.nodes["Principled BSDF"]
b.inputs["Base Color"].default_value = (0.42, 0.44, 0.48, 1)
b.inputs["Roughness"].default_value = 0.55
obj.data.materials.append(clay)

sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x = sc.render.resolution_y = RES
sc.view_settings.view_transform = "Standard"
try:
    sc.eevee.use_raytracing = True; sc.eevee.use_shadows = True
except AttributeError: pass
sc.world = sc.world or bpy.data.worlds.new("W"); sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs[0].default_value = (.10, .11, .13, 1)
bpy.ops.object.light_add(type="SUN", location=(1, -1, 2))
k = bpy.context.object; k.data.energy = 1.6
k.rotation_euler = (math.radians(50), 0, math.radians(30))
bpy.ops.object.light_add(type="AREA", location=(-1, -1, 1))
fl = bpy.context.object; fl.data.energy = 35; fl.data.size = 2

cd = bpy.data.cameras.new("C"); cam = bpy.data.objects.new("C", cd)
sc.collection.objects.link(cam); sc.camera = cam
cd.type = "ORTHO"; cd.ortho_scale = SCALE

VIEWS = {
    # name: (view direction toward the hand, right vector, up vector)
    "palm":  (-nrm, bar, fing),     # looking onto the palm: x=across, y=along fingers
    "edge":  (-bar, nrm, fing),     # looking along the handle axis: x=through palm
}
mapping = {}
for name, (viewdir, right, up) in VIEWS.items():
    cam.location = centre - viewdir * 0.5
    m = viewdir.to_track_quat("-Z", "Y")
    cam.rotation_euler = m.to_euler()
    # force the camera's own right/up to the intended basis
    R = [right.normalized(), up.normalized(), (-viewdir).normalized()]
    from mathutils import Matrix
    cam.matrix_world = (Matrix.Translation(centre - viewdir * 0.5)
                        @ Matrix((R[0], R[1], R[2])).transposed().to_4x4())
    sc.render.filepath = os.path.join(OUT, "hand_%s.png" % name)
    bpy.ops.render.render(write_still=True)
    mapping[name] = {
        "centre_world": [round(x, 6) for x in centre],
        "right": [round(x, 6) for x in right.normalized()],
        "up": [round(x, 6) for x in up.normalized()],
        "ortho_scale_m": SCALE, "resolution": RES,
        "pixel_to_world": "P = centre + right*((px/RES-0.5)*S) + up*((0.5-py/RES)*S)",
    }
    print("RENDERED", sc.render.filepath)

mapping["frame"] = {
    "hand_origin": [round(x, 6) for x in o],
    "palm_centre": [round(x, 6) for x in pc],
    "fing": [round(x, 6) for x in fing],
    "bar": [round(x, 6) for x in bar],
    "nrm": [round(x, 6) for x in nrm],
    "t_lo": round(lo, 6), "t_hi": round(hi, 6),
}
json.dump(mapping, open(os.path.join(OUT, "hand_ortho_mapping.json"), "w"), indent=2)
print("ORTHO_DONE")
