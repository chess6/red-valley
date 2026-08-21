"""Render the water_can clip: front / true-side / three-quarter / gameplay.

The saved blend still contains the attached can (the deform-only purge happens
only in the export path), so the renders show the full interaction.

  blender --background water_can.blend --python render_water.py -- <outdir>
"""
import math, os, sys
import bpy
from mathutils import Vector

OUT = sys.argv[sys.argv.index("--") + 1:][0]
os.makedirs(OUT, exist_ok=True)
rig = bpy.data.objects["rv_rigify"]
bpy.context.view_layer.objects.active = rig
if rig.mode != "OBJECT": bpy.ops.object.mode_set(mode="OBJECT")
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.view_settings.view_transform = "Standard"
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
    fl = bpy.context.object; fl.data.energy = 260; fl.data.size = 5
    fl.rotation_euler = (math.radians(75), 0, math.radians(-45))
# ground + the 0.22 m soil bed in front, per the plot-anchor contract
bpy.ops.mesh.primitive_plane_add(size=12, location=(0, 0, 0))
g = bpy.context.object
gm = bpy.data.materials.new("gnd"); gm.use_nodes = True
gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (.30, .32, .30, 1)
g.data.materials.append(gm)
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -0.85, 0.11))
bed = bpy.context.object; bed.scale = (1.6, 1.0, 0.22)
bm = bpy.data.materials.new("soil"); bm.use_nodes = True
bm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (.18, .11, .07, 1)
bed.data.materials.append(bm)

cd = bpy.data.cameras.new("C"); cam = bpy.data.objects.new("C", cd)
sc.collection.objects.link(cam); sc.camera = cam
sc.render.image_settings.file_format = "PNG"
VIEWS = [("front", 0, 3.4, 55, 720, 900),
         ("side", -90, 3.4, 55, 720, 900),
         ("threequarter", -35, 3.4, 55, 720, 900),
         ("gameplay", 25, 5.2, 28.3, 1000, 1000)]
focus = Vector((0, 0, 1.0))
for tag, az, dist, lens, rx, ry in VIEWS:
    cd.lens = lens
    sc.render.resolution_x = rx; sc.render.resolution_y = ry
    a, e = math.radians(az), math.radians(12)
    cam.location = focus + Vector((math.sin(a) * math.cos(e) * dist,
                                   -math.cos(a) * math.cos(e) * dist, math.sin(e) * dist))
    cam.rotation_euler = (focus - cam.location).to_track_quat("-Z", "Y").to_euler()
    d = os.path.join(OUT, "frames_" + tag); os.makedirs(d, exist_ok=True)
    sc.render.filepath = os.path.join(d, "f_")
    bpy.ops.render.render(animation=True)
    print("RENDERED_SEQ", tag)
print("WATER_RENDER_DONE")
