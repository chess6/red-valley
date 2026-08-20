"""Generate the Rigify rig from the aligned metarig and verify it. Iteration 1.

Verification only -- no binding, no weights, no animation.

  blender --background <metarig.blend> --python generate_rigify.py -- <out.blend>
"""
import json, math, os, sys
import bpy, addon_utils
from mathutils import Vector

def _enable_rigify():
    for m in addon_utils.modules():
        if "rigify" in m.__name__.lower():
            try: addon_utils.enable(m.__name__, default_set=False)
            except Exception as e: print("rigify enable note:", e)
_enable_rigify()

OUT = sys.argv[sys.argv.index("--") + 1:][0]
meta = bpy.data.objects["rv_metarig"]
mesh = max([o for o in bpy.data.objects if o.type == "MESH"],
           key=lambda o: len(o.data.vertices))

bpy.ops.object.mode_set(mode="OBJECT")
for o in bpy.data.objects: o.select_set(False)
meta.select_set(True)
bpy.context.view_layer.objects.active = meta
try:
    bpy.ops.pose.rigify_generate()
except Exception as e:
    print("GENERATE_FAILED:", e); raise
gen = bpy.context.view_layer.objects.active
gen.name = "rv_rigify"
print("generated rig: %s, %d bones" % (gen.name, len(gen.data.bones)))

names = [b.name for b in gen.data.bones]
DEF = sorted(n for n in names if n.startswith("DEF-"))
ORG = [n for n in names if n.startswith("ORG-")]
MCH = [n for n in names if n.startswith("MCH-")]
CTRL = [n for n in names if not n.startswith(("DEF-", "ORG-", "MCH-"))]
print("VERIFY bones total=%d  DEF=%d  ORG=%d  MCH=%d  ctrl=%d"
      % (len(names), len(DEF), len(ORG), len(MCH), len(CTRL)))

fing = [n for n in DEF if any(k in n for k in
        ("f_index", "f_middle", "f_ring", "f_pinky", "thumb"))]
print("VERIFY deform finger bones=%d (expect 30)" % len(fing))
for d in ("thumb", "f_index", "f_middle", "f_ring", "f_pinky"):
    L = sorted(n for n in fing if n.endswith(".L") and d in n)
    R = sorted(n for n in fing if n.endswith(".R") and d in n)
    print("   %-9s L=%d R=%d" % (d, len(L), len(R)))

# handedness: this character faces -Y, so anatomical right is -X
bad = []
for n in DEF:
    b = gen.data.bones[n]
    c = (gen.matrix_world @ b.matrix_local).to_translation()
    if n.endswith(".R") and c.x > 0.005: bad.append((n, round(c.x, 4)))
    if n.endswith(".L") and c.x < -0.005: bad.append((n, round(c.x, 4)))
print("VERIFY handedness violations: %d %s" % (len(bad), bad[:5]))

# symmetry: mirror each .R deform bone and compare with its .L partner
asym = []
for n in DEF:
    if not n.endswith(".R"): continue
    p = n[:-2] + ".L"
    if p not in gen.data.bones: asym.append((n, "no partner")); continue
    a = (gen.matrix_world @ gen.data.bones[n].matrix_local).to_translation()
    b = (gen.matrix_world @ gen.data.bones[p].matrix_local).to_translation()
    d = (Vector((-a.x, a.y, a.z)) - b).length
    if d > 0.004: asym.append((n, round(d, 4)))
print("VERIFY symmetry: %d bones off by >4 mm %s" % (len(asym), asym[:6]))

# rest alignment: every deform bone head should sit inside the mesh volume
from mathutils.bvhtree import BVHTree
mesh.data.calc_loop_triangles()
bvh = BVHTree.FromPolygons([mesh.matrix_world @ v.co for v in mesh.data.vertices],
                           [tuple(t.vertices) for t in mesh.data.loop_triangles],
                           all_triangles=True)
out = []
for n in DEF:
    h = (gen.matrix_world @ gen.data.bones[n].matrix_local).to_translation()
    loc, nor, idx, dist = bvh.find_nearest(h)
    if dist is not None and dist > 0.030: out.append((n, round(dist, 4)))
print("VERIFY rest alignment: %d deform bones >30 mm from the surface %s"
      % (len(out), out[:6]))

# the accepted mesh must be untouched
mesh.data.calc_loop_triangles()
print("VERIFY mesh verts=%d tris=%d groups=%d shapekeys=%s uvs=%d materials=%d"
      % (len(mesh.data.vertices), len(mesh.data.loop_triangles),
         len(mesh.vertex_groups),
         [k.name for k in mesh.data.shape_keys.key_blocks] if mesh.data.shape_keys else None,
         len(mesh.data.uv_layers), len(mesh.data.materials)))

bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("GENERATE_DONE")
