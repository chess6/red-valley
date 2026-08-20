"""Overlay renders of the generated Rigify deform bones on the character.

Bones are drawn as emissive proxy cylinders because armature display is a
viewport feature and does not appear in a background render.

  blender --background <rv_rigify.blend> --python overlay_rigify.py -- <outdir>
"""
import json, math, os, sys
import bpy
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

OUT = sys.argv[sys.argv.index("--") + 1:][0]
os.makedirs(OUT, exist_ok=True)
rig = bpy.data.objects["rv_rigify"]
mesh = max([o for o in bpy.data.objects if o.type == "MESH"],
           key=lambda o: len(o.data.vertices))
MAP = json.load(open("art/animation/rigify/hand_ortho_mapping.json"))
F = MAP["frame"]
CEN = Vector(MAP["palm_depth"]["centre_world"])
BAR, NRM, FING = Vector(F["bar"]), Vector(F["nrm"]), Vector(F["fing"])

DEF = [b for b in rig.data.bones if b.name.startswith("DEF-")]

# ---- corrected rest-alignment test: inside/outside, not distance-to-surface --
mesh.data.calc_loop_triangles()
verts = [mesh.matrix_world @ v.co for v in mesh.data.vertices]
tris = [tuple(t.vertices) for t in mesh.data.loop_triangles]
bvh = BVHTree.FromPolygons(verts, tris, all_triangles=True)
def inside(p):
    hits = 0
    for d in (Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))):
        n, o_, cnt = 0, p.copy(), 0
        while cnt < 64:
            r = bvh.ray_cast(o_ + d * 1e-5, d)
            if r[0] is None: break
            o_ = r[0]; n += 1; cnt += 1
        hits += (n % 2)
    return hits >= 2
outside = [b.name for b in DEF
           if not inside((rig.matrix_world @ b.matrix_local).to_translation())]
print("VERIFY rest alignment: %d of %d deform-bone heads lie OUTSIDE the mesh %s"
      % (len(outside), len(DEF), outside[:8]))

# ---- bone proxies -----------------------------------------------------------
col = bpy.data.materials.new("bone"); col.use_nodes = True
nt = col.node_tree
for n in list(nt.nodes):
    if n.type != "OUTPUT_MATERIAL": nt.nodes.remove(n)
em = nt.nodes.new("ShaderNodeEmission")
em.inputs["Color"].default_value = (1.0, 0.35, 0.1, 1)
em.inputs["Strength"].default_value = 3.0
nt.links.new(em.outputs["Emission"], nt.nodes["Material Output"].inputs["Surface"])
fcol = bpy.data.materials.new("bonef"); fcol.use_nodes = True
nt2 = fcol.node_tree
for n in list(nt2.nodes):
    if n.type != "OUTPUT_MATERIAL": nt2.nodes.remove(n)
em2 = nt2.nodes.new("ShaderNodeEmission")
em2.inputs["Color"].default_value = (0.15, 0.9, 1.0, 1)
em2.inputs["Strength"].default_value = 4.0
nt2.links.new(em2.outputs["Emission"], nt2.nodes["Material Output"].inputs["Surface"])

FINGKEY = ("f_index", "f_middle", "f_ring", "f_pinky", "thumb", "palm.")
proxies = []
for b in DEF:
    h = rig.matrix_world @ Vector(b.head_local)
    t = rig.matrix_world @ Vector(b.tail_local)
    v = t - h
    if v.length < 1e-5: continue
    isf = any(k in b.name for k in FINGKEY)
    r = 0.0018 if isf else 0.006
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=v.length,
                                        location=(h + t) / 2, vertices=8)
    o = bpy.context.object
    o.rotation_mode = "QUATERNION"
    o.rotation_quaternion = v.to_track_quat("Z", "Y")
    o.data.materials.append(fcol if isf else col)
    proxies.append(o)
print("bone proxies: %d" % len(proxies))

clay = bpy.data.materials.new("clay"); clay.use_nodes = True
bs = clay.node_tree.nodes["Principled BSDF"]
bs.inputs["Base Color"].default_value = (0.52, 0.53, 0.56, 1)
bs.inputs["Roughness"].default_value = 0.7
mesh.data.materials.clear(); mesh.data.materials.append(clay)

sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.view_settings.view_transform = "Standard"
sc.render.image_settings.file_format = "PNG"
try:
    sc.eevee.use_raytracing = True; sc.eevee.use_shadows = True
except AttributeError: pass
sc.world = sc.world or bpy.data.worlds.new("W"); sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs[0].default_value = (.13, .14, .17, 1)
bpy.ops.object.light_add(type="SUN", location=(3, -4, 5))
k = bpy.context.object; k.data.energy = 2.6
k.rotation_euler = (math.radians(48), 0, math.radians(28))
cd = bpy.data.cameras.new("C"); cam = bpy.data.objects.new("C", cd)
sc.collection.objects.link(cam); sc.camera = cam

def ortho(name, centre, right, up, scale, res=1200):
    cd.type = "ORTHO"; cd.ortho_scale = scale
    sc.render.resolution_x = sc.render.resolution_y = res
    view = right.normalized().cross(up.normalized())
    R = [right.normalized(), up.normalized(), view.normalized()]
    cam.matrix_world = (Matrix.Translation(centre + view * 1.5)
                        @ Matrix((R[0], R[1], R[2])).transposed().to_4x4())
    sc.render.filepath = os.path.join(OUT, "overlay_%s.png" % name)
    bpy.ops.render.render(write_still=True)
    print("RENDERED", sc.render.filepath)

body = Vector((0, 0, 0.95))
ortho("front", body, Vector((1, 0, 0)), Vector((0, 0, 1)), 2.1)
ortho("side", body, Vector((0, -1, 0)), Vector((0, 0, 1)), 2.1)

# hand plates: isolate the hand so the thigh does not block the palm camera
gi = {g.name: g.index for g in mesh.vertex_groups}
def wt(v, n):
    i = gi.get(n)
    return next((g.weight for g in v.groups if g.group == i), 0.0) if i is not None else 0.0
import bmesh
t_lo = F["t_lo"]
o_h = Vector(F["hand_origin"])
keep = set()
for v in mesh.data.vertices:
    p = mesh.matrix_world @ v.co
    if (p - CEN).length > 0.090: continue
    if (p - o_h).dot(FING) < t_lo - 0.006: continue
    if wt(v, "hand.R") >= 0.40 or wt(v, "forearm.R") >= 0.40: keep.add(v.index)
bm = bmesh.new(); bm.from_mesh(mesh.data); bm.verts.ensure_lookup_table()
bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.index not in keep], context="VERTS")
bm.to_mesh(mesh.data); bm.free(); mesh.data.update()
for m in list(mesh.modifiers): mesh.modifiers.remove(m)
ortho("palm", CEN, BAR, FING, 0.15)
ortho("edge", CEN, NRM, FING, 0.15)
print("OVERLAY_DONE")
