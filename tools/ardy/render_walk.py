"""Render the retargeted walk from front, true side and three-quarter.

  blender --background <walk_rigify.blend> --python render_walk.py -- <outdir>
"""
import math, os, sys
import bpy
from mathutils import Vector

OUT = sys.argv[sys.argv.index("--") + 1:][0]
os.makedirs(OUT, exist_ok=True)
rig = bpy.data.objects["rv_rigify"]
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.view_settings.view_transform = "Standard"
sc.render.resolution_x = 720; sc.render.resolution_y = 900
sc.render.fps = 20; sc.render.fps_base = 1.0
try:
    sc.eevee.use_raytracing = True; sc.eevee.use_shadows = True
except AttributeError: pass
sc.world = sc.world or bpy.data.worlds.new("W"); sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs[0].default_value = (.30, .34, .40, 1)
if not any(o.type == "LIGHT" for o in bpy.data.objects):
    bpy.ops.object.light_add(type="SUN", location=(3, -4, 5))
    k = bpy.context.object; k.data.energy = 3.0
    k.rotation_euler = (math.radians(46), 0, math.radians(28))
    bpy.ops.object.light_add(type="AREA", location=(-3, -3, 2))
    f = bpy.context.object; f.data.energy = 260; f.data.size = 5
    f.rotation_euler = (math.radians(75), 0, math.radians(-45))
bpy.ops.mesh.primitive_plane_add(size=8, location=(0, 0, 0))
g = bpy.context.object
gm = bpy.data.materials.new("ground"); gm.use_nodes = True
gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (.28, .30, .28, 1)
g.data.materials.append(gm)
cd = bpy.data.cameras.new("C"); cam = bpy.data.objects.new("C", cd)
sc.collection.objects.link(cam); sc.camera = cam; cd.lens = 55
focus = Vector((0, 0, 0.95))

# This Blender build has no FFMPEG writer, so render PNG frames and let the
# system ffmpeg encode them at the clip's native rate.
sc.render.image_settings.file_format = "PNG"
for az, tag in ((0, "front"), (-90, "side"), (-35, "threequarter")):
    a = math.radians(az)
    cam.location = focus + Vector((math.sin(a) * 3.4, -math.cos(a) * 3.4, 0.35))
    cam.rotation_euler = (focus - cam.location).to_track_quat("-Z", "Y").to_euler()
    d = os.path.join(OUT, "frames_" + tag)
    os.makedirs(d, exist_ok=True)
    sc.render.filepath = os.path.join(d, "f_")
    bpy.ops.render.render(animation=True)
    print("RENDERED_SEQ", d)
print("WALK_RENDER_DONE")
