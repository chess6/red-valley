"""Standardized turnaround render of one GLB: front, side, back, three-quarter
stills at fixed camera/light setup, scaled to the object's own bounding box.
Rendering only -- no geometry edits, per docs/ASSET_POLICY.md.

Run headless:
  /opt/blender/blender --background --python tools/assetgen/glb_turnaround.py -- \
      --glb path/to/asset.glb --outdir path/to/renders/
"""
import bpy
import math
import os
import sys


def args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = {"glb": None, "outdir": None, "res": 1024}
    i = 0
    while i < len(argv):
        if argv[i] == "--glb":
            out["glb"] = argv[i + 1]; i += 2
        elif argv[i] == "--outdir":
            out["outdir"] = argv[i + 1]; i += 2
        elif argv[i] == "--res":
            out["res"] = int(argv[i + 1]); i += 2
        else:
            i += 1
    if not out["glb"] or not out["outdir"]:
        raise SystemExit("usage: --glb <path> --outdir <dir> [--res N]")
    return out


def main():
    a = args()
    os.makedirs(a["outdir"], exist_ok=True)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=a["glb"])
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if not meshes:
        raise SystemExit("glb_turnaround: no mesh objects found on import")

    xs, ys, zs = [], [], []
    for obj in meshes:
        for v in obj.bound_box:
            wv = obj.matrix_world @ __import__("mathutils").Vector(v)
            xs.append(wv.x); ys.append(wv.y); zs.append(wv.z)
    center = ((max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2, (max(zs) + min(zs)) / 2)
    radius = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs), 0.5)
    dist = radius * 2.4

    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 64
    scene.render.resolution_x = a["res"]
    scene.render.resolution_y = a["res"]
    scene.render.film_transparent = True

    sun_data = bpy.data.lights.new("sun", type="SUN")
    sun_data.energy = 3.0
    sun = bpy.data.objects.new("sun", sun_data)
    scene.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(55), 0, math.radians(35))

    fill_data = bpy.data.lights.new("fill", type="SUN")
    fill_data.energy = 1.0
    fill = bpy.data.objects.new("fill", fill_data)
    scene.collection.objects.link(fill)
    fill.rotation_euler = (math.radians(65), 0, math.radians(-140))

    cam_data = bpy.data.cameras.new("cam")
    cam = bpy.data.objects.new("cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam

    views = {"front": 0, "side": 90, "tq": 45, "back": 180}
    for name, yaw_deg in views.items():
        yaw = math.radians(yaw_deg)
        cam.location = (
            center[0] + dist * math.sin(yaw),
            center[1] - dist * math.cos(yaw),
            center[2] + radius * 0.15,
        )
        direction = __import__("mathutils").Vector(center) - cam.location
        cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
        scene.render.filepath = os.path.join(a["outdir"], f"{name}.png")
        bpy.ops.render.render(write_still=True)
        print(f"turnaround: wrote {scene.render.filepath}")


main()
