"""Bake one neutral-pose, texture-embedded copy of the proportioned mesh.

For third-party autorig benchmarking (Mixamo). Read-only with respect to the
accepted asset: it imports, strips, bakes and exports elsewhere. Nothing in
art/animation/ardy_pilot/derived/ is written.

  blender --background --python bake_for_autorig.py -- <src.glb> <out.fbx>
"""
import hashlib, json, os, sys
import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
SRC, OUT = argv[0], argv[1]
os.makedirs(os.path.dirname(OUT), exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=SRC)

mesh = max([o for o in bpy.data.objects if o.type == "MESH"],
           key=lambda o: len(o.data.vertices))
removed = []
for o in list(bpy.data.objects):
    if o is mesh:
        continue
    removed.append("%s(%s)" % (o.name, o.type))
    bpy.data.objects.remove(o, do_unlink=True)
print("stripped: %s" % ", ".join(removed))

for m in list(mesh.modifiers):
    mesh.modifiers.remove(m)

# Bake the accepted proportion shape keys into the base mesh, then drop them.
keys = []
if mesh.data.shape_keys:
    keys = [(k.name, round(k.value, 4)) for k in mesh.data.shape_keys.key_blocks]
    bpy.context.view_layer.objects.active = mesh
    mesh.select_set(True)
    baked = mesh.shape_key_add(name="_bake", from_mix=True)
    co = [d.co.copy() for d in baked.data]
    bpy.ops.object.shape_key_remove(all=True)
    for i, v in enumerate(mesh.data.vertices):
        v.co = co[i]
print("baked shape keys: %s" % keys)

# Mixamo re-rigs from scratch; stale groups would only confuse the result.
mesh.vertex_groups.clear()
mesh.matrix_world.identity()
mesh.data.calc_loop_triangles()

bpy.ops.export_scene.fbx(filepath=OUT, use_selection=False, object_types={"MESH"},
                         path_mode="COPY", embed_textures=True,
                         add_leaf_bones=False, bake_anim=False,
                         apply_scale_options="FBX_SCALE_ALL", global_scale=1.0)

def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()

bb = [Vector(c) for c in mesh.bound_box]
prov = {
    "purpose": "Mixamo autorig benchmark upload (evaluation only)",
    "NOT_FOR_SHIPPING": True,
    "source_asset": SRC,
    "source_sha256": sha(SRC),
    "output": OUT,
    "output_sha256": sha(OUT),
    "output_bytes": os.path.getsize(OUT),
    "blender": bpy.app.version_string,
    "stripped_objects": removed,
    "shape_keys_baked": keys,
    "vertex_groups": "cleared (Mixamo re-rigs)",
    "vertices": len(mesh.data.vertices),
    "polygons": len(mesh.data.polygons),
    "triangles": len(mesh.data.loop_triangles),
    "height_m": round(max(b.z for b in bb) - min(b.z for b in bb), 4),
    "textures": sorted(set("%s %dx%d" % (i.name, i.size[0], i.size[1])
                           for i in bpy.data.images if i.size[0])),
    "pose": "neutral rest (armature removed; no bone had a non-rest pose)",
    "contains": "single mesh only; no props, cameras, lights or helper objects",
}
json.dump(prov, open(OUT.replace(".fbx", ".provenance.json"), "w"), indent=2)
print(json.dumps(prov, indent=2))
print("BAKE_DONE")
