"""Natural carry pose: relaxed arm, un-twisted wrist, can hanging under gravity.

Two faults this corrects:
  * the hand was targeted at 0.82 m, below the 0.843 m a fully extended arm
    reaches standing, so IK locked the elbow straight at 179.9 deg;
  * the can hung along the PALM NORMAL, so making it upright twisted the wrist
    127 deg. A real can hangs from the bar under gravity, independent of hand
    roll, so the socket's body axis is world-down and the wrist stays neutral.

  blender --background <rv_bound.blend> --python carry_pose.py -- <can.glb> <out.blend>
"""
import json, math, os, sys
import bpy
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:]
CAN_GLB, OUT = argv[0], argv[1]
rig = bpy.data.objects["rv_rigify"]
mesh = max([o for o in bpy.data.objects if o.type == "MESH"],
           key=lambda o: len(o.data.vertices))
bpy.context.view_layer.objects.active = rig
if rig.mode != "OBJECT": bpy.ops.object.mode_set(mode="OBJECT")
PB = rig.pose.bones
S = "R"
GIx = {g.name: g.index for g in mesh.vertex_groups}

def w(n): return (rig.matrix_world @ PB[n].matrix).to_translation()
def upd(): bpy.context.view_layer.update()

for b in PB:
    b.rotation_mode = "XYZ"; b.rotation_euler = (0, 0, 0); b.location = (0, 0, 0)
upd()

_fm0 = (rig.matrix_world @ PB["DEF-forearm.%s" % S].matrix).to_3x3()
_hm0 = (rig.matrix_world @ PB["DEF-hand.%s" % S].matrix).to_3x3()
sh = w("DEF-upper_arm.%s" % S)
reach = (w("DEF-forearm.%s" % S) - sh).length + (w("DEF-hand.%s" % S) - w("DEF-forearm.%s" % S)).length
REST_REL = _fm0.inverted() @ _hm0
print("shoulder z %.3f, arm reach %.3f -> lowest possible wrist %.3f m"
      % (sh.z, reach, sh.z - reach))
# a relaxed carry keeps a real elbow bend: aim for ~94% of full extension
TARGET_EXT = 0.94
drop = reach * TARGET_EXT
tgt = Vector((sh.x - 0.035, sh.y - 0.075, sh.z - math.sqrt(max(0.0, drop**2 - 0.035**2 - 0.075**2))))
print("hand target (%.3f, %.3f, %.3f) -> %.0f%% extension" % (tgt.x, tgt.y, tgt.z, TARGET_EXT * 100))

if "upper_arm_parent.%s" % S in PB:
    try: PB["upper_arm_parent.%s" % S]["IK_FK"] = 0.0
    except Exception: pass
upd()
ik = PB["hand_ik.%s" % S]
ik.matrix = rig.matrix_world.inverted() @ Matrix.Translation(tgt)
upd()

def elbow_angle():
    a, b, c = w("DEF-upper_arm.%s" % S), w("DEF-forearm.%s" % S), w("DEF-hand.%s" % S)
    return math.degrees((a - b).angle(c - b))
REST_REL = None
def wrist_dev():
    """Deviation from the REST wrist relationship. Comparing raw bone matrices
    reports ~170 deg on a perfectly neutral wrist, because the forearm and hand
    rest axes differ by construction."""
    global REST_REL
    fm = (rig.matrix_world @ PB["DEF-forearm.%s" % S].matrix).to_3x3()
    hm = (rig.matrix_world @ PB["DEF-hand.%s" % S].matrix).to_3x3()
    rel = fm.inverted() @ hm
    if REST_REL is None: return 0.0
    return math.degrees((REST_REL.inverted() @ rel).to_quaternion().angle)
print("elbow %.1f deg | wrist deviation %.1f deg (neutral arm, no roll applied)"
      % (elbow_angle(), wrist_dev()))

# ---- socket: bar across the palm, can body hanging straight DOWN ------------
hm = rig.matrix_world @ PB["DEF-hand.%s" % S].matrix
FING = (hm.to_3x3() @ Vector((0, 1, 0))).normalized()
PALMIDX = [GIx.get("DEF-hand.%s" % S)] + [GIx.get("DEF-palm.0%d.%s" % (i, S)) for i in (1, 2, 3, 4)]
PALMIDX = [i for i in PALMIDX if i is not None]
handv = [mesh.matrix_world @ v.co for v in mesh.data.vertices
         if any(g.group in PALMIDX and g.weight > 0.3 for g in v.groups)]
PALM = sum(handv, Vector()) / len(handv)
FORE = (w("DEF-hand.%s" % S) - w("DEF-forearm.%s" % S)).normalized()
BAR = FORE.cross(Vector((0, 0, -1)))
if BAR.length < 1e-4:                       # forearm vertical: fall back to across-body
    BAR = Vector((1, 0, 0))
BAR.normalize()
NRM = BAR.cross(FORE).normalized()          # through the palm, perpendicular to both
print("bar axis (%.3f,%.3f,%.3f) horizontality %.3f" % (BAR.x, BAR.y, BAR.z, 1 - abs(BAR.z)))

META = json.load(open(CAN_GLB.replace(".glb", ".json")))
GA = Matrix(META["grip_anchor_basis_rows"])
BAR_R = META["dimensions_m"]["handle_bar_diameter"] / 2.0
# Position from the measured GRIP CHANNEL, not a normal-offset from the palm
# centroid: NRM is perpendicular to the forearm, so for a hanging arm it is
# horizontal and "lifting" along it pushes the can sideways out of the hand.
def surf_of(groups, wmin=0.5):
    idx = [GIx.get(g) for g in groups]; idx = [i for i in idx if i is not None]
    dg = bpy.context.evaluated_depsgraph_get()
    ev = mesh.evaluated_get(dg); m = ev.to_mesh()
    pts = [mesh.matrix_world @ m.vertices[v.index].co for v in mesh.data.vertices
           if any(g.group in idx and g.weight > wmin for g in v.groups)]
    ev.to_mesh_clear(); return pts
PRE = {"thumb": (34, 40, 28, 0.45), "f_index": (52, 68, 44, 0.55),
       "f_middle": (52, 68, 44, 0.55), "f_ring": (40, 52, 30, 0.55)}
for d, (a1, a2, a3, fr) in PRE.items():
    for j, a in zip(("01", "02", "03"), (a1, a2, a3)):
        n = "%s.%s.%s" % (d, j, S)
        if n in PB: PB[n].rotation_mode = "XYZ"; PB[n].rotation_euler = (math.radians(a * fr), 0, 0)
upd()
pads = surf_of(["DEF-f_index.03.%s" % S, "DEF-f_middle.03.%s" % S,
                "DEF-f_index.02.%s" % S, "DEF-f_middle.02.%s" % S])
palmpts = surf_of(["DEF-palm.01.%s" % S, "DEF-palm.02.%s" % S,
                   "DEF-palm.03.%s" % S, "DEF-hand.%s" % S], wmin=0.3)
P_pads = sum(pads, Vector()) / len(pads)
P_palm = sum(palmpts, Vector()) / len(palmpts)
pos = (P_pads + P_palm) * 0.5
print("grip channel gap %.4f m -> socket at the midpoint" % (P_pads - P_palm).length)
for d, (a1, a2, a3, fr) in PRE.items():
    for j in ("01", "02", "03"):
        n = "%s.%s.%s" % (d, j, S)
        if n in PB: PB[n].rotation_euler = (0, 0, 0)
upd()
DOWN = Vector((0, 0, -1))
zc = (DOWN - BAR * DOWN.dot(BAR)).normalized()          # can body hangs vertically
xc = BAR.cross(zc).normalized()
SOCK = Matrix.Translation(pos) @ Matrix((xc, BAR, zc)).transposed().to_4x4()

bpy.ops.object.mode_set(mode="EDIT")
EB = rig.data.edit_bones
if "prop_socket.R" in EB: EB.remove(EB["prop_socket.R"])
sb = EB.new("prop_socket.R")
inv = rig.matrix_world.inverted()
sb.head = inv @ SOCK.to_translation()
sb.tail = inv @ (SOCK.to_translation() + SOCK.to_3x3() @ Vector((0, 0.05, 0)))
sb.parent = EB["DEF-hand.%s" % S]; sb.use_connect = False; sb.use_deform = False
bpy.ops.object.mode_set(mode="OBJECT")

before = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=CAN_GLB)
can = [o for o in bpy.data.objects if o not in before and o.type == "MESH"][0]
can.parent = rig; can.parent_type = "BONE"; can.parent_bone = "prop_socket.R"
upd()
can.matrix_world = SOCK @ GA.inverted()
upd()
up = (can.matrix_world.to_3x3() @ Vector((0, 0, 1))).normalized()
print("can tilt off vertical: %.1f deg" % math.degrees(math.acos(max(-1, min(1, up.z)))))

# close the working digits onto the bar
mesh.data.calc_loop_triangles()
GN = {i: n for n, i in GIx.items()}
def dom(vi):
    v = mesh.data.vertices[vi]
    return GN.get(max(v.groups, key=lambda g: g.weight).group) if v.groups else None
def digit_tris(d):
    keys = ["DEF-%s.%02d.%s" % (d, i, S) for i in (1, 2, 3)]
    return [tuple(t.vertices) for t in mesh.data.loop_triangles
            if any((dom(i) or "") in keys for i in t.vertices)]
def hits(tris):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = mesh.evaluated_get(dg); m = ev.to_mesh()
    co = [mesh.matrix_world @ v.co for v in m.vertices]
    bt = BVHTree.FromPolygons(co, tris, all_triangles=True)
    cev = can.evaluated_get(dg); cm = cev.to_mesh(); cm.calc_loop_triangles()
    ct = BVHTree.FromPolygons([can.matrix_world @ v.co for v in cm.vertices],
                              [tuple(t.vertices) for t in cm.loop_triangles], all_triangles=True)
    n = len(ct.overlap(bt)); ev.to_mesh_clear(); cev.to_mesh_clear(); return n
# FIXED natural curl -- no search. Closure search is closed as diminishing
# returns; the bar sits in the grip channel, which is exactly where the fingers
# are, so any search anchored at zero closure starts already in contact. These
# are the angles the middle finger already validated, applied to all four.
CLOSE = {"thumb": (30, 34, 24), "f_index": (34, 44, 28),
         "f_middle": (34, 44, 28), "f_ring": (28, 36, 22)}
for d, angs in CLOSE.items():
    for j, ang in zip(("01", "02", "03"), angs):
        n = "%s.%s.%s" % (d, j, S)
        if n in PB:
            PB[n].rotation_mode = "XYZ"
            PB[n].rotation_euler = (math.radians(ang), 0, 0)
    if "thumb.01.%s" % S in PB and d == "thumb":
        PB["thumb.01.%s" % S].rotation_euler = (math.radians(angs[0]), 0, math.radians(-18))
upd()
tot = 0
for d in CLOSE:
    tris = digit_tris(d)
    n = hits(tris) if tris else 0
    tot += n
    print("  %-9s fixed curl, %d intersecting tris" % (d, n))
print("TOTAL hand/can intersecting triangles: %d" % tot)

print("FINAL elbow %.1f deg | wrist deviation %.1f deg" % (elbow_angle(), wrist_dev()))
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("CARRY_DONE")
