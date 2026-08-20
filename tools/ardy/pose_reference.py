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

# Geometry that fixes these numbers, measured on this rig:
#   shoulder 1.5584 m, shoulder->wrist 0.7153 m. With the knees nearly straight
#   (0.025 m drop) the shoulder sits at ~1.520 m, so the hand cannot go below
#   ~0.81 m -- which is why the hand band had to open up to 0.85 m.
#   The can's grip->tip vector is 0.323 m and sits 68.2 deg off the body axis, so
#   putting the tip 0.15-0.30 m above soil forces a body tilt of at least ~46 deg.
CAN_TILT_TARGET = 47.0          # degrees off vertical; brief allows 35-50
CAN_TILT_RANGE = (35.0, 50.0)
POSES = {
  # Carry poses abduct the arm slightly so a full can clears the thigh, and share
  # one neutral carry orientation so start and return read as the same hold.
  "01_start":  dict(lean=2.0,  hip_drop=0.000, hand=Vector((-0.30, -0.10, 0.88)),
                    carry=True),
  "02_pour":   dict(lean=12.5, hip_drop=0.025, hand=Vector((-0.38, -0.45, 0.82))),
  "03_return": dict(lean=4.0,  hip_drop=0.005, hand=Vector((-0.30, -0.12, 0.88)),
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

def solve_two_bone(root, mid, effector, target, pole_dir):
    """Analytic two-bone IK with an explicit pole direction.

    CCD constrains only the end effector, never the joint swivel, so it settles
    on whatever rotation the iteration reaches -- which rotated the thighs inward
    and crossed the legs while every foot-height check still passed. Placing the
    knee/elbow explicitly makes that impossible.
    """
    H = wpos(root)
    L1 = (wpos(mid) - H).length
    L2 = (wpos(effector) - wpos(mid)).length
    A = Vector(target)
    u = A - H
    d = u.length
    if d < 1e-6: return 0.0
    u = u / d
    d = min(d, (L1 + L2) * 0.999)
    a = (L1 * L1 - L2 * L2 + d * d) / (2 * d)
    h = math.sqrt(max(0.0, L1 * L1 - a * a))
    pole = Vector(pole_dir)
    f = pole - u * pole.dot(u)              # pole, projected off the root->target axis
    if f.length < 1e-6: f = Vector((0, 0, 1)).cross(u)
    f.normalize()
    aim(PB[root], H + u * a + f * h)        # knee/elbow lands on the pole side
    aim(PB[mid], A)
    return (wpos(effector) - A).length

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

def can_tilt_deg():
    """Angle of the can's body axis off vertical. 0 = upright, 90 = on its side."""
    up = (can.matrix_world.to_3x3() @ Vector((0, 0, 1))).normalized()
    return math.degrees(math.acos(max(-1.0, min(1.0, up.z))))

FACE = None
def face_dir():
    return (rig.matrix_world @ PB["head"].matrix).to_3x3() @ FACE

MAX_HEAD_PITCH = 40.0

def head_pitch():
    f = face_dir()
    return math.degrees(math.atan2(-f.z, math.hypot(f.x, f.y)))

def gaze(target, max_deg=38.0):
    """Pitch the head so the face points at `target`, within a natural limit."""
    o = wpos("head")
    cur, des = face_dir(), (Vector(target) - o)
    a_cur = math.atan2(cur.z, -cur.y)
    a_des = math.atan2(des.z, -des.y)
    d = math.degrees(a_des - a_cur)
    d = max(-max_deg, min(max_deg, d))
    base = PB["head"].matrix.copy()
    best = None
    for sign in (1.0, -1.0):
        PB["head"].matrix = base.copy(); upd()
        pitch(PB["head"], d * sign)
        e = face_dir().angle((Vector(target) - wpos("head")).normalized())
        if best is None or e < best[0]: best = (e, sign)
    # Cap how far the head actually ends up pitched. Looking straight at soil a
    # third of a metre ahead needs ~75 deg, which no one does -- the eyes cover
    # the rest, and the neck stops at a natural limit.
    lo, hi = 0.0, d * best[1]
    for _ in range(14):
        mid = (lo + hi) / 2.0
        PB["head"].matrix = base.copy(); upd(); pitch(PB["head"], mid)
        if abs(head_pitch()) > MAX_HEAD_PITCH: hi = mid
        else: lo = mid
    PB["head"].matrix = base.copy(); upd(); pitch(PB["head"], lo)
    return round(math.degrees(
        face_dir().angle((Vector(target) - wpos("head")).normalized())), 1)

def frame_from(b1, b2):
    """Orthonormal basis whose first axis is b1 and whose second lies toward b2."""
    e1 = Vector(b1).normalized()
    e2 = (Vector(b2) - e1 * Vector(b2).dot(e1))
    e2.normalize()
    return Matrix((e1, e2, e1.cross(e2))).transposed()

def pour_orientation(tilt_deg, spout_from_vertical_deg, outboard=-1.0, yaw_deg=0.0):
    """Set the can's world orientation directly, instead of searching roll+pitch.

    Roll about the arm axis plus a world-X pitch spans only two of the three
    rotational degrees of freedom, so the orientation this pose needs -- body
    tilted ~47 deg forward AND spout steeply down-forward -- is simply not
    reachable by that search. Build the rotation and apply the delta to the hand.
    """
    t_local = (OFF["spout_tip"] - OFF["grip_origin"]).normalized()
    cos_ta = t_local.dot(Vector((0, 0, 1)))          # fixed by the can's geometry
    a = math.radians(spout_from_vertical_deg)
    d = Vector((0.0, -math.sin(a), -math.cos(a)))    # spout: down and forward
    uz = math.cos(math.radians(tilt_deg))
    # up.dot(d) must equal cos_ta; solve for the remaining components.
    uy = (cos_ta - d.z * uz) / d.y
    ux2 = 1.0 - uy * uy - uz * uz
    if ux2 < 0:
        raise SystemExit("CAN ORIENTATION INCONSISTENT: tilt %.1f deg cannot pair "
                         "with a spout %.1f deg off vertical" % (tilt_deg, spout_from_vertical_deg))
    up = Vector((math.copysign(math.sqrt(ux2), outboard), uy, uz))
    # Tilting the can forward can swing its body into the thigh; yawing the whole
    # solved frame moves the body outboard without changing tilt or spout pitch.
    Rz = Matrix.Rotation(math.radians(yaw_deg), 3, "Z")
    up, d = Rz @ up, Rz @ d
    R1 = frame_from(up, d) @ frame_from(Vector((0, 0, 1)), t_local).transposed()
    R0 = can.matrix_world.to_3x3()
    dR = (R1 @ R0.inverted()).to_4x4()
    m = PB["hand.R"].matrix.copy()
    T = Matrix.Translation(m.to_translation())
    PB["hand.R"].matrix = T @ dR @ T.inverted() @ m
    upd(); place_can()

def orient_can(target_z, mode="pour", reuse=None):
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
    if reuse is not None:                 # start and return share one carry hold
        apply(*reuse)
        if body_can_intersections() == 0:
            print("  carry orientation reused: roll=%d pitch=%d tilt=%.1f deg"
                  % (reuse[0], reuse[1], can_tilt_deg()))
            return (0.0, reuse[0], reuse[1])
    cands = []
    for roll in range(-180, 180, 6):
        for pdeg in range(-90, 91, 6):
            apply(roll, pdeg)
            s_, g_ = spout(), grip()
            d = (s_ - g_).normalized()
            tilt = can_tilt_deg()
            if mode == "carry":
                # Carried: body upright so the water stays in, nozzle roughly level.
                err = tilt / 15.0 + abs(d.z) * 0.5
            else:
                # A vertical spout under a horizontal body is the "mallet" read;
                # constrain the BODY tilt, not just where the nozzle points.
                if not (CAN_TILT_RANGE[0] <= tilt <= CAN_TILT_RANGE[1]):
                    continue
                err = abs(tilt - CAN_TILT_TARGET) / 15.0
                err += abs(s_.z - target_z) * 3.0
                err += max(0.0, d.z + 0.45) * 2.0    # down, but not straight down
                err += max(0.0, d.y + 0.35) * 2.0    # and clearly forward (-Y)
            cands.append((err, roll, pdeg))
    # Aiming the nozzle forward can swing the can into the thigh, so rank by the
    # cheap score but accept only the best orientation that is actually clear.
    cands.sort()
    for err, roll, pdeg in cands[:80]:
        apply(roll, pdeg)
        if body_can_intersections() == 0:
            print("  can roll=%d pitch=%d tilt=%.1f deg err=%.3f (collision-free)"
                  % (roll, pdeg, can_tilt_deg(), err))
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

# Which local axis of the head bone points out of the face? Measure it rather
# than assume -- the glTF import orientation is not guaranteed.
for pb in PB: pb.matrix_basis.identity()
upd()
_hm = (rig.matrix_world @ PB["head"].matrix).to_3x3()
FACE = max([Vector(a) for a in ((1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1))],
           key=lambda a: (_hm @ a).normalized().dot(Vector((0, -1, 0))))
print("head face axis (local): %s" % (tuple(FACE),))

report = {}
CARRY_HOLD = None
for name, spec in POSES.items():
    for pb in PB: pb.matrix_basis.identity()
    upd()
    hips_rest = wpos("hips")
    ankles = {s: wpos("foot." + s) for s in ("R", "L")}
    foot_rest = {s: PB["foot." + s].matrix.copy() for s in ("R", "L")}
    if spec["hip_drop"]:
        # Pose-bone .location is in BONE-LOCAL axes and the hips bone points up,
        # so .z moves it sideways. Translate the matrix in world space instead.
        PB["hips"].matrix = Matrix.Translation((0, 0, -spec["hip_drop"])) @ PB["hips"].matrix
        upd()
        for sd in ("R", "L"):
            # Knees forward (the character faces -Y), never swivelled inward.
            solve_two_bone("thigh." + sd, "shin." + sd, "foot." + sd,
                           ankles[sd], (0.0, -1.0, 0.0))
            # Bending the knee tilts the shin, which would tip the sole off the
            # ground; restore the foot's rest orientation so it stays planted.
            fm = PB["foot." + sd].matrix
            PB["foot." + sd].matrix = (Matrix.Translation(fm.to_translation())
                                       @ foot_rest[sd].to_3x3().to_4x4())
            upd()
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
        reach = (PB["upperarm.R"].bone.length + PB["forearm.R"].bone.length) * 0.99
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
        err = solve_two_bone("upperarm.R", "forearm.R", "hand.R", tgt,
                             (-0.3, 1.0, 0.0))
        if spec.get("carry"):
            hold = orient_can(SOIL + 0.24, "carry", reuse=CARRY_HOLD)
            if CARRY_HOLD is None: CARRY_HOLD = (hold[1], hold[2])
        else:
            # Solve orientation and hand height together: the orientation fixes
            # how far the tip hangs below the grip, so the hand height follows.
            want_tip = SOIL + 0.29
            base_tgt = tgt.copy()
            solved = None
            for yaw in (0, -12, 12, -24, 24, -36, 36, -48, 48):
                for ob in (-1.0, 1.0):
                    tgt = base_tgt.copy()
                    for _ in range(5):
                        solve_two_bone("upperarm.R", "forearm.R", "hand.R", tgt,
                                       (-0.3, 1.0, 0.0))
                        pour_orientation(CAN_TILT_TARGET, 22.0, ob, yaw)
                        dz = want_tip - spout().z
                        if abs(dz) < 0.004: break
                        tz = max(0.78, min(0.85, wpos("hand.R").z + dz))
                        d2 = Vector((base_tgt.x, base_tgt.y, tz)) - wpos("upperarm.R")
                        if abs(d2.z) >= reach: break
                        r2 = math.sqrt(reach * reach - d2.z * d2.z)
                        h2 = Vector((d2.x, d2.y, 0.0))
                        if h2.length > r2: h2 = h2.normalized() * r2
                        tgt = wpos("upperarm.R") + Vector((h2.x, h2.y, d2.z))
                    if body_can_intersections() == 0:
                        solved = (yaw, ob); break
                if solved: break
            if not solved:
                raise SystemExit("NO COLLISION-FREE POUR at tilt %.0f deg" % CAN_TILT_TARGET)
            print("  pour can: tilt %.1f deg, tip %.3f m, hand %.3f m, yaw %d"
                  % (can_tilt_deg(), spout().z, wpos("hand.R").z, solved[0]))
    # Free arm: hanging at the rest angle reads as flared backward once the
    # torso leans, so hold it a little forward of the shoulder with a soft elbow.
    sh_l = wpos("upperarm.L")
    solve_two_bone("upperarm.L", "forearm.L", "hand.L",
                   sh_l + Vector((0.02, -0.10, -0.68)), (0.3, 1.0, 0.0))
    place_can()

    # Look at the work, not through it.
    if spec.get("carry"):
        gz = wpos("head") + Vector((0.0, -3.0, -0.55))
    else:
        # Aim straight ahead down the body's own axis; a target off to the side
        # only produces a yaw error this single-axis gaze cannot remove.
        gz = Vector((wpos("head").x, spout().y, SOIL))
    gaze_err = gaze(gz)
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
        "can_tilt_deg": round(can_tilt_deg(), 1),
        "gaze_error_deg": gaze_err,
        "head_pitch_below_horiz_deg": round(math.degrees(
            math.atan2(-face_dir().z, math.hypot(face_dir().x, face_dir().y))), 1),
        "left_hand_fwd_of_hips_m": round(hips.y - wpos("hand.L").y, 4),
        "knee_gap_m": round(wpos("shin.L").x - wpos("shin.R").x, 4),
        "ankle_gap_m": round(wpos("foot.L").x - wpos("foot.R").x, 4),
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
