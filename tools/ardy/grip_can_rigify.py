"""Right-hand watering-can grip on the Rigify rig. Gated by hand regression.

No geometry is modified and no fist is faked: each working digit closes only
until it contacts the handle. The pinky is left relaxed because it carries no
weight, and the ring closes only as far as its weak weighting allows.

  blender --background <rv_bound.blend> --python grip_can_rigify.py -- <can.glb> <outdir>
"""
import json, math, os, sys
import bpy
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:]
CAN_GLB, OUT = argv[0], argv[1]
os.makedirs(OUT, exist_ok=True)
SOIL = 0.22

rig = bpy.data.objects["rv_rigify"]
mesh = max([o for o in bpy.data.objects if o.type == "MESH"],
           key=lambda o: len(o.data.vertices))

exec(open("tools/ardy/hand_regression.py").read().split('if __name__')[0])
print("GATE: hand regression")
ok, fails = run_checks(rig, mesh)
for f in fails: print("   FAIL: %s" % f)
if not ok:
    raise SystemExit("ABORTED: hand regression failed; refusing to render a grip")
print("GATE PASSED")

PB = rig.pose.bones
GIx = {g.name: g.index for g in mesh.vertex_groups}

def reset():
    for b in PB:
        b.rotation_mode = "XYZ"; b.rotation_euler = (0, 0, 0); b.location = (0, 0, 0)
    bpy.context.view_layer.update()
reset()

# ---------------------------------------------------------- palm frame ------
S = "R"
hm = rig.matrix_world @ PB["DEF-hand.%s" % S].matrix
FING = (hm.to_3x3() @ Vector((0, 1, 0))).normalized()
ti = [GIx.get("DEF-thumb.%02d.%s" % (i, S)) for i in (1, 2, 3)]
tv = [mesh.matrix_world @ v.co for v in mesh.data.vertices
      if any(g.group in ti and g.weight > 0.4 for g in v.groups)]
fi = [GIx.get("DEF-f_%s.%02d.%s" % (d, i, S)) for d in ("index", "middle") for i in (1, 2)]
fv = [mesh.matrix_world @ v.co for v in mesh.data.vertices
      if any(g.group in fi and g.weight > 0.4 for g in v.groups)]
# Toward-the-thumb is the right axis for judging curl DIRECTION, but it is not
# the palm's surface normal -- the thumb sits off to the side. Seating a handle
# needs the true normal: the thin axis of the palm slab (PCA), with the thumb
# only used to fix its sign.
THUMBDIR = ((sum(tv, Vector()) / len(tv)) - (sum(fv, Vector()) / len(fv)))
THUMBDIR = (THUMBDIR - FING * THUMBDIR.dot(FING)).normalized()
# Rigify splits the palm across DEF-palm.01..04, so DEF-hand alone owns almost
# nothing above 0.5 -- sample the whole palm group set.
PALMIDX = [GIx.get("DEF-hand.%s" % S)] + [GIx.get("DEF-palm.0%d.%s" % (i, S))
                                          for i in (1, 2, 3, 4)]
PALMIDX = [i for i in PALMIDX if i is not None]
handv = [mesh.matrix_world @ v.co for v in mesh.data.vertices
         if any(g.group in PALMIDX and g.weight > 0.3 for g in v.groups)]
print("palm sample: %d verts" % len(handv))
PALM = sum(handv, Vector()) / len(handv)
_u = Vector((0, 0, 1)).cross(FING)
if _u.length < 1e-6: _u = Vector((1, 0, 0)).cross(FING)
_u.normalize(); _v = FING.cross(_u).normalized()
_sxx = _syy = _sxy = 0.0
for c in handv:
    _d = c - PALM; _a, _b = _d.dot(_u), _d.dot(_v)
    _sxx += _a * _a; _syy += _b * _b; _sxy += _a * _b
_th = 0.5 * math.atan2(2 * _sxy, _sxx - _syy)
_e1 = (_u * math.cos(_th) + _v * math.sin(_th)).normalized()
_e2 = FING.cross(_e1).normalized()
_v1 = sum(((c - PALM).dot(_e1)) ** 2 for c in handv)
_v2 = sum(((c - PALM).dot(_e2)) ** 2 for c in handv)
BAR, NRM = (_e1, _e2) if _v1 > _v2 else (_e2, _e1)
if NRM.dot(THUMBDIR) < 0: NRM = -NRM          # thumb fixes the sign only
if BAR.cross(NRM).dot(FING) < 0: BAR = -BAR
print("palm normal . thumbdir = %+.3f (sign check)" % NRM.dot(THUMBDIR))

META = json.load(open(CAN_GLB.replace(".glb", ".json")))
GA = Matrix(META["grip_anchor_basis_rows"])
BAR_R = META["dimensions_m"]["handle_bar_diameter"] / 2.0
# Seat the bar in the hand's actual GRIP CHANNEL, not at palm-centroid + lift.
# The old method put the bar 0.025 m off the palm centroid, which is exactly
# where the thumb tip sits, so the thumb and index had no collision-free pose at
# any closure. Curl the digits first, then measure the space they enclose.
PRECURL = {"f_index": 0.55, "f_middle": 0.55, "f_ring": 0.55, "thumb": 0.45}
BASE_ANG = {"f_index": (52, 68, 44), "f_middle": (52, 68, 44),
            "f_ring": (40, 52, 30), "thumb": (34, 40, 28)}
def set_digit(d, frac):
    for j, a in zip(("01", "02", "03"), BASE_ANG[d]):
        nm = "%s.%s.%s" % (d, j, S)
        if nm in PB:
            PB[nm].rotation_mode = "XYZ"
            PB[nm].rotation_euler = (math.radians(a * frac), 0, 0)
    if d == "thumb" and "thumb.01.R" in PB:
        PB["thumb.01.R"].rotation_euler = (math.radians(BASE_ANG[d][0] * frac), 0,
                                           math.radians(-22 * frac))
for d, f in PRECURL.items(): set_digit(d, f)
bpy.context.view_layer.update()

def surf_of(groups, wmin=0.5):
    idx = [GIx.get(g) for g in groups]
    idx = [i for i in idx if i is not None]
    dg = bpy.context.evaluated_depsgraph_get()
    ev = mesh.evaluated_get(dg); m = ev.to_mesh()
    pts = [mesh.matrix_world @ m.vertices[v.index].co for v in mesh.data.vertices
           if any(g.group in idx and g.weight > wmin for g in v.groups)]
    ev.to_mesh_clear()
    return pts

pads = surf_of(["DEF-f_index.03.%s" % S, "DEF-f_middle.03.%s" % S,
                "DEF-f_index.02.%s" % S, "DEF-f_middle.02.%s" % S])
palm_s = surf_of(["DEF-palm.01.%s" % S, "DEF-palm.02.%s" % S,
                  "DEF-palm.03.%s" % S, "DEF-hand.%s" % S], wmin=0.3)
if not pads or not palm_s:
    raise SystemExit("cannot sample the grip channel")
P_pads = sum(pads, Vector()) / len(pads)
# palm surface on the gripping side only
palm_face = [c for c in palm_s if (c - PALM).dot(NRM) > 0]
P_palm = sum(palm_face, Vector()) / len(palm_face) if palm_face else PALM
CHANNEL = (P_pads + P_palm) * 0.5
gap = (P_pads - P_palm).length
print("grip channel: pads<->palm gap %.4f m, bar diameter %.4f m" % (gap, BAR_R * 2))
print("  channel centre %.4f m off the palm centroid along the normal"
      % (CHANNEL - PALM).dot(NRM))
for d in PRECURL: set_digit(d, 0.0)
bpy.context.view_layer.update()

SOCK = (Matrix.Translation(CHANNEL)
        @ Matrix((BAR.cross(NRM), BAR, NRM)).transposed().to_4x4())

before = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=CAN_GLB)
can = [o for o in bpy.data.objects if o not in before and o.type == "MESH"][0]
can.parent = rig; can.parent_type = "BONE"; can.parent_bone = "DEF-hand.%s" % S
def seat():
    bpy.context.view_layer.update()
    sock = rig.matrix_world @ PB["DEF-hand.%s" % S].matrix @ SOCK_LOCAL
    can.matrix_world = sock @ GA.inverted()
    bpy.context.view_layer.update()
SOCK_LOCAL = (rig.matrix_world @ PB["DEF-hand.%s" % S].matrix).inverted() @ SOCK
seat()
OFFS = {k: Vector(v) for k, v in META["markers"].items()}
def spout(): return can.matrix_world @ OFFS["spout_tip"]
def anchor(): return can.matrix_world @ GA
def sock_world(): return rig.matrix_world @ PB["DEF-hand.%s" % S].matrix @ SOCK_LOCAL
def drift():
    a, b = anchor(), sock_world()
    return ((a.to_translation() - b.to_translation()).length,
            math.degrees(a.to_quaternion().rotation_difference(b.to_quaternion()).angle))

mesh.data.calc_loop_triangles()
GN = {i: n for n, i in GIx.items()}
def dom(vi):
    v = mesh.data.vertices[vi]
    return GN.get(max(v.groups, key=lambda g: g.weight).group) if v.groups else None
HANDKEY = ("DEF-hand.R", "DEF-f_", "DEF-thumb", "DEF-palm")
BODY_TRIS = [tuple(t.vertices) for t in mesh.data.loop_triangles
             if not any((dom(i) or "").startswith(HANDKEY) for i in t.vertices)]
def intersections(tris):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = mesh.evaluated_get(dg); m = ev.to_mesh()
    co = [mesh.matrix_world @ v.co for v in m.vertices]
    bt = BVHTree.FromPolygons(co, tris, all_triangles=True)
    cev = can.evaluated_get(dg); cm = cev.to_mesh(); cm.calc_loop_triangles()
    ct = BVHTree.FromPolygons([can.matrix_world @ v.co for v in cm.vertices],
                              [tuple(t.vertices) for t in cm.loop_triangles],
                              all_triangles=True)
    n = len(ct.overlap(bt))
    ev.to_mesh_clear(); cev.to_mesh_clear()
    return n
def digit_tris(d):
    idx = ["DEF-%s.%02d.%s" % (d, i, S) for i in (1, 2, 3)]
    return [tuple(t.vertices) for t in mesh.data.loop_triangles
            if any((dom(i) or "") in idx for i in t.vertices)]

# ------------------------------------------------------- watering pose ------
for n in ("upper_arm_parent.R",):
    if n in PB:
        try: PB[n]["IK_FK"] = 1.0
        except Exception: pass
PB["torso"].rotation_mode = "XYZ"; PB["torso"].rotation_euler = (math.radians(12), 0, 0)
for s in ("L", "R"):
    PB["thigh_fk." + s].rotation_mode = "XYZ"
    PB["thigh_fk." + s].rotation_euler = (math.radians(-10), 0, 0)
    PB["shin_fk." + s].rotation_mode = "XYZ"
    PB["shin_fk." + s].rotation_euler = (math.radians(16), 0, 0)
PB["upper_arm_fk.R"].rotation_mode = "XYZ"
PB["upper_arm_fk.R"].rotation_euler = (math.radians(-34), 0, math.radians(-8))
PB["forearm_fk.R"].rotation_mode = "XYZ"
PB["forearm_fk.R"].rotation_euler = (math.radians(-22), 0, 0)
bpy.context.view_layer.update(); seat()

# tilt the can by rolling the wrist, keeping the nozzle down and forward
def can_tilt():
    up = (can.matrix_world.to_3x3() @ Vector((0, 0, 1))).normalized()
    return math.degrees(math.acos(max(-1.0, min(1.0, up.z))))
best = None
for rx in range(-40, 41, 8):
    for rz in range(-50, 51, 10):
        PB["hand_fk.R"].rotation_mode = "XYZ"
        PB["hand_fk.R"].rotation_euler = (math.radians(rx), 0, math.radians(rz))
        bpy.context.view_layer.update(); seat()
        t = can_tilt(); s_ = spout()
        d = (s_ - anchor().to_translation()).normalized()
        err = abs(t - 45) / 15.0 + abs(s_.z - (SOIL + 0.24)) * 3.0 + max(0.0, d.z + 0.4) * 2.0
        if best is None or err < best[0]: best = (err, rx, rz)
_, rx, rz = best
PB["hand_fk.R"].rotation_euler = (math.radians(rx), 0, math.radians(rz))
bpy.context.view_layer.update(); seat()
print("wrist rx=%d rz=%d -> can tilt %.1f deg, spout %.3f m (%.3f above soil)"
      % (rx, rz, can_tilt(), spout().z, spout().z - SOIL))

# ------------------------------------------------------------- the grip -----
CLOSE = {"thumb": (34, 40, 28), "f_index": (52, 68, 44),
         "f_middle": (52, 68, 44), "f_ring": (40, 52, 30)}
report = {}
for d, angs in CLOSE.items():
    tris = digit_tris(d)
    if not tris:
        report[d] = "no surface - left relaxed"; continue
    def put(f):
        for j, a in zip(("01", "02", "03"), angs):
            nm = "%s.%s.%s" % (d, j, S)
            if nm in PB:
                PB[nm].rotation_mode = "XYZ"
                PB[nm].rotation_euler = (math.radians(a * f), 0, 0)
        if d == "thumb":
            PB["thumb.01.R"].rotation_euler = (math.radians(angs[0] * f), 0,
                                               math.radians(-22 * f))
        bpy.context.view_layer.update()
    # Sweep, do not bisect: the thumb already touches the can at rest, so a
    # search anchored at zero closure can never start from a clear state. Going
    # negative abducts the digit out of the way first.
    ok_f, contact = None, None
    f = -0.8
    while f <= 1.0001:
        put(f)
        if intersections(tris) == 0:
            ok_f = f
        elif ok_f is not None:
            contact = f; break
        f += 0.05
    if ok_f is None:
        put(-0.8)
        report[d] = "NO CLEAR POSE even fully abducted (%d intersections)" % intersections(tris)
    else:
        put(ok_f)
        report[d] = ("closed to %+.0f%% (contact at %s)"
                     % (ok_f * 100, "%+.0f%%" % (contact * 100) if contact else "no contact reached"))
for d, v in report.items(): print("   %-9s %s" % (d, v))
print("   f_pinky   left relaxed (unweighted)")

dp, dr = drift()
print("GRIP anchor drift: %.9f m, %.7f deg" % (dp, dr))
print("GRIP body/can intersections: %d" % intersections(BODY_TRIS))
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "grip_pose.blend"))

# ------------------------------------------------------------- renders -----
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.view_settings.view_transform = "Standard"
sc.render.image_settings.file_format = "PNG"
try:
    sc.eevee.use_raytracing = True; sc.eevee.use_shadows = True
except AttributeError: pass
sc.world = sc.world or bpy.data.worlds.new("W"); sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs[0].default_value = (.30, .34, .40, 1)
bpy.ops.object.light_add(type="SUN", location=(3, -4, 5))
_k = bpy.context.object; _k.data.energy = 3.2
_k.rotation_euler = (math.radians(46), 0, math.radians(28))
bpy.ops.object.light_add(type="AREA", location=(-3, -3, 2))
_f = bpy.context.object; _f.data.energy = 300; _f.data.size = 5
_f.rotation_euler = (math.radians(75), 0, math.radians(-45))
cd = bpy.data.cameras.new("C"); cam = bpy.data.objects.new("C", cd)
sc.collection.objects.link(cam); sc.camera = cam

def shot(tag, focus, dist, az, el, lens, res):
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

# gameplay framing: SpringArm3D length 5.2 m, Camera3D fov 65 (src/player/player.gd).
# Godot's fov is VERTICAL, so on Blender's 36 mm sensor that is
# 18 / tan(32.5 deg) = 28.3 mm, not the 18 mm a horizontal reading would give.
GAMEPLAY_LENS = 28.3
for az in (0, 35, -35):
    shot("gameplay_az%+d" % az, Vector((0, 0, 1.0)), 5.2, az, 12, GAMEPLAY_LENS, 1000)
# how many pixels does the hand actually occupy at that framing?
_h = (rig.matrix_world @ PB["DEF-hand.R"].matrix).to_translation()
_px = 1000.0 * 0.095 / (2.0 * 5.2 * math.tan(math.radians(32.5)))
print("hand spans about %.0f px of a 1000 px gameplay frame" % _px)
hand = (rig.matrix_world @ PB["DEF-hand.R"].matrix).to_translation()
for az, tag in ((-70, "palm"), (110, "dorsal"), (20, "side")):
    shot("grip_%s" % tag, hand, 0.30, az, 12, 80, 900)
print("GRIP_DONE")
