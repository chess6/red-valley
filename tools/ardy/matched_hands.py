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

# BOTH hands curl at +X. An earlier test concluded the signs were mirrored, but
# that measured the left hand against the RIGHT hand's palm normal; measured
# against each hand's own thumb-derived normal, +88 curls both (+39.6 mm R,
# +36.9 mm L) and -88 hyperextends both.
#
# A fist is not one rotation: the knuckle, middle and end joints close by
# different amounts. Driving only the master gives a uniform arc that reads as a
# claw, so the three joints are driven separately.
FIST = {"01": 50, "02": 68, "03": 42}
CURL = {"01": 32, "02": 40, "03": 22}
def set_digit(f, s, table):
    for j, ang in table.items():
        rot("%s.%s.%s" % (f, j, s), x=ang)

POSES = {
    "relaxed": lambda s: None,
    "curl":    lambda s: [set_digit(f, s, CURL) for f in FING],
    # X (curl) does not mirror, but Z (the thumb's sweep across the palm) does --
    # using one Z on both hands left the thumbs 4.5 mm and 8.5 mm out of step.
    "fist":    lambda s: ([set_digit(f, s, FIST) for f in FING]
                          + [set_digit("thumb", s, {"01": 34, "02": 40, "03": 28}),
                             rot("thumb.01.%s" % s, x=34,
                                 z=-22 if s == "R" else 22)]),
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
