"""Render the three constraint poses from front / true-side / three-quarter.

Review scaffolding only -- the ground and soil bed exist so the spout height can
be judged by eye. They are NOT assets and are never exported.

  blender --background pose_reference.blend --python render_poses.py -- <outdir>
"""
import math, os, sys
import bpy
from mathutils import Vector

OUT = sys.argv[sys.argv.index("--") + 1]
os.makedirs(OUT, exist_ok=True)
SOIL = 0.22

sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"   # 5.1 renamed EEVEE_NEXT back to this
sc.render.resolution_x, sc.render.resolution_y = 900, 1200
sc.render.film_transparent = False
# Without ray-traced shadows there is no contact shadow under the boots and a
# planted foot reads as floating -- the soles are measured at z = 0.0000.
try:
    sc.eevee.use_raytracing = True
    sc.eevee.use_shadows = True
    sc.eevee.use_shadow_jitter_viewport = True
except AttributeError:
    pass
sc.view_settings.view_transform = "Standard"   # AgX washes these out
sc.render.image_settings.file_format = "PNG"

bpy.ops.mesh.primitive_plane_add(size=12, location=(0, 0, 0))
bpy.context.object.name = "REF_ground"
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -0.75, SOIL / 2))
bed = bpy.context.object; bed.name = "REF_soil_bed"
bed.scale = (1.6, 1.0, SOIL)
m = bpy.data.materials.new("REF_soil"); m.use_nodes = True
m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.18, 0.11, 0.07, 1)
bed.data.materials.append(m)

bpy.ops.object.light_add(type="SUN", location=(4, -6, 8))
key = bpy.context.object; key.data.energy = 4.0
key.rotation_euler = (math.radians(38), 0, math.radians(28))
key.data.angle = math.radians(2.0)
bpy.ops.object.light_add(type="AREA", location=(-4, -5, 3))
fill = bpy.context.object; fill.data.energy = 260; fill.data.size = 6
fill.rotation_euler = (math.radians(75), 0, math.radians(-40))
sc.world = sc.world or bpy.data.worlds.new("W")
sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs[0].default_value = (0.30, 0.34, 0.40, 1)

cam_d = bpy.data.cameras.new("C"); cam = bpy.data.objects.new("C", cam_d)
sc.collection.objects.link(cam); sc.camera = cam
cam_d.lens = 60
FOCUS = Vector((0.0, -0.30, 0.95))

def look(az_deg, dist=4.0, height=1.05):
    """az 0 = in front of the character (it faces -Y)."""
    a = math.radians(az_deg)
    cam.location = FOCUS + Vector((math.sin(a) * dist, -math.cos(a) * dist,
                                   height - FOCUS.z + 0.15))
    d = (FOCUS - cam.location)
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()

# The can is in the RIGHT hand, so a side camera at +90 puts the body between
# the lens and the prop. Shoot the true side from her right.
VIEWS = [("front", 0.0), ("side", -90.0), ("threequarter", 38.0)]
POSES = ["01_start", "02_pour", "03_return"]
for i, pose in enumerate(POSES):
    sc.frame_set(i + 1)
    for vname, az in VIEWS:
        look(az)
        sc.render.filepath = os.path.join(OUT, "%s_%s.png" % (pose, vname))
        bpy.ops.render.render(write_still=True)
        print("RENDERED", sc.render.filepath)
print("RENDER_POSES_DONE")
