"""Bind the accepted mesh to the generated Rigify rig via a welded proxy.

Blender's bone-heat solver fails on this mesh because the glTF import splits
vertices at UV/normal seams, leaving the surface topologically disconnected. The
proven workaround: weld a copy, bind that, then transfer the weights back onto
the original UV-split mesh by position. The original keeps its UVs, material,
shape keys and vertex positions untouched -- only vertex groups are written.

  blender --background <rv_rigify.blend> --python bind_rigify.py -- <out.blend>
"""
import math, os, sys
import bpy, bmesh
from mathutils import Vector
from mathutils.kdtree import KDTree

OUT = sys.argv[sys.argv.index("--") + 1:][0]
rig = bpy.data.objects["rv_rigify"]
mesh = max([o for o in bpy.data.objects if o.type == "MESH"],
           key=lambda o: len(o.data.vertices))

before = dict(verts=len(mesh.data.vertices),
              polys=len(mesh.data.polygons),
              uvs=[l.name for l in mesh.data.uv_layers],
              mats=[m.name for m in mesh.data.materials if m],
              keys=[k.name for k in mesh.data.shape_keys.key_blocks]
                   if mesh.data.shape_keys else [],
              co=[v.co.copy() for v in mesh.data.vertices])

# ---------------------------------------------------------------- 1. weld ---
proxy = mesh.copy(); proxy.data = mesh.data.copy(); proxy.name = "weld_proxy"
bpy.context.collection.objects.link(proxy)
bpy.context.view_layer.objects.active = proxy
if proxy.data.shape_keys:
    proxy.shape_key_clear()
for m in list(proxy.modifiers): proxy.modifiers.remove(m)
bm = bmesh.new(); bm.from_mesh(proxy.data)
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
bm.to_mesh(proxy.data); bm.free(); proxy.data.update()
print("weld: %d verts -> %d verts (%.1f%% were seam duplicates)"
      % (before["verts"], len(proxy.data.vertices),
         100.0 * (before["verts"] - len(proxy.data.vertices)) / before["verts"]))
proxy.vertex_groups.clear()

# --------------------------------------------------- 2. automatic weights ---
for o in bpy.data.objects: o.select_set(False)
proxy.select_set(True); rig.select_set(True)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode="OBJECT")
try:
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")
except Exception as e:
    print("BIND_FAILED on the welded proxy:", e); raise
ngrp = len([g for g in proxy.vertex_groups if g.name.startswith("DEF-")])
unweighted = sum(1 for v in proxy.data.vertices if not v.groups)
print("proxy bound: %d DEF groups, %d unweighted verts" % (ngrp, unweighted))

# ------------------------------------------------ 3. transfer to original ---
kd = KDTree(len(proxy.data.vertices))
for i, v in enumerate(proxy.data.vertices): kd.insert(v.co, i)
kd.balance()
pgn = {g.index: g.name for g in proxy.vertex_groups}
for g in list(mesh.vertex_groups):
    if g.name.startswith("DEF-"): mesh.vertex_groups.remove(g)
for g in proxy.vertex_groups:
    if g.name not in mesh.vertex_groups: mesh.vertex_groups.new(name=g.name)
moved = 0
for v in mesh.data.vertices:
    _, idx, d = kd.find(v.co)
    if d > 1e-4: moved += 1
    for g in proxy.data.vertices[idx].groups:
        n = pgn.get(g.group)
        if n: mesh.vertex_groups[n].add([v.index], g.weight, "REPLACE")
print("transferred weights to %d verts (%d had no exact weld partner)"
      % (len(mesh.data.vertices), moved))

for m in list(mesh.modifiers): mesh.modifiers.remove(m)
mod = mesh.modifiers.new("Armature", "ARMATURE"); mod.object = rig
mesh.parent = rig
bpy.data.objects.remove(proxy, do_unlink=True)

# ------------------------------------------- 4. thumb correction + face -----
GI = {g.name: g.index for g in mesh.vertex_groups}
def wsum(v, pred):
    return sum(g.weight for g in v.groups
               if pred(next((k for k, i in GI.items() if i == g.group), "")))
thumbish = [v for v in mesh.data.vertices
            if wsum(v, lambda n: "thumb" in n) > 0.0]
onforearm = [v for v in thumbish if wsum(v, lambda n: "forearm" in n) > 0.25]
print("THUMB: %d verts carry thumb weight; %d of them still carry >0.25 forearm"
      % (len(thumbish), len(onforearm)))

# rigid face: skull rides DEF-spine.006, neck blending stops below the jaw
head_b = rig.data.bones.get("DEF-spine.006")
if head_b and "DEF-spine.006" in GI:
    jaw = (rig.matrix_world @ head_b.matrix_local).to_translation().z
    hg = mesh.vertex_groups["DEF-spine.006"]
    band, fixed = 0.02, 0
    for v in mesh.data.vertices:
        z = (mesh.matrix_world @ v.co).z
        if z < jaw - band: continue
        wh = next((g.weight for g in v.groups if g.group == GI["DEF-spine.006"]), 0.0)
        f = 1.0 if z >= jaw else (z - (jaw - band)) / band
        new = wh + (1.0 - wh) * f
        if abs(new - wh) < 1e-6: continue
        scale = 0.0 if wh >= 1.0 else (1.0 - new) / (1.0 - wh)
        for g in list(v.groups):
            if g.group == GI["DEF-spine.006"]: continue
            nm = next((k for k, i in GI.items() if i == g.group), None)
            if nm: mesh.vertex_groups[nm].add([v.index], g.weight * scale, "REPLACE")
        hg.add([v.index], new, "REPLACE")
        fixed += 1
    print("face/skull made rigid on DEF-spine.006: %d verts (jaw z=%.4f)" % (fixed, jaw))

# ------------------------------------------------------ 5. preservation -----
after = dict(verts=len(mesh.data.vertices), polys=len(mesh.data.polygons),
             uvs=[l.name for l in mesh.data.uv_layers],
             mats=[m.name for m in mesh.data.materials if m],
             keys=[k.name for k in mesh.data.shape_keys.key_blocks]
                  if mesh.data.shape_keys else [])
drift = max(((before["co"][i] - v.co).length for i, v in enumerate(mesh.data.vertices)),
            default=0.0)
print("PRESERVE verts %d->%d  polys %d->%d" % (before["verts"], after["verts"],
                                               before["polys"], after["polys"]))
print("PRESERVE uvs %s  materials %s" % (after["uvs"], after["mats"]))
print("PRESERVE shape keys %s" % (after["keys"],))
print("PRESERVE max vertex drift %.9f m" % drift)
nw = sum(1 for v in mesh.data.vertices if not v.groups)
print("PRESERVE unweighted verts on the bound mesh: %d" % nw)
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("BIND_DONE")
