"""Deformation validation for the bound Rigify rig. No animation, no export.

  blender --background <rv_bound.blend> --python deform_tests.py -- <outdir>
"""
import math, os, sys
import bpy
from mathutils import Vector, Matrix

OUT = sys.argv[sys.argv.index("--") + 1:][0]
os.makedirs(OUT, exist_ok=True)
rig = bpy.data.objects["rv_rigify"]
mesh = max([o for o in bpy.data.objects if o.type == "MESH"],
           key=lambda o: len(o.data.vertices))
PB = rig.pose.bones

# FK, so the *_fk controls actually drive the limbs
for n in ("upper_arm_parent.R", "upper_arm_parent.L", "thigh_parent.R", "thigh_parent.L"):
    if n in PB:
        try: PB[n]["IK_FK"] = 1.0
        except Exception: pass

sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.view_settings.view_transform = "Standard"
sc.render.image_settings.file_format = "PNG"
try:
    sc.eevee.use_raytracing = True; sc.eevee.use_shadows = True
except AttributeError: pass
sc.world = sc.world or bpy.data.worlds.new("W"); sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs[0].default_value = (.16, .17, .20, 1)
bpy.ops.object.light_add(type="SUN", location=(3, -4, 5))
k = bpy.context.object; k.data.energy = 3.2
k.rotation_euler = (math.radians(46), 0, math.radians(30))
bpy.ops.object.light_add(type="AREA", location=(-3, -3, 2))
fl = bpy.context.object; fl.data.energy = 300; fl.data.size = 5
fl.rotation_euler = (math.radians(75), 0, math.radians(-45))
cd = bpy.data.cameras.new("C"); cam = bpy.data.objects.new("C", cd)
sc.collection.objects.link(cam); sc.camera = cam

def reset():
    for b in PB:
        b.rotation_mode = "XYZ"
        b.rotation_euler = (0, 0, 0)
        b.location = (0, 0, 0)
    bpy.context.view_layer.update()

def rot(name, x=0, y=0, z=0):
    if name not in PB: return False
    b = PB[name]; b.rotation_mode = "XYZ"
    b.rotation_euler = (math.radians(x), math.radians(y), math.radians(z))
    return True

def shoot(tag, focus, dist, az, el=10, lens=70, res=900):
    cd.type = "PERSP"; cd.lens = lens
    sc.render.resolution_x = sc.render.resolution_y = res
    a, e = math.radians(az), math.radians(el)
    cam.location = Vector(focus) + Vector((math.sin(a) * math.cos(e) * dist,
                                           -math.cos(a) * math.cos(e) * dist,
                                           math.sin(e) * dist))
    cam.rotation_euler = (Vector(focus) - cam.location).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = os.path.join(OUT, tag + ".png")
    bpy.ops.render.render(write_still=True)
    print("RENDERED", sc.render.filepath)

def handfocus():
    bpy.context.view_layer.update()
    return (rig.matrix_world @ PB["DEF-hand.R"].matrix).to_translation()

FING = ["f_index", "f_middle", "f_ring", "f_pinky"]
HAND_TESTS = {
    "hand_rest":       lambda: None,
    "hand_curl":       lambda: [rot("%s.01_master.R" % f, x=-55) for f in FING],
    "hand_fist":       lambda: ([rot("%s.01_master.R" % f, x=-85) for f in FING]
                                + [rot("thumb.01_master.R", x=-40)]),
    "hand_thumb_opp":  lambda: rot("thumb.01_master.R", x=-55, z=-25),
    "hand_wrist_flex": lambda: rot("hand_fk.R", x=-45),
    "hand_wrist_ext":  lambda: rot("hand_fk.R", x=45),
}
for tag, fn in HAND_TESTS.items():
    reset(); fn(); bpy.context.view_layer.update()
    f = handfocus()
    shoot(tag + "_a", f, 0.30, -60, el=14, lens=75)
    shoot(tag + "_b", f, 0.30, 110, el=14, lens=75)

BODY = Vector((0, 0, 0.95))
BODY_TESTS = {
    "body_rest":     lambda: None,
    "body_elbow":    lambda: rot("forearm_fk.R", x=-95),
    "body_shoulder": lambda: (rot("upper_arm_fk.R", z=-75), rot("shoulder.R", z=-15)),
    "body_knee":     lambda: (rot("thigh_fk.L", x=-70), rot("shin_fk.L", x=95)),
    "body_crouch":   lambda: ([rot("thigh_fk.%s" % s, x=-55) for s in ("L", "R")]
                              + [rot("shin_fk.%s" % s, x=85) for s in ("L", "R")]
                              + [rot("torso", x=18)]),
}
for tag, fn in BODY_TESTS.items():
    reset(); fn(); bpy.context.view_layer.update()
    shoot(tag + "_front", BODY, 3.6, 0, el=6, lens=60, res=800)
    shoot(tag + "_side", BODY, 3.6, -90, el=6, lens=60, res=800)
print("DEFORM_DONE")
