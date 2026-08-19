"""Standardised review renders for a generated GLB. Blender headless.

Validation and rendering only: this script imports an asset and photographs
it. It never edits geometry -- see docs/ASSET_POLICY.md. Four fixed cameras
(front / three-quarter / side / back) at one fixed framing, so candidates from
different runs are directly comparable side by side.

  blender --background --python tools/assetgen/render_review.py -- IN.glb OUTDIR
"""
import json
import math
import sys
from pathlib import Path

import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
src, outdir = Path(argv[0]), Path(argv[1])
outdir.mkdir(parents=True, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(src))

meshes = [o for o in bpy.data.objects if o.type == "MESH"]
if not meshes:
    raise SystemExit(f"FAIL: {src} imported no mesh objects")

# world-space bounds, so framing does not depend on the exporter's transforms
lo = [float("inf")] * 3
hi = [float("-inf")] * 3
tris = 0
for o in meshes:
    o.data.calc_loop_triangles()
    tris += len(o.data.loop_triangles)
    for corner in o.bound_box:
        w = o.matrix_world @ __import__("mathutils").Vector(corner)
        for i in range(3):
            lo[i] = min(lo[i], w[i]); hi[i] = max(hi[i], w[i])
size = [hi[i] - lo[i] for i in range(3)]
centre = [(hi[i] + lo[i]) / 2 for i in range(3)]
radius = max(size) or 1.0

stats = {
    "source": str(src),
    "objects": len(meshes),
    "triangles": tris,
    "bbox_min": lo, "bbox_max": hi, "size": size,
    "materials": sorted({m.name for o in meshes for m in o.data.materials if m}),
    "images": sorted({i.name: list(i.size) for i in bpy.data.images if i.size[0]}.items()),
    "uv_layers": sorted({uv.name for o in meshes for uv in o.data.uv_layers}),
}

world = bpy.data.worlds.new("W")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[1].default_value = 1.4
bpy.context.scene.world = world

key = bpy.data.objects.new("key", bpy.data.lights.new("key", "AREA"))
key.data.energy = 900 * radius ** 2
key.data.size = 3 * radius
key.location = (centre[0] + 2 * radius, centre[1] - 2.5 * radius, centre[2] + 2 * radius)
key.rotation_euler = (math.radians(60), 0, math.radians(40))
bpy.context.collection.objects.link(key)

cam_data = bpy.data.cameras.new("cam")
cam_data.lens = 70
cam = bpy.data.objects.new("cam", cam_data)
bpy.context.collection.objects.link(cam)
bpy.context.scene.camera = cam

scene = bpy.context.scene
# the EEVEE enum has been renamed between Blender versions; pick what exists
engines = scene.render.bl_rna.properties["engine"].enum_items.keys()
scene.render.engine = next(e for e in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES")
                           if e in engines)
scene.render.resolution_x = scene.render.resolution_y = 900
scene.render.film_transparent = False

VIEWS = {"front": 0, "three_quarter": 40, "side": 90, "back": 180}
dist = radius * 3.1
written = {}
for name, yaw in VIEWS.items():
    a = math.radians(yaw)
    cam.location = (centre[0] + dist * math.sin(a),
                    centre[1] - dist * math.cos(a),
                    centre[2] + radius * 0.18)
    cam.rotation_euler = (math.radians(90), 0, a)
    path = outdir / f"review_{name}.png"
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    written[name] = str(path)

stats["renders"] = written
(outdir / "render_stats.json").write_text(json.dumps(stats, indent=2, default=str))
print("RENDER_STATS " + json.dumps(stats, default=str))
