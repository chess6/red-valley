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
# optional yaw offset: some generators emit the subject facing away, so the
# labelled views must be rotated to stay comparable across candidates
yaw_offset = float(argv[2]) if len(argv) > 2 else 0.0
outdir.mkdir(parents=True, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(src))

meshes = [o for o in bpy.data.objects if o.type == "MESH"]
if not meshes:
    raise SystemExit(f"FAIL: {src} imported no mesh objects")

# Generators disagree on the up axis: some export Y-up, which lands the subject
# lying down. Stand it up by rotating so the longest extent runs along Z, then
# bake the rotation in so world coordinates are what the cameras expect.
def _world_extents():
    lo3 = [float("inf")] * 3
    hi3 = [float("-inf")] * 3
    for o in meshes:
        for corner in o.bound_box:
            w = o.matrix_world @ mathutils.Vector(corner)
            for i in range(3):
                lo3[i] = min(lo3[i], w[i]); hi3[i] = max(hi3[i], w[i])
    return [hi3[i] - lo3[i] for i in range(3)]

import mathutils
ext = _world_extents()
tall = max(range(3), key=lambda i: ext[i])
if tall != 2:
    axis = "X" if tall == 1 else "Y"
    rot = mathutils.Matrix.Rotation(math.radians(-90), 4, axis)
    for o in meshes:
        o.matrix_world = rot @ o.matrix_world
    bpy.context.view_layer.update()
    print(f"up-axis normalised: rotated 90 deg about {axis} (was {'XYZ'[tall]}-up)")

# Vertex-colour meshes (e.g. TripoSR's default path) carry a COLOR_0 attribute
# and no texture. Wire it into Base Color, or the render comes out blank white.
for o in meshes:
    cols = getattr(o.data, "color_attributes", None)
    has_tex = any(m and m.use_nodes and any(n.type == "TEX_IMAGE" for n in m.node_tree.nodes)
                  for m in o.data.materials)
    if cols and len(cols) and not has_tex:
        mat = bpy.data.materials.new(f"vcol_{o.name}")
        mat.use_nodes = True
        nt = mat.node_tree
        bsdf = nt.nodes.get("Principled BSDF")
        ca = nt.nodes.new("ShaderNodeVertexColor")
        ca.layer_name = cols[0].name
        nt.links.new(ca.outputs["Color"], bsdf.inputs["Base Color"])
        o.data.materials.clear()
        o.data.materials.append(mat)
        print(f"vertex colours wired for {o.name} (attribute '{cols[0].name}')")

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
world.node_tree.nodes["Background"].inputs[1].default_value = 0.55
bpy.context.scene.world = world

key = bpy.data.objects.new("key", bpy.data.lights.new("key", "AREA"))
key.data.energy = 260 * radius ** 2
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
# Blender 4.x defaults to the AgX view transform, which is a film emulation:
# it desaturates and rolls off highlights, washing an asset review out. Use
# Standard so what is rendered is the albedo actually stored in the file.
try:
    scene.view_settings.view_transform = "Standard"
except TypeError:
    pass

VIEWS = {"front": 0, "three_quarter": 40, "side": 90, "back": 180}
dist = radius * 3.1
written = {}
for name, yaw in VIEWS.items():
    a = math.radians(yaw + yaw_offset)
    cam.location = (centre[0] + dist * math.sin(a),
                    centre[1] - dist * math.cos(a),
                    centre[2] + radius * 0.18)
    cam.rotation_euler = (math.radians(90), 0, a)
    path = outdir / f"review_{name}.png"
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    written[name] = str(path)

# face + torso close-up, framed on the upper eighth of the bounding box
fa = math.radians(yaw_offset)
head_z = hi[2] - size[2] * 0.10
cam_data.lens = 105
cdist = radius * 0.95
cam.location = (centre[0] + cdist * math.sin(fa),
                centre[1] - cdist * math.cos(fa),
                head_z)
cam.rotation_euler = (math.radians(90), 0, fa)
scene.render.filepath = str(outdir / "review_face.png")
bpy.ops.render.render(write_still=True)
written["face"] = str(outdir / "review_face.png")
cam_data.lens = 70

stats["renders"] = written
(outdir / "render_stats.json").write_text(json.dumps(stats, indent=2, default=str))
print("RENDER_STATS " + json.dumps(stats, default=str))
