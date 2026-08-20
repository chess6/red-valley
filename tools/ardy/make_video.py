"""Side-by-side comparison render: raw ARDY skeleton vs retargeted character.

Left  = ARDY's raw joint output (scaled to rig height so the comparison is fair)
Right = the retargeted Rodin character with the watering-can proxy on its socket
Both  = floor grid, soil target at plot height, foot-contact indicators

Renders a front and a three-quarter camera per frame; the caller composites.

  blender --background --python make_video.py -- <rig.glb> <can.glb> <clip.npz> <map.json> <outdir>
"""
import json, math, os, sys
import bpy, mathutils
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:]
RIG_GLB, CAN_GLB, NPZ, MAP_JSON, OUT = argv[:5]
# The can is attached only for the bend/reach clip: per the diagnostic plan the
# prop goes on AFTER the motion exists, so locomotion is judged bare-handed.
ATTACH_CAN = (len(argv) < 6) or (argv[5].lower() not in ("0", "false", "no"))
os.makedirs(OUT, exist_ok=True)

d = np.load(NPZ, allow_pickle=True)
J = d["posed_joints"]; fc = d["foot_contacts"]; fps = int(d["fps"]); F = len(J)
MAP = json.load(open(MAP_JSON))
NAMES = MAP["source_joint_order"]
SI = {n: i for i, n in enumerate(NAMES)}
PARENT = {}
import re
# parent list, same order as the source definition
PAIRS = [("Hips",None),("Spine","Hips"),("Spine1","Spine"),("Spine2","Spine1"),("Spine3","Spine2"),
         ("Neck","Spine3"),("Head","Neck"),("RightShoulder","Spine3"),("RightArm","RightShoulder"),
         ("RightForeArm","RightArm"),("RightHand","RightForeArm"),("RightHandEnd","RightHand"),
         ("RightHandThumb1","RightHand"),("LeftShoulder","Spine3"),("LeftArm","LeftShoulder"),
         ("LeftForeArm","LeftArm"),("LeftHand","LeftForeArm"),("LeftHandEnd","LeftHand"),
         ("LeftHandThumb1","LeftHand"),("RightUpLeg","Hips"),("RightLeg","RightUpLeg"),
         ("RightFoot","RightLeg"),("RightToeBase","RightFoot"),("LeftUpLeg","Hips"),
         ("LeftLeg","LeftUpLeg"),("LeftFoot","LeftLeg"),("LeftToeBase","LeftFoot")]
for c, p in PAIRS: PARENT[c] = p

RIG_H = 1.9005
scale = RIG_H / float(J[:, SI["Head"], 1].max() - J[:, SI["RightToeBase"], 1].min())
def cv(v):                       # ARDY Y-up -> Blender Z-up, scaled
    return mathutils.Vector((float(v[0]) * scale, -float(v[2]) * scale, float(v[1]) * scale))

SKEL_X, CHAR_X = -1.15, 1.15

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.fps = fps
sc.frame_start, sc.frame_end = 1, F

def mat(name, rgb, rough=0.6, emit=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    if emit:
        b.inputs["Emission Color"].default_value = (*rgb, 1)
        b.inputs["Emission Strength"].default_value = emit
    return m

M_BONE = mat("bone", (0.35, 0.75, 1.0), 0.4, 1.2)
M_JOINT = mat("joint", (1.0, 0.85, 0.25), 0.4, 1.5)
M_ON = mat("contact_on", (0.15, 1.0, 0.25), 0.5, 2.5)
M_OFF = mat("contact_off", (0.9, 0.15, 0.15), 0.5, 0.6)
M_SOIL = mat("soil", (0.30, 0.19, 0.11), 0.95)
M_GRID = mat("grid", (0.32, 0.33, 0.36), 0.9)

# floor grid
bpy.ops.mesh.primitive_grid_add(size=14, x_subdivisions=15, y_subdivisions=15, location=(0, 0, 0))
grid = bpy.context.active_object; grid.name = "floor_grid"
w = grid.modifiers.new("wire", "WIREFRAME"); w.thickness = 0.012
grid.data.materials.append(M_GRID)
bpy.ops.mesh.primitive_plane_add(size=14, location=(0, 0, -0.002))
bpy.context.active_object.data.materials.append(mat("ground", (0.12, 0.12, 0.13), 1.0))

# soil target in front of each subject (plot bed: 1.8 x 1.8 x 0.22)
for x in (SKEL_X, CHAR_X):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x, -0.95, 0.11))
    s = bpy.context.active_object; s.scale = (0.9, 0.9, 0.11); s.name = "soil"
    s.data.materials.append(M_SOIL)

# --- raw ARDY skeleton: joints + bones, keyframed
joints = {}
for n in NAMES:
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.032, segments=10, ring_count=6)
    o = bpy.context.active_object; o.name = "j_" + n
    o.data.materials.append(M_JOINT); joints[n] = o
bones = {}
for c, p in PAIRS:
    if p is None: continue
    bpy.ops.mesh.primitive_cylinder_add(radius=0.016, depth=1.0, vertices=8)
    o = bpy.context.active_object; o.name = "b_" + c
    o.data.materials.append(M_BONE); bones[c] = o
contacts = {}
for k, jn in enumerate(["LeftFoot", "LeftToeBase", "RightFoot", "RightToeBase"]):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.055, segments=12, ring_count=8)
    o = bpy.context.active_object; o.name = "c_" + jn
    o.data.materials.append(M_ON); contacts[k] = (o, jn)

for f in range(F):
    off = mathutils.Vector((SKEL_X, 0, 0))
    P = {n: cv(J[f, SI[n]]) + off for n in NAMES}
    for n, o in joints.items():
        o.location = P[n]; o.keyframe_insert("location", frame=f + 1)
    for c, p in PAIRS:
        if p is None: continue
        a, b = P[p], P[c]
        v = b - a; L = max(v.length, 1e-5)
        o = bones[c]
        o.location = (a + b) / 2
        o.rotation_mode = "QUATERNION"
        o.rotation_quaternion = mathutils.Vector((0, 0, 1)).rotation_difference(v.normalized())
        o.scale = (1, 1, L)
        o.keyframe_insert("location", frame=f + 1)
        o.keyframe_insert("rotation_quaternion", frame=f + 1)
        o.keyframe_insert("scale", frame=f + 1)
    for k, (o, jn) in contacts.items():
        o.location = P[jn] + mathutils.Vector((0, 0, -0.03))
        o.keyframe_insert("location", frame=f + 1)
        o.scale = (1, 1, 1) if fc[f, k] else (0.55, 0.55, 0.55)
        o.keyframe_insert("scale", frame=f + 1)

# --- retargeted character + can
before = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=RIG_GLB)
rig = [o for o in bpy.data.objects if o not in before and o.type == "ARMATURE"][0]
rig.location.x = CHAR_X
for o in bpy.data.objects:
    if o.type == "MESH" and o.parent == rig: pass
can = None
if ATTACH_CAN:
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=CAN_GLB)
    can = [o for o in bpy.data.objects if o not in before and o.type == "MESH"][0]
if can is not None:
    OFF = {k: mathutils.Vector(v) for k, v in
           json.load(open(CAN_GLB.replace(".glb", ".json")))["markers"].items()}
    can.parent = rig; can.parent_type = "BONE"; can.parent_bone = "prop_socket.R"
    BFP = mathutils.Matrix.Rotation(math.radians(90), 4, "X")
    for f in range(1, F + 1):
        sc.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        sock = rig.matrix_world @ rig.evaluated_get(dg).pose.bones["prop_socket.R"].matrix
        can.matrix_world = sock @ BFP
        can.keyframe_insert("location", frame=f)
        can.rotation_mode = "QUATERNION"
        can.keyframe_insert("rotation_quaternion", frame=f)

# --- lights + cameras
key = bpy.data.objects.new("key", bpy.data.lights.new("key", "AREA"))
key.data.energy = 2200; key.data.size = 9
key.location = (3.5, -5.0, 4.5); key.rotation_euler = (math.radians(52), 0, math.radians(35))
bpy.context.collection.objects.link(key)
fill = bpy.data.objects.new("fill", bpy.data.lights.new("fill", "AREA"))
fill.data.energy = 600; fill.data.size = 9
fill.location = (-4.0, -3.0, 3.0); fill.rotation_euler = (math.radians(60), 0, math.radians(-40))
bpy.context.collection.objects.link(fill)
world = bpy.data.worlds.new("W"); world.use_nodes = True
world.node_tree.nodes["Background"].inputs[1].default_value = 0.35
sc.world = world
sc.render.engine = next(e for e in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES")
                        if e in sc.render.bl_rna.properties["engine"].enum_items.keys())
sc.render.resolution_x, sc.render.resolution_y = 1280, 620
try: sc.view_settings.view_transform = "Standard"
except TypeError: pass

# Aim every camera at the same point between the two subjects via a Track To
# constraint -- hand-set euler angles cropped the heads.
look = bpy.data.objects.new("look_at", None)
look.location = (0, 0, 0.95)
bpy.context.collection.objects.link(look)

def add_cam(name, loc, lens):
    cd = bpy.data.cameras.new(name); cd.lens = lens
    c = bpy.data.objects.new(name, cd); c.location = loc
    bpy.context.collection.objects.link(c)
    t = c.constraints.new("TRACK_TO"); t.target = look
    t.track_axis = "TRACK_NEGATIVE_Z"; t.up_axis = "UP_Y"
    return c

CAMS = {
  "front": add_cam("front", (0, -7.2, 1.05), 40),
  "threequarter": add_cam("tq", (5.6, -5.6, 2.1), 40),
}
for tag, cam in CAMS.items():
    sc.camera = cam
    for f in range(1, F + 1):
        sc.frame_set(f)
        sc.render.filepath = os.path.join(OUT, f"{tag}_{f:03d}.png")
        bpy.ops.render.render(write_still=True)
    print("rendered", tag, flush=True)
print("VIDEO_FRAMES_DONE")
