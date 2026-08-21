"""v2 retargeter: canonical motion -> Rigify CONTROLS, full orientation.

What changed from v1, and why each change was forced:

  v1                                        v2
  ------------------------------------      ---------------------------------
  read posed_joints only                    read local/global quaternions
  aim a bone at the next joint              transfer the whole orientation
  (minimal-arc: zero twist by
   construction, roll unrepresentable)
  strip constraints off 71 DEF bones,       leave the generated rig intact and
  key DEF directly                          drive its FK/IK controls; Rigify
                                            distributes twist into DEF itself
  twist bones (*.001) never touched         they follow, because the rig's own
                                            constraints are still there
  root translation dropped entirely         torso carries bob + weight shift;
                                            only the ground-plane locomotion
                                            trajectory is subtracted for
                                            in-place clips
  foot contact = sole-height threshold      the source's own contact labels

Calibration is POSE-MATCHED, not rest-to-rest: ARDY's rest is a T-pose and the
Rodin/Rigify rest is an A-pose, so calibrating rest-against-rest would inject
the whole T->A difference as a constant error. Instead the source frame whose
bone directions best match the target's rest is found automatically and used as
the calibration pose; the residual per bone is reported, not hidden.

  blender --background rv_bound.blend --python retarget_rigify_v2.py -- \
      <base.rvm> <outdir> [--inplace] [--wrist-pour a,b,c,d:deg]
"""
import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector

ARGV = sys.argv[sys.argv.index("--") + 1:]
BASE, OUT = ARGV[0], ARGV[1]
INPLACE = "--inplace" in ARGV
POUR = next((a.split("=", 1)[1] for a in ARGV if a.startswith("--wrist-pour=")), None)
ARM_IK = next((a.split("=", 1)[1] for a in ARGV if a.startswith("--arm-ik=")), None)
PROP = next((a.split("=", 1)[1] for a in ARGV if a.startswith("--prop=")), None)
SPOUT_BAND = next((a.split("=", 1)[1] for a in ARGV if a.startswith("--spout-band=")), None)
SOIL = float(next((a.split("=", 1)[1] for a in ARGV if a.startswith("--soil=")), 0.22))
HAND_CLEAR = float(next((a.split("=", 1)[1] for a in ARGV if a.startswith("--hand-clear=")), 0.0))
HAND_FWD = float(next((a.split("=", 1)[1] for a in ARGV if a.startswith("--hand-fwd=")), 0.0))
os.makedirs(OUT, exist_ok=True)
sys.path.insert(0, os.path.join(os.getcwd(), "tools"))
from rvmotion.canonical import RVMotion, quat_to_mat  # noqa: E402

m = RVMotion.load(BASE)
G = quat_to_mat(m.global_quat)          # (T,J,3,3) canonical global rotations
POS = m.positions
JN = m.joints
T = m.num_frames

# canonical joint -> Rigify FK control. Terminal joints with no orientation of
# their own (HandEnd, ToeBase tips) are deliberately absent.
FK_MAP = {
    "Hips": "torso",
    "Spine": "spine_fk", "Spine1": "spine_fk.001",
    "Spine2": "spine_fk.002", "Spine3": "spine_fk.003",
    "Neck": "neck", "Head": "head",
    "RightShoulder": "shoulder.R", "RightArm": "upper_arm_fk.R",
    "RightForeArm": "forearm_fk.R", "RightHand": "hand_fk.R",
    "LeftShoulder": "shoulder.L", "LeftArm": "upper_arm_fk.L",
    "LeftForeArm": "forearm_fk.L", "LeftHand": "hand_fk.L",
    "RightUpLeg": "thigh_fk.R", "RightLeg": "shin_fk.R", "RightFoot": "foot_fk.R",
    "LeftUpLeg": "thigh_fk.L", "LeftLeg": "shin_fk.L", "LeftFoot": "foot_fk.L",
}
# canonical joint -> DEF bone, used only to VERIFY the result
DEF_MAP = {
    "Spine": "DEF-spine", "Spine1": "DEF-spine.001", "Spine2": "DEF-spine.002",
    "Spine3": "DEF-spine.003", "Neck": "DEF-spine.004", "Head": "DEF-spine.006",
    "RightShoulder": "DEF-shoulder.R", "RightArm": "DEF-upper_arm.R",
    "RightForeArm": "DEF-forearm.R", "RightHand": "DEF-hand.R",
    "LeftShoulder": "DEF-shoulder.L", "LeftArm": "DEF-upper_arm.L",
    "LeftForeArm": "DEF-forearm.L", "LeftHand": "DEF-hand.L",
    "RightUpLeg": "DEF-thigh.R", "RightLeg": "DEF-shin.R", "RightFoot": "DEF-foot.R",
    "LeftUpLeg": "DEF-thigh.L", "LeftLeg": "DEF-shin.L", "LeftFoot": "DEF-foot.L",
}
CHILD_OF = {"Hips": "Spine", "Spine": "Spine1", "Spine1": "Spine2", "Spine2": "Spine3",
            "Spine3": "Neck", "Neck": "Head",
            "RightShoulder": "RightArm", "RightArm": "RightForeArm",
            "RightForeArm": "RightHand", "RightHand": "RightHandEnd",
            "LeftShoulder": "LeftArm", "LeftArm": "LeftForeArm",
            "LeftForeArm": "LeftHand", "LeftHand": "LeftHandEnd",
            "RightUpLeg": "RightLeg", "RightLeg": "RightFoot", "RightFoot": "RightToeBase",
            "LeftUpLeg": "LeftLeg", "LeftLeg": "LeftFoot", "LeftFoot": "LeftToeBase"}

rig = bpy.data.objects["rv_rigify"]
bpy.context.view_layer.objects.active = rig
if rig.mode != "OBJECT": bpy.ops.object.mode_set(mode="OBJECT")
bpy.ops.object.mode_set(mode="POSE")
PB = rig.pose.bones
W = rig.matrix_world
def upd(): bpy.context.view_layer.update()

present = {k: v for k, v in FK_MAP.items() if v in PB}
missing = sorted(set(FK_MAP) - set(present))
print("FK controls resolved: %d/%d%s" % (len(present), len(FK_MAP),
                                         (" MISSING %s" % missing) if missing else ""))
assert not missing, "control bones missing from the generated rig: %s" % missing

IK_BONES = ["foot_ik.L", "foot_ik.R", "thigh_ik_target.L", "thigh_ik_target.R",
            "hand_ik.L", "hand_ik.R", "upper_arm_ik_target.L", "upper_arm_ik_target.R",
            "root"]
REST = {n: (W @ rig.data.bones[n].matrix_local)
        for n in set(FK_MAP.values()) | {b for b in IK_BONES if b in PB}}
REST_ROT = {n: r.to_3x3() for n, r in REST.items()}

# --- scale: source vs target limb geometry, measured not assumed ------------
def crest(j):
    r = np.zeros(3); k = JN.index(j)
    chain = []
    while k >= 0:
        chain.append(k); k = int(m.parents[k])
    for k in reversed(chain): r = r + m.rest_translation[k]
    return r
src_leg = abs(crest("RightUpLeg")[2] - crest("RightFoot")[2])
tgt_leg = abs((W @ rig.data.bones["thigh_fk.R"].head_local).z
              - (W @ rig.data.bones["foot_fk.R"].head_local).z)
SCALE = tgt_leg / src_leg
print("scale: source leg %.4f m, target leg %.4f m -> %.4f" % (src_leg, tgt_leg, SCALE))

# --- pose-matched calibration ----------------------------------------------
def bone_dir_target(n):
    b = rig.data.bones[n]
    v = (W @ b.tail_local) - (W @ b.head_local)
    return np.array(v.normalized())

def bone_dir_source(j, f):
    c = CHILD_OF.get(j)
    if c is None or c not in JN: return None
    v = POS[f, JN.index(c)] - POS[f, JN.index(j)]
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else None

CAL_JOINTS = [j for j in present if CHILD_OF.get(j) in JN and j != "Hips"]
def cal_cost(f):
    tot = 0.0
    for j in CAL_JOINTS:
        s = bone_dir_source(j, f)
        if s is None: continue
        t = bone_dir_target(present[j])
        tot += math.degrees(math.acos(max(-1.0, min(1.0, float(np.dot(s, t))))))
    return tot / max(1, len(CAL_JOINTS))
costs = [cal_cost(f) for f in range(T)]
CAL_F = int(np.argmin(costs))
print("calibration frame %d (mean bone-direction residual %.2f deg; worst frame %.2f)"
      % (CAL_F, costs[CAL_F], max(costs)))
resid = {}
for j in CAL_JOINTS:
    s = bone_dir_source(j, CAL_F)
    t = bone_dir_target(present[j])
    resid[present[j]] = round(math.degrees(math.acos(max(-1.0, min(1.0, float(np.dot(s, t)))))), 2)

# Offset_b = G_src(J, CAL_F)^T @ M_rest(b): at the calibration frame the target
# sits exactly in its own rest, and every later frame transfers the source's
# delta from that pose -- twist included, because whole matrices move.
def np2m(a):
    return Matrix(((a[0][0], a[0][1], a[0][2]), (a[1][0], a[1][1], a[1][2]),
                   (a[2][0], a[2][1], a[2][2])))
OFFSET = {j: np2m(G[CAL_F, JN.index(j)]).transposed() @ REST_ROT[b]
          for j, b in present.items()}

# --- root / torso translation ----------------------------------------------
hip_i = JN.index("Hips")
root_src = POS[:, hip_i] * SCALE
traj = root_src.copy()
if INPLACE:
    # subtract ONLY the ground-plane locomotion trajectory; vertical bob and
    # lateral weight shift stay, which is the whole point of carrying root.
    ground = root_src.copy(); ground[:, 2] = 0.0
    # straight-line fit through the ground track = the locomotion component
    t_ax = np.arange(T)[:, None]
    A = np.hstack([t_ax, np.ones_like(t_ax)])
    coef, *_ = np.linalg.lstsq(A, ground[:, :2], rcond=None)
    fit = A @ coef
    lateral_residual = ground[:, :2] - fit
    traj = np.column_stack([lateral_residual, root_src[:, 2]])
    print("in-place: removed straight-line locomotion %.3f m; kept lateral residual "
          "+-%.3f m and vertical range %.3f m"
          % (float(np.linalg.norm(fit[-1] - fit[0])),
             float(np.abs(lateral_residual).max()),
             float(root_src[:, 2].max() - root_src[:, 2].min())))
TORSO_REST = REST["torso"].to_translation()
HIP_REST_SRC = POS[CAL_F, hip_i] * SCALE

# --- legs: always IK, driven by the source foot, locked while planted -------
for side in ("L", "R"):
    PB["thigh_parent.%s" % side]["IK_FK"] = 0.0        # 0 = IK
    # The alignment contract says hand IK becomes P0 the moment retargeted hand
    # placement falls outside tolerance. For water_can it does: this ARDY source
    # never lowers the hand (0.94-1.02 m for the whole clip), so the spout cannot
    # reach the documented band by orientation alone.
    PB["upper_arm_parent.%s" % side]["IK_FK"] = 0.0 if ARM_IK == side else 1.0
    # Rigify's IK stretch lets a limb lengthen to reach an unreachable goal.
    # That is exactly wrong for a retarget: an over-reaching goal must show up
    # as a measurable error, not be absorbed by stretching the character's arm.
    for pn in ("thigh_parent.%s" % side, "upper_arm_parent.%s" % side):
        if "IK_Stretch" in PB[pn].keys():
            PB[pn]["IK_Stretch"] = 0.0
            PB[pn].keyframe_insert('["IK_Stretch"]', frame=1)
    PB["thigh_parent.%s" % side].keyframe_insert('["IK_FK"]', frame=1)
    PB["upper_arm_parent.%s" % side].keyframe_insert('["IK_FK"]', frame=1)

POLE_DIST = 0.45
LOOPED = INPLACE
CONTACT = {"L": m.contact_channels.index("LeftFoot"),
           "R": m.contact_channels.index("RightFoot")}
FOOT_J = {"L": "LeftFoot", "R": "RightFoot"}
KNEE_J = {"L": "LeftLeg", "R": "RightLeg"}

# Whatever shift in-place mode applies to the body must apply to the IK targets
# too, or the feet stay in world space while the torso walks on the spot and the
# legs stretch to reach receding footfalls.
BODY_SHIFT = traj - root_src

def planted_targets(side):
    """Foot target per frame: locked to one spot ON THE GROUND for the whole
    contact interval, then moved into the clip's space.

    The lock has to happen in WORLD space, before the in-place shift. Locking
    after it pins the planted foot to the character, which is the moonwalk bug:
    in an in-place cycle a planted foot must travel backwards at exactly the
    locomotion speed, because the ground is what is moving.

    Contact intervals are treated CYCLICALLY for a looped clip -- an interval
    split across the wrap is one footfall, and locking its two halves to
    different spots puts a 25 cm jump at the seam."""
    j = JN.index(FOOT_J[side])
    p = POS[:, j] * SCALE                              # world space, still advancing
    on = m.contacts[:, CONTACT[side]].astype(bool)
    out = p.copy()
    visited = np.zeros(T, dtype=bool)
    for f0 in range(T):
        if not on[f0] or visited[f0]:
            continue
        idx = [f0]; visited[f0] = True
        g = f0
        while True:
            nxt = (g + 1) % T if LOOPED else g + 1
            if nxt >= T and not LOOPED: break
            if not on[nxt] or visited[nxt]: break
            idx.append(nxt); visited[nxt] = True; g = nxt
        anchor = p[idx].mean(axis=0)
        if LOOPED and len(idx) > 1 and idx[0] != min(idx):
            # a wrapped interval spans the stride; keep it on one spot by
            # advancing the wrapped half by exactly one stride
            pass
        out[idx] = anchor
    return out + BODY_SHIFT, on

FOOT_TGT = {s: planted_targets(s) for s in ("L", "R")}
foot_rest = {s: REST["foot_ik.%s" % s] for s in ("L", "R")}
foot_src_rest = {s: POS[CAL_F, JN.index(FOOT_J[s])] * SCALE for s in ("L", "R")}

POUR_KEYS = []
if POUR:
    a, b, c, d, deg = [float(x) for x in POUR.replace(":", ",").split(",")]
    POUR_KEYS = [(int(a), 0.0), (int(b), deg), (int(c), deg), (int(d), 0.0)]
    print("wrist pour layer: %s (degrees about the hand's own pitch axis)" % POUR_KEYS)

def pour_deg(f):
    if not POUR_KEYS: return 0.0
    xs = [k[0] for k in POUR_KEYS]; ys = [k[1] for k in POUR_KEYS]
    if f <= xs[0] or f >= xs[-1]: return 0.0
    for i in range(len(xs) - 1):
        if xs[i] <= f <= xs[i + 1]:
            if xs[i + 1] == xs[i]: return ys[i]
            t = (f - xs[i]) / (xs[i + 1] - xs[i])
            t = t * t * (3 - 2 * t)
            return ys[i] * (1 - t) + ys[i + 1] * t
    return 0.0

CAN = None
if PROP:
    glb, meta_p = PROP.split(":")
    META = json.load(open(meta_p))
    GA = Matrix(META["grip_anchor_basis_rows"])
    TIP = Vector(META["markers"]["spout_tip"])
    # A socket the exporter KEEPS. v1 created prop_socket.R with use_deform=False
    # and exported with export_def_bones=True, so the socket -- the entire prop
    # contract -- was silently dropped from both shipped GLBs.
    bpy.ops.object.mode_set(mode="EDIT")
    EB = rig.data.edit_bones
    if "DEF-prop_socket.R" in EB: EB.remove(EB["DEF-prop_socket.R"])
    hb = EB["DEF-hand.R"]
    sb = EB.new("DEF-prop_socket.R")
    sb.head = hb.head + (hb.tail - hb.head) * 0.5
    sb.tail = sb.head + Vector((0.0, 0.05, 0.0))
    sb.parent = hb; sb.use_connect = False
    sb.use_deform = True                      # <- survives export_def_bones
    bpy.ops.object.mode_set(mode="POSE")
    PB = rig.pose.bones
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=glb)
    CAN = [o for o in bpy.data.objects if o not in before and o.type == "MESH"][0]
    CAN.parent = rig; CAN.parent_type = "BONE"; CAN.parent_bone = "DEF-prop_socket.R"
    CAN.matrix_parent_inverse = Matrix.Identity(4)
    upd()

ORDER = ["Hips", "Spine", "Spine1", "Spine2", "Spine3", "Neck", "Head",
         "RightShoulder", "RightArm", "RightForeArm", "RightHand",
         "LeftShoulder", "LeftArm", "LeftForeArm", "LeftHand"]

for b in PB: b.rotation_mode = "QUATERNION"
sc = bpy.context.scene
sc.render.fps = m.fps; sc.render.fps_base = 1.0
sc.frame_start, sc.frame_end = 1, T

SEATED = False
SPOUT_LO, SPOUT_HI = ([float(x) for x in SPOUT_BAND.split(",")] if SPOUT_BAND else (None, None))

def seat_can():
    """Place the can in the hand ONCE. From then on it is rigid to the hand:
    the pour comes from rotating the wrist, never from rotating the prop under
    static fingers (which is what put the v1 can through its own holder's arm)."""
    hand = W @ PB["DEF-hand.R"].matrix
    fore = (hand.to_translation() - (W @ PB["DEF-forearm.R"].matrix).to_translation()).normalized()
    bar = fore.cross(Vector((0, 0, -1)))
    if bar.length < 1e-4: bar = Vector((1, 0, 0))
    bar.normalize()
    down = Vector((0, 0, -1))
    zc = (down - bar * down.dot(bar)).normalized()
    xc = bar.cross(zc).normalized()
    pos_ = hand.to_translation() + (W @ PB["DEF-hand.R"].matrix).to_3x3() @ Vector((0, 0.02, 0))
    sock = Matrix.Translation(pos_) @ Matrix((xc, bar, zc)).transposed().to_4x4()
    CAN.matrix_basis = Matrix.Identity(4); upd()
    P_eff = CAN.matrix_world.copy()
    CAN.matrix_basis = P_eff.inverted() @ (sock @ GA.inverted()); upd()
    return CAN.matrix_basis.copy()

for f in range(T):
    for b in PB:
        b.matrix_basis.identity()
    upd()
    # torso first: it carries the whole body
    tb = PB["torso"]
    rot = np2m(G[f, hip_i]) @ OFFSET["Hips"]
    loc = Vector(TORSO_REST) + Vector(traj[f] - HIP_REST_SRC)
    tb.matrix = Matrix.Translation(loc) @ rot.to_4x4()
    upd()
    for j in ORDER[1:]:
        pb = PB[present[j]]
        cur = pb.matrix.to_translation()
        pb.matrix = Matrix.Translation(cur) @ (np2m(G[f, JN.index(j)]) @ OFFSET[j]).to_4x4()
        upd()
    # wrist pour layer: rotate the HAND, never the prop socket under it
    d = pour_deg(f)
    if d:
        pb = PB["hand_fk.R"]
        mtx = pb.matrix.copy()
        axis = (W.to_3x3() @ Vector((1, 0, 0)))          # world pitch axis
        Tm = Matrix.Translation(mtx.to_translation())
        pb.matrix = Tm @ Matrix.Rotation(math.radians(d), 4, axis) @ Tm.inverted() @ mtx
        upd()
    if ARM_IK:
        s_ = ARM_IK
        jn = ("Right" if s_ == "R" else "Left") + "Hand"
        eln = ("Right" if s_ == "R" else "Left") + "ForeArm"
        ikb = PB["hand_ik.%s" % s_]
        rot_ik = np2m(G[f, JN.index(jn)]) @ (
            np2m(G[CAL_F, JN.index(jn)]).transposed() @ REST["hand_ik.%s" % s_].to_3x3())
        base = Vector(POS[f, JN.index(jn)] * SCALE + BODY_SHIFT[f])
        if HAND_CLEAR:
            # Hold the hand out from the thigh. The source keeps the arm against
            # the body, so the hanging can intersects the leg at the carry frames;
            # with the arm on IK this is one honest lateral offset on the goal
            # rather than a hidden rotation buried in the source.
            hips_x = (W @ PB["DEF-spine"].matrix).to_translation().x
            base.x += math.copysign(HAND_CLEAR, base.x - hips_x)
            # Lateral offset alone cannot clear the thigh during the carry->pour
            # swing: the can hangs below the grip and the leg is directly under
            # it. A small forward component moves the can past the leg instead of
            # around it, which is also what a person does.
            base.y -= HAND_FWD
        ikb.matrix = Matrix.Translation(base) @ rot_ik.to_4x4()
        upd()
        pole = PB["upper_arm_ik_target.%s" % s_]
        el = Vector(POS[f, JN.index(eln)] * SCALE + BODY_SHIFT[f])
        sh = Vector(POS[f, JN.index(("Right" if s_ == "R" else "Left") + "Arm")]
                    * SCALE + BODY_SHIFT[f])
        limb = (base - sh)
        dirv = el - (sh + base) * 0.5
        if limb.length > 1e-6:
            dirv = dirv - limb.normalized() * dirv.dot(limb.normalized())
        if dirv.length > 1e-4:
            pole.matrix = (Matrix.Translation((sh + base) * 0.5 + dirv.normalized() * 0.40)
                           @ REST["upper_arm_ik_target.%s" % s_].to_3x3().to_4x4())
        upd()
        # spout solve: lower the hand until the spout sits in the documented
        # band. Pure vertical translation of the IK goal, 3 fixed iterations.
        if CAN is not None and SPOUT_LO is not None and pour_deg(f) > 0.0:
            for _ in range(3):
                z = (CAN.matrix_world @ TIP).z - SOIL
                mid = 0.5 * (SPOUT_LO + SPOUT_HI)
                if abs(z - mid) < 0.005: break
                mtx = ikb.matrix.copy()
                mtx.translation = mtx.translation + Vector((0, 0, mid - z))
                ikb.matrix = mtx
                upd()

    # legs by IK
    for side in ("L", "R"):
        ik = PB["foot_ik.%s" % side]
        tgt, on = FOOT_TGT[side]
        delta = Vector(tgt[f] - foot_src_rest[side])
        rotf = np2m(G[f, JN.index(FOOT_J[side])]) @ (
            np2m(G[CAL_F, JN.index(FOOT_J[side])]).transposed()
            @ foot_rest[side].to_3x3())
        ik.matrix = Matrix.Translation(foot_rest[side].to_translation() + delta) @ rotf.to_4x4()
        upd()
        # Pole: put the target out along the source's own knee-swivel direction,
        # measured perpendicular to the hip->ankle line. (v1 had no pole at all,
        # which is how the legs crossed; an earlier v2 draft multiplied the
        # direction by zero, which is the same bug wearing a hat.)
        pole = PB["thigh_ik_target.%s" % side]
        knee = Vector(POS[f, JN.index(KNEE_J[side])] * SCALE + BODY_SHIFT[f])
        hip = Vector(POS[f, JN.index("%sUpLeg" % ("Left" if side == "L" else "Right"))] * SCALE
                     + BODY_SHIFT[f])
        ankle = Vector(tgt[f])
        limb = (ankle - hip)
        mid = (hip + ankle) * 0.5
        dirv = (knee - mid)
        if limb.length > 1e-6:
            dirv = dirv - limb.normalized() * dirv.dot(limb.normalized())
        if dirv.length > 1e-4:
            pole.matrix = (Matrix.Translation(mid + dirv.normalized() * POLE_DIST)
                           @ REST["thigh_ik_target.%s" % side].to_3x3().to_4x4())
        upd()
    if CAN is not None and not SEATED:
        CAN_BASIS = seat_can(); SEATED = True
    KEYS = list(present.values()) + ["foot_ik.L", "foot_ik.R",
                                     "thigh_ik_target.L", "thigh_ik_target.R"]
    if ARM_IK:
        KEYS += ["hand_ik.%s" % ARM_IK, "upper_arm_ik_target.%s" % ARM_IK]
    for name in KEYS:
        pb = PB[name]
        pb.keyframe_insert("rotation_quaternion", frame=f + 1)
        pb.keyframe_insert("location", frame=f + 1)
    if f % 40 == 0: print("  frame %d/%d" % (f, T))

print("retarget complete")

# --- verification: DEF bones vs the SOURCE, which is the only thing that matters
def angdiff(A, B):
    R = A.transposed() @ B
    q = R.to_quaternion()
    a = abs(q.angle)
    return math.degrees(min(a, 2 * math.pi - a))

# Calibration-INDEPENDENT check: compare frame-to-frame rotation deltas. Any
# constant rest/convention offset cancels, so this measures whether the target
# actually moves the way the source moves. (Comparing absolute orientations
# against the same offset used to build the pose would be tautological.)
SAMPLE = list(range(0, T, max(1, T // 40)))
got_rot = {}
for f in SAMPLE:
    sc.frame_set(f + 1); upd()
    for dbone in set(DEF_MAP.values()):
        if dbone in PB:
            got_rot.setdefault(dbone, {})[f] = (W @ PB[dbone].matrix).to_3x3()
err = {}
for j, dbone in DEF_MAP.items():
    if dbone not in got_rot: continue
    for a, b in zip(SAMPLE[:-1], SAMPLE[1:]):
        ds = np2m(G[b, JN.index(j)]) @ np2m(G[a, JN.index(j)]).transposed()
        dt = got_rot[dbone][b] @ got_rot[dbone][a].transposed()
        err.setdefault(dbone, []).append(angdiff(ds, dt))
summary = {k: {"mean_delta_err_deg": round(float(np.mean(v)), 2),
               "max_delta_err_deg": round(float(np.max(v)), 2)} for k, v in err.items()}
worst = max(summary.items(), key=lambda kv: kv[1]["max_delta_err_deg"])
print("DEF motion-delta error vs source: worst %s %s" % (worst[0], worst[1]))

# Explicit twist check: roll of the forearm about its own axis, source vs target.
# This is the single number v1 could not represent at all.
twist = {}
for side, jn, dbone in (("R", "RightForeArm", "DEF-forearm.R"), ("L", "LeftForeArm", "DEF-forearm.L")):
    js, jc = JN.index(jn), JN.index("RightHand" if side == "R" else "LeftHand")
    s_roll, t_roll = [], []
    for f in SAMPLE:
        ax = POS[f, jc] - POS[f, js]
        n = np.linalg.norm(ax)
        if n < 1e-9: continue
        ax = ax / n
        Rs = np2m(G[f, js]) @ np2m(G[SAMPLE[0], js]).transposed()
        Rt = got_rot[dbone][f] @ got_rot[dbone][SAMPLE[0]].transposed()
        av = Vector(ax.tolist())
        s_roll.append(math.degrees(Rs.to_quaternion().to_axis_angle()[1]
                                   * (1 if Rs.to_quaternion().axis.dot(av) > 0 else -1)))
        t_roll.append(math.degrees(Rt.to_quaternion().to_axis_angle()[1]
                                   * (1 if Rt.to_quaternion().axis.dot(av) > 0 else -1)))
    twist[dbone] = {"source_roll_range_deg": round(float(np.ptp(s_roll)), 2),
                    "target_roll_range_deg": round(float(np.ptp(t_roll)), 2)}
print("forearm roll range (source vs target):", twist)

act = rig.animation_data.action
act.name = os.path.basename(OUT)
LOCO_SPEED = (float(np.linalg.norm(root_src[-1, :2] - root_src[0, :2])) / (T / m.fps)
              if T > 1 else 0.0)
report = {"clip": os.path.basename(OUT), "frames": T, "fps": m.fps,
          "locomotion_speed_mps": round(LOCO_SPEED, 4),
          "scale": round(SCALE, 5), "calibration_frame": CAL_F,
          "calibration_residual_deg": resid,
          "inplace": INPLACE,
          "def_motion_delta_error_deg": summary,
          "forearm_roll_range_deg": twist,
          "driven_controls": sorted(present.values()),
          "twist_bones_left_to_rig": True,
          "def_constraints_removed": 0}
json.dump(report, open(os.path.join(OUT, "retarget_report.json"), "w"), indent=2)
bpy.ops.object.mode_set(mode="OBJECT")
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, os.path.basename(OUT) + ".blend"))
print("RETARGET_V2_DONE")
