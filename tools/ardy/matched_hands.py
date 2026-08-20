"""Matched close-ups of both hands in relaxed, curl and fist poses.

  blender --background <rv_bound.blend> --python matched_hands.py -- <outdir>
"""
import math, os, sys
import bpy
from mathutils import Vector

OUT = sys.argv[sys.argv.index("--") + 1:][0]
os.makedirs(OUT, exist_ok=True)
rig = bpy.data.objects["rv_rigify"]
PB = rig.pose.bones
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.view_settings.view_transform = "Standard"
sc.render.resolution_x = sc.render.resolution_y = 900
try:
    sc.eevee.use_raytracing = True; sc.eevee.use_shadows = True
except AttributeError: pass
sc.world = sc.world or bpy.data.worlds.new("W"); sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs[0].default_value = (.17, .18, .21, 1)
bpy.ops.object.light_add(type="SUN", location=(3, -4, 5))
k = bpy.context.object; k.data.energy = 3.4
k.rotation_euler = (math.radians(45), 0, math.radians(28))
bpy.ops.object.light_add(type="AREA", location=(-3, -3, 2))
fl = bpy.context.object; fl.data.energy = 320; fl.data.size = 5
fl.rotation_euler = (math.radians(75), 0, math.radians(-45))
cd = bpy.data.cameras.new("C"); cam = bpy.data.objects.new("C", cd)
sc.collection.objects.link(cam); sc.camera = cam; cd.lens = 78

FING = ["f_index", "f_middle", "f_ring", "f_pinky"]
def reset():
    for b in PB:
        b.rotation_mode = "XYZ"; b.rotation_euler = (0, 0, 0); b.location = (0, 0, 0)
    bpy.context.view_layer.update()
def rot(n, **kw):
    if n in PB:
        PB[n].rotation_mode = "XYZ"
        PB[n].rotation_euler = (math.radians(kw.get("x", 0)),
                                math.radians(kw.get("y", 0)),
                                math.radians(kw.get("z", 0)))

# Rigify mirrors the finger controls, so a curl is +X on the right and -X on the
# left. Using one sign for both hands hyperextends one of them -- every earlier
# fist and curl render of the RIGHT hand was showing it bent backwards.
SGN = {"R": +1.0, "L": -1.0}
POSES = {
    "relaxed": lambda s: None,
    "curl":    lambda s: [rot("%s.01_master.%s" % (f, s), x=55 * SGN[s]) for f in FING],
    "fist":    lambda s: ([rot("%s.01_master.%s" % (f, s), x=88 * SGN[s]) for f in FING]
                          + [rot("thumb.01_master.%s" % s, x=45 * SGN[s], z=-20 * SGN[s])]),
}
for tag, fn in POSES.items():
    for s in ("R", "L"):
        reset(); fn(s); bpy.context.view_layer.update()
        f = (rig.matrix_world @ PB["DEF-hand." + s].matrix).to_translation()
        # mirrored azimuth so the two hands are shown from equivalent angles
        az = -62 if s == "R" else 62
        a, e = math.radians(az), math.radians(14)
        cam.location = f + Vector((math.sin(a) * math.cos(e) * 0.30,
                                   -math.cos(a) * math.cos(e) * 0.30,
                                   math.sin(e) * 0.30))
        cam.rotation_euler = (f - cam.location).to_track_quat("-Z", "Y").to_euler()
        sc.render.filepath = os.path.join(OUT, "%s_%s.png" % (tag, s))
        bpy.ops.render.render(write_still=True)
        print("RENDERED", sc.render.filepath)
print("MATCHED_DONE")
