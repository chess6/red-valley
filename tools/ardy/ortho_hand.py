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
# The accepted rig weights much of the thumb/thenar mass to forearm.R (254 of
# 549 vertices standing proud of the palm), so isolating on hand weight alone
# deletes the thumb. Include forearm-dominated vertices that sit past the wrist
# station, which keeps the thumb and drops the arm shaft.
t_lo_cut = lo - 0.006
keep = set()
for v in obj.data.vertices:
    p_ = obj.matrix_world @ v.co
    if (p_ - centre).length > 0.090: continue
    if (p_ - o).dot(fing) < t_lo_cut: continue
    if wt(v, "hand." + SIDE) >= 0.40 or wt(v, "forearm." + SIDE) >= 0.40:
        keep.add(v.index)
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

def depth_material(axis, origin, lo=-0.030, hi=0.030):
    """Colour = position along `axis`, so the plate carries depth as well as
    silhouette. Without this the curled phalanges overlap in every direction and
    joints cannot be read from any single view."""
    m = bpy.data.materials.new("depth"); m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        if n.type != "OUTPUT_MATERIAL": nt.nodes.remove(n)
    out = nt.nodes["Material Output"]
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sub = nt.nodes.new("ShaderNodeVectorMath"); sub.operation = "SUBTRACT"
    sub.inputs[1].default_value = origin
    dot = nt.nodes.new("ShaderNodeVectorMath"); dot.operation = "DOT_PRODUCT"
    dot.inputs[1].default_value = axis
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value = lo; mr.inputs["From Max"].default_value = hi
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = "LINEAR"
    ramp.color_ramp.elements[0].color = (0.05, 0.15, 0.9, 1)
    ramp.color_ramp.elements[1].color = (1.0, 0.85, 0.1, 1)
    e = ramp.color_ramp.elements.new(0.5); e.color = (0.1, 0.9, 0.4, 1)
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(geo.outputs["Position"], sub.inputs[0])
    nt.links.new(sub.outputs["Vector"], dot.inputs[0])
    nt.links.new(dot.outputs["Value"], mr.inputs["Value"])
    nt.links.new(mr.outputs["Result"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], em.inputs["Color"])
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    return m

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

# depth-coded palm plate: same camera, colour carries the nrm coordinate
dm = depth_material(list(nrm), list(centre))
obj.data.materials.clear(); obj.data.materials.append(dm)
viewdir, right, up = VIEWS["palm"]
from mathutils import Matrix as _M
R = [right.normalized(), up.normalized(), (-viewdir).normalized()]
cam.matrix_world = (_M.Translation(centre - viewdir * 0.5)
                    @ _M((R[0], R[1], R[2])).transposed().to_4x4())
sc.render.filepath = os.path.join(OUT, "hand_palm_depth.png")
bpy.ops.render.render(write_still=True)
print("RENDERED", sc.render.filepath)
mapping["palm_depth"] = dict(mapping["palm"])
mapping["palm_depth"]["encoding"] = ("colour = nrm offset from centre; blue=-30mm, "
                                     "green=0mm, yellow=+30mm, linear")

# edge depth plate: depth along bar, to separate the thumb from the index mass
dm2 = depth_material(list(bar), list(centre), -0.045, 0.045)
obj.data.materials.clear(); obj.data.materials.append(dm2)
viewdir, right, up = VIEWS["edge"]
R = [right.normalized(), up.normalized(), (-viewdir).normalized()]
cam.matrix_world = (_M.Translation(centre - viewdir * 0.5)
                    @ _M((R[0], R[1], R[2])).transposed().to_4x4())
sc.render.filepath = os.path.join(OUT, "hand_edge_depth.png")
bpy.ops.render.render(write_still=True)
print("RENDERED", sc.render.filepath)
# axial plate: looking straight down the finger axis from the fingertip side.
# The curl runs along the view direction here, so it stops occluding and each
# digit reads as its own cross-section.
dm3 = depth_material(list(fing), list(centre), -0.050, 0.050)
obj.data.materials.clear(); obj.data.materials.append(dm3)
ax_view, ax_right, ax_up = -fing, bar, nrm
R = [ax_right.normalized(), ax_up.normalized(), (-ax_view).normalized()]
cam.matrix_world = (_M.Translation(centre - ax_view * 0.5)
                    @ _M((R[0], R[1], R[2])).transposed().to_4x4())
sc.render.filepath = os.path.join(OUT, "hand_axial_depth.png")
bpy.ops.render.render(write_still=True)
print("RENDERED", sc.render.filepath)
mapping["axial_depth"] = {
    "centre_world": [round(x, 6) for x in centre],
    "right": [round(x, 6) for x in bar.normalized()],
    "up": [round(x, 6) for x in nrm.normalized()],
    "ortho_scale_m": SCALE, "resolution": RES,
    "pixel_to_world": "P = centre + right*((px/RES-0.5)*S) + up*((0.5-py/RES)*S)",
    "encoding": "colour = fing offset from centre; blue=-50mm, green=0, yellow=+50mm",
    "note": "viewed from the fingertip side, looking along -fing",
}

mapping["edge_depth"] = dict(mapping["edge"])
mapping["edge_depth"]["encoding"] = ("colour = bar offset from centre; blue=-45mm, "
                                     "green=0mm, yellow=+45mm, linear")

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
