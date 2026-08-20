"""Author the water_can constraint reference locally: start / pour / return.

No generation. These are hand-specified poses on the accepted derived rig,
built to satisfy the approved constraint set, so that a later ARDY run can be
driven by end-effector constraints instead of prompt wording.

  blender --background --python pose_reference.py -- <rig.glb> <can.glb> <outdir>
"""
import json, math, os, sys
import bpy, mathutils
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:]
RIG_GLB, CAN_GLB, OUT = argv[0], argv[1], argv[2]
os.makedirs(OUT, exist_ok=True)

SOIL = 0.22
# Reach measured on this rig: shoulder 1.5584 m, shoulder->wrist 0.7153 m, so the
# lowest wrist at 15 deg lean + 0.10 m hip drop is 0.7236 m. 0.65 m is therefore
# unreachable without the deep fold the target excludes; poses sit at 0.76 m.
POSES = {
  # Arm straight down buries the can in the thigh, so the carry poses abduct it
  # slightly -- the same thing a person does to keep a full can off their leg.
  "01_start":  dict(lean=2.0,  hip_drop=0.00, hand=Vector((-0.30, -0.10, 0.88)),
                    carry=True),
  # 0.80 m is the top of the approved hand band and the only height that also
  # allows meaningful forward reach: at 15 deg lean + 0.10 m drop the shoulder is
  # at 1.439 m and the arm is 0.715 m, so 0.76 m would consume the entire reach
  # vertically and leave the hand directly under the shoulder.
  "02_pour":   dict(lean=12.5, hip_drop=0.095, hand=Vector((-0.32, -0.45, 0.79))),
  "03_return": dict(lean=4.0,  hip_drop=0.01, hand=Vector((-0.29, -0.14, 0.87)),
                    carry=True),
}

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=RIG_GLB)
rig = [o for o in bpy.data.objects if o.type == "ARMATURE"][0]
obj = max([o for o in bpy.data.objects if o.type == "MESH" and len(o.vertex_groups)],
          key=lambda o: len(o.data.vertices))
before = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=CAN_GLB)
can = [o for o in bpy.data.objects if o not in before and o.type == "MESH"][0]
OFF = {k: Vector(v) for k, v in json.load(open(CAN_GLB.replace(".glb", ".json")))["markers"].items()}
can.parent = rig; can.parent_type = "BONE"; can.parent_bone = "prop_socket.R"
BFP = Matrix.Rotation(math.radians(90), 4, "X")

bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode="POSE")
PB = rig.pose.bones

def upd(): bpy.context.view_layer.update()
def wpos(n): return (rig.matrix_world @ PB[n].matrix).to_translation()

REST = {b.name: (rig.matrix_world @ b.bone.matrix_local).to_translation() for b in PB}

def pitch(pb, deg):
    m = pb.matrix.copy(); T = Matrix.Translation(m.to_translation())
    pb.matrix = T @ Matrix.Rotation(math.radians(deg), 4, "X") @ T.inverted() @ m; upd()

def aim(pb, target):
    m = pb.matrix.copy()
    cur = (m.to_3x3() @ Vector((0, 1, 0))).normalized()
    tgt = (Vector(target) - m.to_translation()).normalized()
    if tgt.length < 1e-6: return
    T = Matrix.Translation(m.to_translation())
    pb.matrix = T @ cur.rotation_difference(tgt).to_matrix().to_4x4() @ T.inverted() @ m; upd()

def ccd(chain, effector, target, iters=25):
    """Cyclic coordinate descent: simple, robust, no analytic edge cases."""
    for _ in range(iters):
        for name in reversed(chain):
            pb = PB[name]
            o = pb.matrix.to_translation()
            e = wpos(effector)
            v1 = (e - o); v2 = (Vector(target) - o)
            if v1.length < 1e-6 or v2.length < 1e-6: continue
            q = v1.normalized().rotation_difference(v2.normalized())
            T = Matrix.Translation(o)
            pb.matrix = T @ q.to_matrix().to_4x4() @ T.inverted() @ pb.matrix; upd()
        if (wpos(effector) - Vector(target)).length < 1e-4: break
    return (wpos(effector) - Vector(target)).length

def place_can():
    sock = rig.matrix_world @ PB["prop_socket.R"].matrix
    can.matrix_world = sock @ BFP; upd()

def spout(): return can.matrix_world @ OFF["spout_tip"]
def grip():  return can.matrix_world @ OFF["grip_origin"]

def orient_can(target_z, mode="pour"):
    """Aim the nozzle: DOWN, FORWARD (-Y) and at the wanted height.

    Roll about the arm axis alone cannot do this -- it spins the can around the
    forearm but leaves the nozzle azimuth wherever the arm solve left it, which
    is how the spout ended up pointing back at the knees. Search roll AND a
    world-X pitch of the hand together.
    """
    base = PB["hand.R"].matrix.copy()
    def apply(roll, pitch_deg):
        PB["hand.R"].matrix = base.copy(); upd()
        m = PB["hand.R"].matrix.copy()
        axis = (m.to_3x3() @ Vector((0, 1, 0))).normalized()
        T = Matrix.Translation(m.to_translation())
        PB["hand.R"].matrix = T @ Matrix.Rotation(math.radians(roll), 4, axis) @ T.inverted() @ m
        upd()
        m = PB["hand.R"].matrix.copy()
        T = Matrix.Translation(m.to_translation())
        PB["hand.R"].matrix = T @ Matrix.Rotation(math.radians(pitch_deg), 4, "X") @ T.inverted() @ m
        upd(); place_can()
    cands = []
    for roll in range(-180, 180, 12):
        for pdeg in range(-80, 81, 10):
            apply(roll, pdeg)
            s_, g_ = spout(), grip()
            d = (s_ - g_).normalized()
            if mode == "carry":
                # Carried: body upright so the water stays in, nozzle roughly level.
                up = (can.matrix_world.to_3x3() @ Vector((0, 0, -1))).normalized()
                err = (up.z + 1.0) * 3.0 + abs(d.z) * 0.5
            else:
                err = abs(s_.z - target_z) * 3.0
                err += max(0.0, d.z + 0.35) * 2.0    # want clearly downward
                err += max(0.0, d.y + 0.30) * 2.0    # want clearly forward (-Y)
            cands.append((err, roll, pdeg))
    # Aiming the nozzle forward can swing the can into the thigh, so rank by the
    # cheap score but accept only the best orientation that is actually clear.
    cands.sort()
    for err, roll, pdeg in cands[:80]:
        apply(roll, pdeg)
        if body_can_intersections() == 0:
            print("  nozzle roll=%d pitch=%d err=%.3f (collision-free)" % (roll, pdeg, err))
            return (err, roll, pdeg)
    raise SystemExit("NO COLLISION-FREE CAN ORIENTATION (%s)" % mode)

# --- intersection test (surface vs surface), reused from intersect_test
GRIP_BONES = {"hand.R", "forearm.R"}
# Testing only the largest mesh silently ignores the trousers, and the carried
# can was buried in the hip while the test reported zero. Cover every skinned mesh.
SKINNED = [o for o in bpy.data.objects
           if o.type == "MESH" and o is not can and len(o.vertex_groups)]
BODY = {}
for so in SKINNED:
    gn = {g.index: g.name for g in so.vertex_groups}
    def dom(vi, so=so, gn=gn):
        v = so.data.vertices[vi]
        return gn.get(max(v.groups, key=lambda g: g.weight).group) if v.groups else None
    so.data.calc_loop_triangles()
    BODY[so.name] = [tuple(t.vertices) for t in so.data.loop_triangles
                     if not any(dom(v) in GRIP_BONES for v in t.vertices)]
print("collision set: " + ", ".join("%s=%d" % (k, len(v)) for k, v in BODY.items()))
def body_can_intersections():
    """Both meshes must be compared in the SAME space -- world."""
    dg = bpy.context.evaluated_depsgraph_get()
    cev = can.evaluated_get(dg); cm = cev.to_mesh()
    cco = [can.matrix_world @ v.co for v in cm.vertices]
    ctr = [tuple(t.vertices) for t in cm.loop_triangles] if cm.loop_triangles else []
    if not ctr:
        cm.calc_loop_triangles(); ctr = [tuple(t.vertices) for t in cm.loop_triangles]
    ct = BVHTree.FromPolygons(cco, ctr, all_triangles=True)
    n = 0
    for so in SKINNED:
        ev = so.evaluated_get(dg); m = ev.to_mesh()
        co = [so.matrix_world @ v.co for v in m.vertices]
        n += len(ct.overlap(BVHTree.FromPolygons(co, BODY[so.name], all_triangles=True)))
        ev.to_mesh_clear()
    cev.to_mesh_clear()
    return n

report = {}
for name, spec in POSES.items():
    for pb in PB: pb.matrix_basis.identity()
    upd()
    hips_rest = wpos("hips")
    ankles = {s: wpos("foot." + s) for s in ("R", "L")}
    if spec["hip_drop"]:
        # Pose-bone .location is in BONE-LOCAL axes and the hips bone points up,
        # so .z moves it sideways. Translate the matrix in world space instead.
        PB["hips"].matrix = Matrix.Translation((0, 0, -spec["hip_drop"])) @ PB["hips"].matrix
        upd()
        for sd in ("R", "L"):
            ccd(["thigh." + sd, "shin." + sd], "foot." + sd, ankles[sd], iters=40)
    # `lean` is the VISIBLE trunk angle (hips -> neck), which is what reads on
    # screen. Rotating spine+chest by that amount undershoots it, because the
    # hips segment of the trunk axis does not rotate -- 15 deg applied gives
    # only 8.3 deg visible. Solve for the applied amount instead of assuming.
    applied = spec["lean"]
    for _ in range(6):
        PB["spine"].matrix_basis.identity(); PB["chest"].matrix_basis.identity(); upd()
        pitch(PB["spine"], applied * 0.55)
        pitch(PB["chest"], applied * 0.45)
        vis = math.degrees(math.atan2(-(wpos("neck") - wpos("hips")).y,
                                       (wpos("neck") - wpos("hips")).z))
        if abs(vis - spec["lean"]) < 0.15: break
        applied *= spec["lean"] / max(1.0, vis)
    print("  lean: applied %.1f deg -> visible %.1f deg" % (applied, vis))
    err = None
    if spec["hand"]:
        # Derive a REACHABLE target rather than trusting a hard-coded point:
        # aim down-and-forward from the shoulder at 95% of arm reach.
        sh = wpos("upperarm.R")
        reach = (PB["upperarm.R"].bone.length + PB["forearm.R"].bone.length) * 0.97
        # Clamping the whole direction vector trades away HEIGHT, which is the
        # constrained axis. Hold the target height and clamp horizontally instead.
        d = Vector(spec["hand"]) - sh
        dz = d.z
        if abs(dz) > reach:
            raise SystemExit("UNREACHABLE: hand z=%.3f needs %.3f m of a %.3f m arm"
                             % (spec["hand"].z, abs(dz), reach))
        r_max = math.sqrt(reach * reach - dz * dz)
        h = Vector((d.x, d.y, 0.0))
        if h.length > r_max: h = h.normalized() * r_max
        tgt = sh + Vector((h.x, h.y, dz))
        print("  reach %.3f  shoulder z %.3f  horiz budget %.3f (wanted %.3f)"
              % (reach, sh.z, r_max, Vector((d.x, d.y, 0.0)).length))
        err = ccd(["upperarm.R", "forearm.R"], "hand.R", tgt, iters=40)
        orient_can(SOIL + 0.24, "carry" if spec.get("carry") else "pour")
    place_can()
    hips = wpos("hips"); hand = wpos("hand.R")
    # Trunk = spine head -> neck head. Measuring from the HIPS head instead spans
    # the un-rotated hips bone as well and reports roughly half the true lean.
    v = wpos("neck") - wpos("spine")
    report[name] = {
        "trunk_lean_visible_deg": round(math.degrees(math.atan2(
            -(wpos("neck") - wpos("hips")).y, (wpos("neck") - wpos("hips")).z)), 2),
        "trunk_lean_spine_chain_deg": round(math.degrees(math.atan2(-v.y, v.z)), 2),
        "hip_drop_m": round(hips_rest.z - hips.z, 4),
        "hand_height_m": round(hand.z, 4),
        "hand_lateral_from_hip_m": round(abs(hand.x - wpos("thigh.R").x), 4),
        "hand_forward_of_hips_m": round(hips.y - hand.y, 4),
        "spout_height_m": round(spout().z, 4),
        "spout_above_soil_m": round(spout().z - SOIL, 4),
        "spout_points_down": round((spout() - grip()).normalized().z, 3),
        "foot_R_z": round(wpos("foot.R").z, 4), "foot_L_z": round(wpos("foot.L").z, 4),
        "ik_error_m": round(err, 5) if err is not None else None,
        "body_can_intersections": body_can_intersections(),
    }
    print(name, json.dumps(report[name]))
    # keyframe so the pose can be re-rendered / exported
    for pb in PB:
        pb.rotation_mode = "QUATERNION"
        pb.keyframe_insert("rotation_quaternion", frame=list(POSES).index(name) + 1)
        pb.keyframe_insert("location", frame=list(POSES).index(name) + 1)

bad = {k: v["body_can_intersections"] for k, v in report.items()
       if v["body_can_intersections"]}
if bad:
    raise SystemExit("POSES INTERSECT THE BODY: %s" % bad)
json.dump(report, open(os.path.join(OUT, "pose_reference.json"), "w"), indent=2)
bpy.ops.object.mode_set(mode="OBJECT")
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "pose_reference.blend"))
print("POSE_REFERENCE_DONE")
