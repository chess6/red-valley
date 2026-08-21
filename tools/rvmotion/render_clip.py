"""Render a retargeted clip: three-quarter, side, and the true gameplay camera.

  blender --background <clip.blend> --python render_clip.py -- <outdir> [--soil 0.22]
"""
import math, os, sys
import bpy
from mathutils import Vector

A = sys.argv[sys.argv.index("--") + 1:]
OUT = A[0]
SOIL = float(next((A[i + 1] for i, x in enumerate(A) if x == "--soil"), 0.0))
os.makedirs(OUT, exist_ok=True)
rig = bpy.data.objects["rv_rigify"]
bpy.context.view_layer.objects.active = rig
if rig.mode != "OBJECT": bpy.ops.object.mode_set(mode="OBJECT")
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"; sc.view_settings.view_transform = "Standard"
try: sc.eevee.use_raytracing = True; sc.eevee.use_shadows = True
except AttributeError: pass
sc.world = sc.world or bpy.data.worlds.new("W"); sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs[0].default_value = (.30, .34, .40, 1)
if not any(o.type == "LIGHT" for o in bpy.data.objects):
    bpy.ops.object.light_add(type="SUN", location=(3, -4, 5))
    k = bpy.context.object; k.data.energy = 3.2
    k.rotation_euler = (math.radians(46), 0, math.radians(28))
    bpy.ops.object.light_add(type="AREA", location=(-3, -3, 2))
    fl = bpy.context.object; fl.data.energy = 260; fl.data.size = 5
    fl.rotation_euler = (math.radians(75), 0, math.radians(-45))
bpy.ops.mesh.primitive_plane_add(size=14, location=(0, 0, 0))
gm = bpy.data.materials.new("g"); gm.use_nodes = True
gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (.30, .32, .30, 1)
bpy.context.object.data.materials.append(gm)
if SOIL > 0:
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -0.85, SOIL / 2))
    bed = bpy.context.object; bed.scale = (1.6, 1.0, SOIL)
    bm = bpy.data.materials.new("s"); bm.use_nodes = True
    bm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (.18, .11, .07, 1)
    bed.data.materials.append(bm)
cd = bpy.data.cameras.new("C"); cam = bpy.data.objects.new("C", cd)
sc.collection.objects.link(cam); sc.camera = cam
sc.render.image_settings.file_format = "PNG"
focus = Vector((0, -0.1, 1.0))
for tag, az, dist, lens, rx, ry in (("threequarter", -35, 3.3, 55, 760, 940),
                                    ("side", -90, 3.3, 55, 760, 940),
                                    ("gameplay", 25, 5.2, 28.3, 1000, 1000)):
    cd.lens = lens
    sc.render.resolution_x = rx; sc.render.resolution_y = ry
    a, e = math.radians(az), math.radians(11)
    cam.location = focus + Vector((math.sin(a) * math.cos(e) * dist,
                                   -math.cos(a) * math.cos(e) * dist, math.sin(e) * dist))
    cam.rotation_euler = (focus - cam.location).to_track_quat("-Z", "Y").to_euler()
    d = os.path.join(OUT, "frames_" + tag); os.makedirs(d, exist_ok=True)
    sc.render.filepath = os.path.join(d, "f_")
    bpy.ops.render.render(animation=True)
    print("RENDERED", tag)
print("RENDER_DONE")
