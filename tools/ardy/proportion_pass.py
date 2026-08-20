"""Reversible proportion pass on a DERIVED copy. The Rodin master is read-only.

Everything here is a shape key, so setting its value to 0 restores the mesh
exactly. No vertex is added, removed or re-ordered, so UVs, textures, material
assignment and vertex order are untouched. Nothing is remeshed.

These edits correct the rest silhouette against the approved concept. They are
NOT a way to hide rigging defects -- the rigging issues are recorded separately
and unchanged by this pass.

  blender --background --python proportion_pass.py -- <rigged.glb> <out.glb> [strength]
"""
import math, sys, os
import bpy, mathutils
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:]
SRC, OUT = argv[0], argv[1]
STRENGTH = float(argv[2]) if len(argv) > 2 else 1.0

# magnitudes, calibrated against the concept front view (modest by intent)
NECK_SCALE_X  = 0.92     # 8% narrower neck
WAIST_SCALE_X = 0.955    # 4.5% narrower waist, symmetric about x=0
PELVIS_BACK_M = 0.015    # 1.5 cm backward, removes the thrust in side view

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=SRC)
obj = max([o for o in bpy.data.objects if o.type == "MESH" and len(o.vertex_groups)],
          key=lambda o: len(o.data.vertices))
rig = [o for o in bpy.data.objects if o.type == "ARMATURE"][0]
print("mesh:", obj.name, len(obj.data.vertices), "verts")

co = np.array([v.co[:] for v in obj.data.vertices])
zmin, zmax = co[:, 2].min(), co[:, 2].max()
H = zmax - zmin

def window(z, lo, hi, feather):
    """raised-cosine window in normalised height: 1 inside, 0 outside"""
    zl, zh = zmin + lo*H, zmin + hi*H
    fe = feather * H
    if z <= zl - fe or z >= zh + fe:
        return 0.0
    if zl <= z <= zh:
        return 1.0
    d = (zl - z) if z < zl else (z - zh)
    return 0.5 * (1.0 + math.cos(math.pi * d / fe))

if obj.data.shape_keys is None:
    obj.shape_key_add(name="Basis", from_mix=False)

def add_key(name, fn):
    k = obj.shape_key_add(name=name, from_mix=False)
    n = 0
    for i, v in enumerate(k.data):
        p = mathutils.Vector(co[i])
        q = fn(p)
        if (q - p).length > 1e-6:
            v.co = q; n += 1
    k.value = STRENGTH
    k.slider_min, k.slider_max = 0.0, 1.0
    print("  shape key '%s': %d vertices moved" % (name, n))
    return k

def neck(p):
    w = window(p.z, 0.835, 0.895, 0.035)
    if w <= 0: return p
    s = 1.0 + (NECK_SCALE_X - 1.0) * w
    return mathutils.Vector((p.x * s, p.y, p.z))

def waist(p):
    w = window(p.z, 0.575, 0.660, 0.045)
    if w <= 0: return p
    s = 1.0 + (WAIST_SCALE_X - 1.0) * w
    return mathutils.Vector((p.x * s, p.y, p.z))

def pelvis(p):
    w = window(p.z, 0.455, 0.570, 0.055)
    if w <= 0: return p
    return mathutils.Vector((p.x, p.y + PELVIS_BACK_M * w, p.z))

add_key("fix_neck_width", neck)
add_key("fix_waist_width", waist)
add_key("fix_pelvis_thrust", pelvis)

# ---- neck articulation: the neck region is dominantly weighted to `head`,
# so the neck bone barely moves the mesh. Blend weight back toward `neck`
# with height, leaving the skull on `head`.
gi = {g.name: g.index for g in obj.vertex_groups}
if "neck" in gi and "head" in gi:
    vg_neck, vg_head = obj.vertex_groups["neck"], obj.vertex_groups["head"]
    moved = 0
    for i, v in enumerate(obj.data.vertices):
        z = co[i][2]
        w = window(z, 0.830, 0.880, 0.020)     # neck column only
        if w <= 0: continue
        hw_ = next((g.weight for g in v.groups if g.group == gi["head"]), 0.0)
        if hw_ <= 0.01: continue
        take = hw_ * 0.75 * w                  # move up to 75% of head weight
        nw = next((g.weight for g in v.groups if g.group == gi["neck"]), 0.0)
        vg_head.add([i], max(0.0, hw_ - take), "REPLACE")
        vg_neck.add([i], nw + take, "REPLACE")
        moved += 1
    print("  neck weights rebalanced on %d vertices" % moved)

bpy.ops.object.select_all(action="DESELECT")
obj.select_set(True); rig.select_set(True)
bpy.context.view_layer.objects.active = rig
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", use_selection=True,
                          export_skins=True, export_morph=True,
                          export_cameras=False, export_lights=False)
print("PROPORTION_PASS_DONE ->", OUT)
