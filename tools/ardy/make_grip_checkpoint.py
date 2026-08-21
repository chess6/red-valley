"""Build a Blender file for the human to finish the grip by hand.

Adds a real prop_socket.R bone, fixes the can to it, isolates the four finger
controls that matter, and sets up the three review cameras. The automated pose
is kept as the starting point.

  blender --background <grip_pose.blend> --python make_grip_checkpoint.py -- <out.blend>
"""
import json, math, os, sys
import bpy
from mathutils import Vector, Matrix

OUT = sys.argv[sys.argv.index("--") + 1:][0]
rig = bpy.data.objects["rv_rigify"]
can = [o for o in bpy.data.objects if o.type == "MESH" and "can" in o.name.lower()][0]
mesh = max([o for o in bpy.data.objects if o.type == "MESH" and o is not can],
           key=lambda o: len(o.data.vertices))
S = "R"

# --- a real prop_socket.R, where the can already sits ------------------------
bpy.context.view_layer.objects.active = rig
bpy.context.view_layer.update()
sock_world = can.matrix_world @ Matrix(
    json.load(open("art/animation/ardy_pilot/proxy/watering_can_proxy.json"))["grip_anchor_basis_rows"])
bpy.ops.object.mode_set(mode="EDIT")
EB = rig.data.edit_bones
if "prop_socket.R" in EB: EB.remove(EB["prop_socket.R"])
sb = EB.new("prop_socket.R")
inv = rig.matrix_world.inverted()
sb.head = inv @ sock_world.to_translation()
sb.tail = inv @ (sock_world.to_translation() + sock_world.to_3x3() @ Vector((0, 0.05, 0)))
sb.parent = EB["DEF-hand.%s" % S]
sb.use_connect = False
sb.use_deform = False
bpy.ops.object.mode_set(mode="OBJECT")
can.parent = rig
can.parent_type = "BONE"
can.parent_bone = "prop_socket.R"
bpy.context.view_layer.update()
can.matrix_world = sock_world @ Matrix(
    json.load(open("art/animation/ardy_pilot/proxy/watering_can_proxy.json"))["grip_anchor_basis_rows"]).inverted()
print("prop_socket.R added; can rigidly parented to it")

# --- isolate only the controls the human should touch ------------------------
EDIT = []
for d in ("thumb", "f_index", "f_middle", "f_ring"):
    for j in ("01", "02", "03"):
        n = "%s.%s.%s" % (d, j, S)
        if n in rig.pose.bones: EDIT.append(n)
# Euler, not quaternion: the N-panel then shows three rotation fields in
# degrees that can be typed into, instead of four quaternion components that
# nobody can reason about by hand.
for n in EDIT:
    rig.pose.bones[n].rotation_mode = "XYZ"
coll = rig.data.collections if hasattr(rig.data, "collections") else None
for b in rig.data.bones:
    keep = b.name in EDIT
    b.hide = not keep
    b.hide_select = not keep
print("selectable controls: %d (%s)" % (len(EDIT), ", ".join(EDIT[:4]) + ", ..."))

# --- three review cameras ----------------------------------------------------
bpy.context.view_layer.update()
hand = (rig.matrix_world @ rig.pose.bones["DEF-hand.%s" % S].matrix).to_translation()
for az, el, tag in ((-70, 12, "PALM"), (20, 12, "SIDE"), (-35, 16, "THREEQUARTER")):
    cd = bpy.data.cameras.new("CAM_" + tag); cd.lens = 80
    c = bpy.data.objects.new("CAM_" + tag, cd)
    bpy.context.collection.objects.link(c)
    a, e = math.radians(az), math.radians(el)
    c.location = hand + Vector((math.sin(a) * math.cos(e) * 0.32,
                                -math.cos(a) * math.cos(e) * 0.32, math.sin(e) * 0.32))
    c.rotation_euler = (hand - c.location).to_track_quat("-Z", "Y").to_euler()
bpy.context.scene.camera = bpy.data.objects["CAM_PALM"]
print("cameras: CAM_PALM, CAM_SIDE, CAM_THREEQUARTER")

# Leave the file with the ARMATURE active and already in Pose Mode. Blender
# stores the mode, and Pose Mode is not even offered in the dropdown unless an
# armature is the active object -- creating the cameras last made a camera
# active, so the option was missing entirely.
for o in bpy.data.objects:
    try: o.select_set(False)
    except Exception: pass
rig.select_set(True)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode="POSE")
try:
    rig.data.bones.active = rig.data.bones[EDIT[3]]   # f_index.01.R
except Exception:
    pass
print("saved in mode: %s, active object: %s" % (rig.mode, bpy.context.view_layer.objects.active.name))

bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("CHECKPOINT_DONE", OUT)
