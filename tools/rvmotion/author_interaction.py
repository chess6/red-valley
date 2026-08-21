"""Author an interaction clip directly on the Rigify rig. No generator involved.

ADR 0001: interaction one-shots are defined by exact placement against a fixed
prop, which is what generative motion models are worst at and keyframes are best
at. This drives Rigify's OWN IK controls from a small JSON spec, so the pose is
stated rather than requested and then inspected.

Everything downstream is unchanged: the result is an ordinary posed rig, so the
same validator, exporter and Godot round-trip apply.

  blender --background rv_bound.blend --python author_interaction.py -- <spec.json> <outdir>
"""
import json
import math
import os
import sys

import bpy
from mathutils import Matrix, Quaternion, Vector

ARGV = sys.argv[sys.argv.index("--") + 1:]
SPEC_PATH, OUT = ARGV[0], ARGV[1]
spec = json.load(open(SPEC_PATH))
os.makedirs(OUT, exist_ok=True)

FPS = int(spec["fps"])
N = int(round(spec["duration_s"] * FPS))
rig = bpy.data.objects["rv_rigify"]
bpy.context.view_layer.objects.active = rig
if rig.mode != "OBJECT":
    bpy.ops.object.mode_set(mode="OBJECT")
bpy.ops.object.mode_set(mode="POSE")
PB = rig.pose.bones
W = rig.matrix_world
sc = bpy.context.scene
sc.render.fps = FPS
sc.render.fps_base = 1.0
sc.frame_start, sc.frame_end = 1, N
def upd(): bpy.context.view_layer.update()

# limbs on IK, stretch off, poles enabled -- same rig configuration the
# retargeter established and validated
for side in ("L", "R"):
    for pn in ("thigh_parent.%s" % side, "upper_arm_parent.%s" % side):
        if pn in PB:
            if "IK_FK" in PB[pn].keys():
                PB[pn]["IK_FK"] = 0.0
                PB[pn].keyframe_insert('["IK_FK"]', frame=1)
            if "IK_Stretch" in PB[pn].keys():
                PB[pn]["IK_Stretch"] = 0.0
                PB[pn].keyframe_insert('["IK_Stretch"]', frame=1)
            if "pole_vector" in PB[pn].keys():
                PB[pn]["pole_vector"] = True
                PB[pn].keyframe_insert('["pole_vector"]', frame=1)

REST = {n: (W @ rig.data.bones[n].matrix_local) for n in
        ("torso", "foot_ik.L", "foot_ik.R", "hand_ik.R", "hand_ik.L",
         "thigh_ik_target.L", "thigh_ik_target.R", "upper_arm_ik_target.R",
         "spine_fk", "spine_fk.001", "spine_fk.002", "spine_fk.003") if n in PB}
SPINE = [n for n in ("spine_fk", "spine_fk.001", "spine_fk.002", "spine_fk.003") if n in PB]


def smooth(a, b, t):
    t = max(0.0, min(1.0, t))
    return a + (b - a) * (t * t * (3 - 2 * t))


def sample(field):
    """Piecewise-smooth interpolation of one spec channel over every frame."""
    ks = spec["keys"]
    out = []
    for f in range(N):
        t = f / float(FPS)
        if t <= ks[0]["t"]:
            out.append(ks[0][field]); continue
        if t >= ks[-1]["t"]:
            out.append(ks[-1][field]); continue
        for a, b in zip(ks[:-1], ks[1:]):
            if a["t"] <= t <= b["t"]:
                u = (t - a["t"]) / max(1e-6, b["t"] - a["t"])
                va, vb = a[field], b[field]
                if isinstance(va, list):
                    out.append([smooth(x, y, u) for x, y in zip(va, vb)])
                else:
                    out.append(smooth(va, vb, u))
                break
    return out


hand_r = sample("hand_r")
tilt = sample("can_tilt_deg")
lean = sample("lean_deg")
pel_dy = sample("pelvis_dy")
foot_fwd = sample("foot_l_fwd")

# lead-foot swing: value AND slope zero at both ends, so lift-off is not a jump
st = spec.get("step", {})
sw_a = int(round(st.get("swing_from_s", 0.0) * FPS))
sw_b = int(round(st.get("swing_to_s", 0.0) * FPS))
lift_m = float(st.get("lift_m", 0.0))
lift = []
for f in range(N):
    if sw_a < f < sw_b and sw_b > sw_a:
        u = (f - sw_a) / float(sw_b - sw_a)
        lift.append(lift_m * 0.5 * (1.0 - math.cos(2.0 * math.pi * u)))
    else:
        lift.append(0.0)

CAN = None
if spec.get("prop"):
    meta = json.load(open(spec["prop"]["meta"]))
    GA = Matrix(meta["grip_anchor_basis_rows"])
    TIP = Vector(meta["markers"]["spout_tip"])
    bpy.ops.object.mode_set(mode="EDIT")
    EB = rig.data.edit_bones
    if "DEF-prop_socket.R" in EB:
        EB.remove(EB["DEF-prop_socket.R"])
    hb = EB[spec["prop"]["socket_parent"]]
    sb = EB.new("DEF-prop_socket.R")
    sb.head = hb.head + (hb.tail - hb.head) * 0.5
    sb.tail = sb.head + Vector((0.0, 0.05, 0.0))
    sb.parent = hb
    sb.use_connect = False
    sb.use_deform = True          # so it survives export_def_bones
    bpy.ops.object.mode_set(mode="POSE")
    PB = rig.pose.bones
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=spec["prop"]["glb"])
    CAN = [o for o in bpy.data.objects if o not in before and o.type == "MESH"][0]
    CAN.parent = rig
    CAN.parent_type = "BONE"
    CAN.parent_bone = "DEF-prop_socket.R"
    CAN.matrix_parent_inverse = Matrix.Identity(4)
    upd()

foot_rest = {s: REST["foot_ik.%s" % s].to_translation() for s in ("L", "R")}
seated = False
for f in range(N):
    for b in PB:
        b.matrix_basis.identity()
    upd()

    # torso: pelvis height and the forward carry of the step
    tb = PB["torso"]
    tb.matrix = Matrix.Translation(
        REST["torso"].to_translation()
        + Vector((0.0, -foot_fwd[f] * 0.5, -pel_dy[f]))) @ REST["torso"].to_3x3().to_4x4()
    upd()

    # trunk lean, shared across the spine, absolute each frame
    per = math.radians(lean[f]) / max(1, len(SPINE))
    for n in SPINE:
        pb = PB[n]
        m = pb.matrix.copy()
        T = Matrix.Translation(m.to_translation())
        pb.matrix = T @ Matrix.Rotation(per, 4, Vector((1, 0, 0))) @ T.inverted() @ m
        upd()

    # feet: rear planted, lead stepped and lifted
    PB["foot_ik.R"].matrix = (Matrix.Translation(foot_rest["R"])
                              @ REST["foot_ik.R"].to_3x3().to_4x4())
    PB["foot_ik.L"].matrix = (Matrix.Translation(
        foot_rest["L"] + Vector((0.0, -foot_fwd[f], lift[f])))
        @ REST["foot_ik.L"].to_3x3().to_4x4())
    upd()

    # right hand: absolute world target, wrist rolled to tip the can
    ik = PB["hand_ik.R"]
    base = REST["hand_ik.R"]
    ik.matrix = Matrix.Translation(Vector(hand_r[f])) @ base.to_3x3().to_4x4()
    upd()
    if CAN is not None:
        if not seated:
            hand = W @ PB["DEF-hand.R"].matrix
            fore = (hand.to_translation()
                    - (W @ PB["DEF-forearm.R"].matrix).to_translation()).normalized()
            bar = fore.cross(Vector((0, 0, -1)))
            if bar.length < 1e-4:
                bar = Vector((1, 0, 0))
            bar.normalize()
            down = Vector((0, 0, -1))
            zc = (down - bar * down.dot(bar)).normalized()
            xc = bar.cross(zc).normalized()
            sock = Matrix.Translation(
                hand.to_translation() + hand.to_3x3() @ Vector((0, 0.02, 0))) \
                @ Matrix((xc, bar, zc)).transposed().to_4x4()
            CAN.matrix_basis = Matrix.Identity(4); upd()
            P_eff = CAN.matrix_world.copy()
            CAN.matrix_basis = P_eff.inverted() @ (sock @ GA.inverted()); upd()
            seated = True
        if tilt[f] > 0.01:
            axis = (CAN.matrix_world @ GA).to_3x3().col[1].normalized()
            m = ik.matrix.copy()
            T = Matrix.Translation(m.to_translation())
            ik.matrix = T @ Matrix.Rotation(math.radians(tilt[f]), 4, axis) \
                @ T.inverted() @ m
            upd()

    for n in ["torso", "foot_ik.L", "foot_ik.R", "hand_ik.R"] + SPINE:
        PB[n].keyframe_insert("rotation_quaternion", frame=f + 1)
        PB[n].keyframe_insert("location", frame=f + 1)

print("authored %d frames at %d fps" % (N, FPS))
if CAN is not None:
    lo, hi = 1e9, -1e9
    for f in range(N):
        sc.frame_set(f + 1); upd()
        z = (CAN.matrix_world @ TIP).z - spec["soil_height_m"]
        lo, hi = min(lo, z), max(hi, z)
    print("spout above bed: %.3f .. %.3f m" % (lo, hi))
act = rig.animation_data.action
act.name = spec["name"]
bpy.ops.object.mode_set(mode="OBJECT")
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, spec["name"] + ".blend"))
print("AUTHOR_DONE")
