"""Build the `water_can` interaction contract for ANY supported generator.

One contract (docs/INTERACTION_CONTRACT_water_can.md), encoded through whichever
generator's own constraint classes are asked for, so an A/B compares generators
rather than two different requests. Nothing is hand-written JSON.

The hand target is DERIVED from the can's measured markers, not guessed: given a
spout position S over the bed and a pour tilt about the handle-bar axis, the
wrist transform is W = T(S) . R(bar, theta)^-1 . A^-1 where A is the grip anchor.

  python3 tools/rvmotion/build_water_contract.py \
      --generator {ardy,kimodo} --src <checkout> --out <constraints.json> \
      [--python <interpreter>]
"""
import argparse
import json
import math
import os
import sys

import numpy as np

CAN_META = "art/animation/ardy_pilot/proxy/watering_can_proxy.json"
# The contract is expressed RELATIVE TO THE BODY, then converted to each
# generator's own scale. Stated in absolute metres it is not the same request:
# ARDY Core27 has a 0.528 m arm and SOMA30 a 0.559 m arm on differently sized
# skeletons, so a fixed world-space spout target is reachable for one and
# impossible for the other -- which would decide the A/B on skeleton proportions
# rather than on generator quality. Fractions are taken against the SHIPPING
# character's hip height, so the numbers still mean what the game means.
CHARACTER_HIP_H = 0.9502          # rig thigh-head height, metres
SOIL_H = 0.22
DURATION_S = 2.4

# The contract is defined in SECONDS and converted per generator. ARDY Core runs
# at 20 fps and Kimodo-SOMA at 30; hard-coding frame indices would silently hand
# the two generators different requests and make the A/B meaningless.
GEN_FPS = {"ardy": 20, "kimodo": 30}
WINDOWS_S = {"settle": (0.00, 0.40),          # both feet planted
             "lead_released": (0.45, 0.95),   # transition deliberately unprescribed
             "lead_landed": (1.00, 2.40),     # stagger landed, stays put
             "pour": (1.10, 1.80),            # spout over the bed
             "carry_end": (2.20, 2.40)}
LEAD_ADVANCE_M = 0.28
BAND = (0.15, 0.30)
SPOUT_TARGET = 0.22           # the documented MIDPOINT, which is what we ask for
# Distance from the PELVIS (after the step) to the spout, not from the world
# origin. Measuring from the origin put the bed 0.36 m ahead of the start, of
# which the 0.26 m step consumed most -- so the "reach" collapsed to a hand at hip
# height 25 cm forward, which reads as standing with a can rather than watering.
REACH_AHEAD_OF_PELVIS = 0.40
# A pour is not reached by hinging the trunk alone. Letting the pelvis drop a
# little -- knee flexion, the way a person actually lowers a can -- supplies the
# last few centimetres far more naturally, and changes the answer a lot: the
# earlier "54 deg of trunk lean" figure assumed the shoulder could only be
# lowered by bowing.
MAX_PELVIS_DROP = 0.10        # character units, scaled per skeleton
# Kimodo's guidance is sparse conditioning (< 20 frames per constraint type) plus
# post-processing. Dense windows fight the prior instead of steering it.
MAX_KEYS_PER_SET = 6
# Lean is a FEASIBILITY ALLOWANCE, not a constraint on the generator.
#
# Capping it at 12 deg made the contract impossible for ARDY's Core27
# anthropometry -- shoulder at 1.422 m with a 0.528 m arm cannot drop a grip to
# 0.826 m however far it staggers -- while SOMA30's proportions reach it easily.
# Hard-capping would have silently handed the two generators different problems
# and decided the A/B on skeleton proportions. So the allowance is set to a
# normal forward-reach limit, the spine constraint is dropped from the request,
# and how much lean each generator actually USES becomes a measured quality:
# reaching the same target with less trunk hinge is the better result.
MAX_LEAN_DEG = 60.0
POUR_TILT_DEG = 44.0


def _rot(axis, rad):
    a = np.asarray(axis, dtype=float); a = a / np.linalg.norm(a)
    K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + math.sin(rad) * K + (1 - math.cos(rad)) * (K @ K)




def make_poser(sk, torch):
    """FK-based CCD posing, on the generator's own skeleton.

    The constraint format stores LOCAL ROTATIONS, so the contract has to be
    authored as a real pose, not as a list of target positions. This is the same
    approach build_water_constraints.py used for the original water clip, where it
    converged to under 2 mm.
    """
    BI = sk.bone_index
    parents = [int(x) for x in sk.joint_parents]
    J = len(sk.bone_order_names)

    def fk(local, root):
        gr, pj, _ = sk.fk(local[None], root[None])
        return gr[0], pj[0]

    def rot_world_at(local, gr, j, axis, rad):
        """Pre-multiply joint j's GLOBAL rotation, expressed in its local frame."""
        a = torch.tensor(axis, dtype=local.dtype)
        a = a / a.norm()
        K = torch.tensor([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]],
                         dtype=local.dtype)
        R = (torch.eye(3, dtype=local.dtype) + math.sin(rad) * K
             + (1 - math.cos(rad)) * (K @ K))
        p = parents[j]
        Rp = gr[p] if p >= 0 else torch.eye(3, dtype=local.dtype)
        local[j] = Rp.T @ R @ Rp @ local[j]

    def reach(local, root, chain, end_name, target, iters=60, step_cap_deg=12.0):
        tgt = torch.tensor(np.asarray(target, dtype=np.float64))
        e = BI[end_name]
        for _ in range(iters):
            for j in reversed(chain):
                gr, pj = fk(local, root)
                v1 = pj[e] - pj[j]
                v2 = tgt - pj[j]
                if v1.norm() < 1e-6 or v2.norm() < 1e-6:
                    continue
                ax = torch.cross(v1, v2)
                if ax.norm() < 1e-9:
                    continue
                ang = math.acos(float(torch.clamp((v1 @ v2) / (v1.norm() * v2.norm()), -1, 1)))
                rot_world_at(local, gr, j, tuple(ax.tolist()),
                             min(ang, math.radians(step_cap_deg)))
            gr, pj = fk(local, root)
            if float((pj[e] - tgt).norm()) < 2e-3:
                break
        gr, pj = fk(local, root)
        return float((pj[e] - tgt).norm())

    return BI, parents, J, fk, rot_world_at, reach


def rot_axis(axis, deg):
    a = np.asarray(axis, dtype=float)
    a = a / np.linalg.norm(a)
    th = math.radians(deg)
    K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + math.sin(th) * K + (1 - math.cos(th)) * (K @ K)


def wrist_from_spout(spout_world, tilt_deg, meta):
    """Invert the rigid can to get the wrist transform that puts the spout there.

    Two traps here, both hit on the first attempt:
      * `spout_tip` is already in CAN-local coordinates, so the grip-anchor basis
        must NOT be applied to it. Doing so rotated the tip's -0.30 m Y offset
        into X and threw the wrist 0.3 m sideways.
      * the constraint is on the WRIST, whose orientation is the anchor frame:
        R_wrist = R_can . A, while the can itself is only tilted about its own
        bar axis (can-local X).
    """
    # The can's markers are authored in Blender Z-up. The generators work in
    # Y-up, so both the tip offset and the anchor basis must be converted before
    # use -- otherwise the spout's 0.30 m FORWARD offset is read as 0.30 m DOWN
    # and the grip lands in front of its own spout.
    PZ = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]])   # Y-up -> Z-up
    A_z = np.array(meta["grip_anchor_basis_rows"], dtype=float)[:3, :3]
    A = PZ.T @ A_z @ PZ
    tip_local = PZ.T @ np.array(meta["markers"]["spout_tip"], dtype=float)
    R_can = rot_axis([1.0, 0.0, 0.0], tilt_deg)          # tilt about the bar
    grip_world = np.asarray(spout_world, dtype=float) - R_can @ tip_local
    return grip_world, R_can @ A


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--generator", required=True, choices=["ardy", "kimodo"])
    ap.add_argument("--src", required=True, help="generator checkout root")
    ap.add_argument("--out", required=True)
    ap.add_argument("--preview-npz", default=None,
                    help="also write the AUTHORED contract motion as a generator-format "
                         "npz, so the contract itself can be retargeted and looked at "
                         "before any generation is paid for")
    ap.add_argument("--seed-npz", default=None,
                    help="clip to take the neutral standing pose from")
    a = ap.parse_args()
    sys.path.insert(0, a.src)
    FPS = GEN_FPS[a.generator]
    N_FRAMES = int(round(DURATION_S * FPS))
    def win(name):
        t0, t1 = WINDOWS_S[name]
        return list(range(int(round(t0 * FPS)), min(N_FRAMES, int(round(t1 * FPS)) + 1)))

    def sparse(frames, k=MAX_KEYS_PER_SET):
        """Keyframes, not windows.

        Kimodo asks for fewer than 20 constrained frames per type plus
        post-processing; the earlier build handed it 72 rear-foot frames, which
        pins the prior rather than steering it and leaves the model no room to
        produce a natural transition. Endpoints are always kept so an interval
        still reads as an interval."""
        if len(frames) <= k:
            return list(frames)
        idx = np.linspace(0, len(frames) - 1, k)
        return sorted({frames[int(round(i))] for i in idx})
    SETTLE = sparse(win("settle"), 3)
    LEAD_LANDED = sparse(win("lead_landed"), 4)
    POUR = sparse(win("pour"), 5)
    SUPPORT = sparse(list(range(N_FRAMES)), 6)      # rear foot: sparse, not every frame
    CARRY = sparse(win("carry_end"), 2) + SETTLE
    print("  %d fps -> %d frames for %.1f s; pour frames %d-%d"
          % (FPS, N_FRAMES, DURATION_S, POUR[0], POUR[-1]))

    import torch
    if a.generator == "ardy":
        from ardy.skeleton.registry import build_skeleton
        from ardy.constraints import (RightHandConstraintSet, LeftFootConstraintSet,
                                      RightFootConstraintSet, EndEffectorConstraintSet,
                                      save_constraints_lst)
        NJ = 27
    else:
        from kimodo.skeleton.registry import build_skeleton
        from kimodo.constraints import (RightHandConstraintSet, LeftFootConstraintSet,
                                        RightFootConstraintSet, EndEffectorConstraintSet,
                                        save_constraints_lst)
        NJ = int(os.environ.get("RV_KIMODO_JOINTS", "77"))
    sk = build_skeleton(NJ)

    class HipsConstraintSet(EndEffectorConstraintSet):
        """Pelvis target. Both libraries treat "Hips" as a base end-effector name,
        so this rides the same machinery as the hand and foot sets."""
        name = "end-effector"
        def __init__(self, *args, **kw):
            super().__init__(*args, joint_names=["Hips"], **kw)
    BI = sk.bone_index
    names = list(sk.bone_order_names)
    print("%s skeleton: %d joints, up-axis assumed Y (generator native)"
          % (a.generator, len(names)))
    for req in ("Hips", "RightHand", "LeftFoot", "RightFoot"):
        assert req in BI, "skeleton lacks %s -- adapter assumption is wrong" % req

    # --- neutral standing pose from the generator's own rest -----------------
    ident = torch.eye(3).repeat(1, len(names), 1, 1)
    _, rest_pj, _ = sk.fk(ident, torch.zeros(1, 3))
    rest = rest_pj[0].numpy()                        # Y-up
    # Ground on the LOWEST foot point, not the ankle. Using the ankle joint put
    # the toes 7 cm underground, which is exactly the toe-clipping seen on screen.
    ground_js = [BI[n] for n in ("LeftFoot", "RightFoot", "LeftToeBase", "RightToeBase")
                 if n in BI]
    foot_y = min(rest[j, 1] for j in ground_js)
    rest = rest - np.array([0.0, foot_y, 0.0])

    meta = json.load(open(CAN_META))
    up = np.array([0.0, 1.0, 0.0])                   # generator-native Y-up
    hip_h = float(rest[BI["Hips"]][1])
    S = hip_h / CHARACTER_HIP_H                      # body-scale factor
    soil = SOIL_H * S
    band = (BAND[0] * S, BAND[1] * S)
    lead_adv = LEAD_ADVANCE_M * S
    standoff = REACH_AHEAD_OF_PELVIS * S
    print("  body scale %.3f (hip %.3f m vs character %.3f m): bed %.3f, band %.3f-%.3f, "
          "stagger %.3f" % (S, hip_h, CHARACTER_HIP_H, soil, band[0], band[1], lead_adv))


    FWD = np.array([0.0, 0.0, 1.0])   # generators seed heading 0 as "facing +Z"
    # hand: derived from the spout target through the rigid can
    # Solve for the DEEPEST point of the documented band the body can actually
    # reach, instead of picking a height and then forcing it. The shoulder is
    # credited with the step and the modest lean the contract permits -- nothing
    # more. If no point in the band is reachable, that is the finding, and the
    # contract says so rather than asking for a crouch.
    sh0 = rest[BI["RightArm"]]
    arm_len = (np.linalg.norm(rest[BI["RightForeArm"]] - sh0)
               + np.linalg.norm(rest[BI["RightHand"]] - rest[BI["RightForeArm"]]))
    # ARDY calls it "Neck"; SOMA30 calls it "Neck1". Resolve rather than assume --
    # the two generators genuinely disagree on several joint names.
    neck = next((n for n in ("Neck", "Neck1", "Neck2") if n in BI), None)
    assert neck, "no neck joint found in %s" % a.generator
    trunk = float(np.linalg.norm(rest[BI[neck]] - rest[BI["Hips"]]))

    # Ask for the DOCUMENTED target first. The previous version searched from the
    # shallowest end of the band downward and broke on the first feasible point,
    # so it always returned 0.30 -- the easiest point -- while the contract says
    # 0.22. Escalation away from the target is now explicit and reported.
    drop_max = MAX_PELVIS_DROP * S
    def solve(above):
        # spout sits ahead of where the PELVIS ends up, not ahead of the origin
        sp = np.array([0.0, soil + above, 0.0]) + FWD * (lead_adv * 0.5 + standoff)
        g, Rw = wrist_from_spout(sp, POUR_TILT_DEG, meta)
        g[0] = sh0[0] * 0.55
        cheapest = None
        for lean_d in np.arange(0.0, MAX_LEAN_DEG + 1e-9, 1.0):
            lean = math.radians(float(lean_d))
            for drop in np.arange(0.0, drop_max + 1e-9, 0.01 * S):
                sh_try = (sh0 + FWD * (lead_adv * 0.5 + trunk * math.sin(lean))
                          - np.array([0.0, trunk * (1 - math.cos(lean)) + drop, 0.0]))
                if np.linalg.norm(g - sh_try) <= arm_len * 0.98:
                    cand = (float(lean_d), float(drop), sp, g, Rw, sh_try)
                    if cheapest is None or lean_d < cheapest[0]:
                        cheapest = cand
                    break
            if cheapest:
                break
        return cheapest
    target_above = SPOUT_TARGET * S
    sol = solve(target_above)
    SPOUT_SOLVED = target_above
    escalated = False
    if sol is None:
        for above in np.arange(target_above, band[1] + 1e-9, 0.005 * S):
            sol = solve(above)
            if sol:
                SPOUT_SOLVED, escalated = float(above), True
                break
    assert sol is not None, (
        "not even the shallowest band point %.3f m is reachable with %.0f deg lean "
        "and %.3f m pelvis drop -- the CONTRACT is impossible for this body"
        % (band[1], MAX_LEAN_DEG, drop_max))
    LEAN_NEEDED, DROP_NEEDED, spout, grip, R_wrist, sh_eff = sol
    if escalated:
        print("  !! documented target %.3f m NOT reachable; escalated to %.3f m "
              "(%.3f in character units) -- reported, not silently substituted"
              % (target_above, SPOUT_SOLVED, SPOUT_SOLVED / S))
    else:
        print("  documented target %.3f m above the bed is reachable" % target_above)
    print("  needs %.0f deg trunk lean + %.3f m pelvis drop (knee flexion)"
          % (LEAN_NEEDED, DROP_NEEDED))

    # ---- author a real POSE per constrained frame -------------------------
    # The saved format keeps LOCAL ROTATIONS and rebuilds positions by FK, so a
    # pose array of target positions with identity rotations serialises to "rest
    # pose, translated" -- which is precisely what made the first A/B contract
    # contain no step. Every constrained frame is now solved with IK.
    BI2, parents, JN_, fk, rot_world_at, reach = make_poser(sk, torch)

    t0 = WINDOWS_S["lead_released"][0]
    t1 = WINDOWS_S["lead_landed"][0]
    f0, f1 = int(round(t0 * FPS)), int(round(t1 * FPS))
    w = np.clip((np.arange(N_FRAMES) - f0) / max(1, (f1 - f0)), 0.0, 1.0)
    w = w * w * (3 - 2 * w)
    root_fwd = w * (lead_adv * 0.5)
    root_dn = w * DROP_NEEDED

    lead_start = rest[BI["LeftFoot"]].copy()
    lead_end = lead_start + FWD * lead_adv
    rear_fixed = rest[BI["RightFoot"]].copy()

    LEG = {"Left": [BI["LeftUpLeg"], BI["LeftLeg"]] if "LeftUpLeg" in BI
                   else [BI["LeftLeg"], BI["LeftShin"]],
           "Right": [BI["RightUpLeg"], BI["RightLeg"]] if "RightUpLeg" in BI
                    else [BI["RightLeg"], BI["RightShin"]]}
    ARM = [BI["RightShoulder"], BI["RightArm"], BI["RightForeArm"]]
    HIP_L = "LeftUpLeg" if "LeftUpLeg" in BI else "LeftLeg"
    KNEE_L = "LeftLeg" if "LeftUpLeg" in BI else "LeftShin"
    HIP_R = "RightUpLeg" if "RightUpLeg" in BI else "RightLeg"
    KNEE_R = "RightLeg" if "RightUpLeg" in BI else "RightShin"
    PW_EASE = max(3, int(round(0.30 * FPS)))

    def pw_lean(fr):
        """Lean follows the pour: full while pouring, partial while carrying."""
        if POUR[0] - PW_EASE <= fr <= POUR[-1] + PW_EASE:
            if fr < POUR[0]:
                t = (fr - (POUR[0] - PW_EASE)) / float(PW_EASE)
            elif fr > POUR[-1]:
                t = 1.0 - (fr - POUR[-1]) / float(PW_EASE)
            else:
                t = 1.0
            t = max(0.0, min(1.0, t))
            return t * t * (3 - 2 * t)
        return 0.0
    SWING_A = int(round(WINDOWS_S["lead_released"][0] * FPS))
    SWING_B = LEAD_LANDED[0]
    STEP_LIFT = 0.06 * S
    KNEE_MIN_OFF = 0.03 * S

    # For the preview, author EVERY frame so the contract can be watched as motion.
    # Constraints still use only the sparse keyframes below.
    all_frames = (list(range(N_FRAMES)) if a.preview_npz
                  else sorted(set(SETTLE) | set(LEAD_LANDED) | set(POUR) | set(SUPPORT)
                              | set(sparse(win("pour"), 3))))
    poses = np.repeat(rest[None], N_FRAMES, axis=0)
    rots = np.repeat(np.eye(3)[None, None], N_FRAMES, axis=0).repeat(len(names), axis=1)
    locals_all = np.repeat(np.eye(3)[None, None], N_FRAMES, axis=0).repeat(len(names), axis=1)
    roots_all = np.repeat(rest[BI["Hips"]][None], N_FRAMES, axis=0)
    worst = {"lead": 0.0, "rear": 0.0, "hand": 0.0}
    swing_worst = [0.0]
    KEYSET = set(SETTLE) | set(LEAD_LANDED) | set(POUR) | set(SUPPORT) | set(sparse(win("pour"), 3))

    prev_local = None
    for f in all_frames:
        # SEED FROM THE PREVIOUS FRAME. Solving each frame from identity lets CCD
        # land in a different valid branch every frame, which is what makes the
        # arm and leg "teleport": the pose is right at each keyframe and
        # discontinuous between them.
        local = (prev_local.clone() if prev_local is not None
                 else torch.eye(3).repeat(len(names), 1, 1).double())
        root = torch.tensor(np.array([0.0, rest[BI["Hips"]][1] - root_dn[f],
                                      root_fwd[f]]))
        # feet: absolute ground targets, so the body advances OVER planted feet
        # The lead foot must SWING. Switching its target between two ground spots
        # teleports it the full 0.26 m stagger in one frame -- measured as a
        # 0.265 m single-frame jump, ~7000x the median.
        if f <= SWING_A:
            lt = lead_start.copy()
        elif f >= SWING_B:
            lt = lead_end.copy()
        else:
            u = (f - SWING_A) / float(SWING_B - SWING_A)
            e = u * u * (3 - 2 * u)
            lt = lead_start * (1 - e) + lead_end * e
            # Lift profile with zero VALUE and zero SLOPE at both ends. sin(pi*u)
            # is zero at the ends but its slope is not, so the foot's vertical
            # velocity jumped from 0 to full in a single frame at lift-off -- which
            # showed up as a 0.12 m/frame^2 knee spike exactly at the swing onset.
            lt[1] += STEP_LIFT * 0.5 * (1.0 - math.cos(2.0 * math.pi * u))
        # Only the CONSTRAINED keyframes go into the contract, so only they are
        # asserted. Swing frames exist for the preview and are allowed a looser
        # residual -- reported separately rather than blocking the build.
        key = f in KEYSET
        e_l = reach(local, root, LEG["Left"], "LeftFoot", lt)
        e_r = reach(local, root, LEG["Right"], "RightFoot", rear_fixed)
        if key:
            worst["lead"] = max(worst["lead"], e_l)
            worst["rear"] = max(worst["rear"], e_r)
        else:
            swing_worst[0] = max(swing_worst[0], e_l, e_r)
        in_pour = (POUR[0] <= f <= POUR[-1]) if a.preview_npz else (f in POUR)
        # OUTSIDE the pour the arm must be posed too, or it stays in the skeleton's
        # REST pose -- and ARDY's rest is a T-pose, so the preview showed the can
        # carried out at chest height. The constraint sets ignore unnamed joints,
        # but the preview is what a human judges the contract by, so it has to show
        # a real carry.
        carry = rest[BI["RightHand"]].copy()
        carry[0] = rest[BI["RightArm"]][0] * 0.92          # in beside the hip
        carry[1] = rest[BI["Hips"]][1] * 0.92              # hanging, near hip height
        carry[2] = root_fwd[f] + 0.02
        # Trunk lean, ramped with the same weight as the pelvis drop. The solver
        # says this pose needs it; without authoring it the preview stands bolt
        # upright and the reach comes entirely from the shoulder, which is both
        # unnatural and not what the feasibility check assumed.
        # Lean is an ABSOLUTE pose, applied to a reset spine.
        #
        # Seeding each frame from the previous one (which is what removed the
        # teleports) means any INCREMENTAL rotation compounds frame over frame:
        # 32 degrees added 48 times folded the character double. Reset the spine
        # first, then apply the absolute angle for this frame.
        spine = [BI[n] for n in ("Spine", "Spine1", "Spine2", "Spine3")
                 if n in BI] or [BI[n] for n in ("Spine1", "Spine2", "Chest") if n in BI]
        for sj in spine:
            local[sj] = torch.eye(3, dtype=local.dtype)
        lean_w = w[f] * (0.35 + 0.65 * pw_lean(f))
        if lean_w > 1e-3 and LEAN_NEEDED > 0.5:
            per = math.radians(LEAN_NEEDED * lean_w) / max(1, len(spine))
            for sj in spine:
                gr, _ = fk(local, root)
                rot_world_at(local, gr, sj, (1.0, 0.0, 0.0), per)
        # Blend carry -> pour -> carry with a smooth weight. A binary switch at the
        # window edge is a teleport no matter how good each end pose is.
        pw = 0.0
        if POUR[0] - PW_EASE <= f <= POUR[-1] + PW_EASE:
            if f < POUR[0]:
                t_ = (f - (POUR[0] - PW_EASE)) / float(PW_EASE)
            elif f > POUR[-1]:
                t_ = 1.0 - (f - POUR[-1]) / float(PW_EASE)
            else:
                t_ = 1.0
            pw = max(0.0, min(1.0, t_))
            pw = pw * pw * (3 - 2 * pw)
        hand_t = carry * (1.0 - pw) + np.asarray(grip) * pw
        err_h = reach(local, root, ARM, "RightHand", hand_t)
        if pw > 0.99 and key:
            worst["hand"] = max(worst["hand"], err_h)

        # Wrist orientation, RAMPED with the same pour weight. Setting it only
        # inside the window snapped the can upright-to-tipped in one frame.
        if pw > 1e-3:
            gr, _ = fk(local, root)
            Rw = np.asarray(R_wrist, dtype=float)
            ang = math.acos(max(-1.0, min(1.0, (np.trace(Rw) - 1.0) / 2.0)))
            if ang > 1e-6:
                ax = np.array([Rw[2, 1] - Rw[1, 2], Rw[0, 2] - Rw[2, 0],
                               Rw[1, 0] - Rw[0, 1]]) / (2.0 * math.sin(ang))
                Rb = rot_axis(ax, math.degrees(ang * pw))
            else:
                Rb = np.eye(3)
            p_ = parents[BI["RightHand"]]
            local[BI["RightHand"]] = gr[p_].T @ torch.tensor(Rb)

        # Feet flat, knees forward. The CCD only controls the ANKLE POSITION, so
        # the foot was free to rotate about it (toes driving through the ground)
        # and the knee was free to sit anywhere on its circle (legs folding
        # inward). Both are fixed after the position solve.
        for side_p, foot_n, knee_n, hip_n in (
                ("L", "LeftFoot", KNEE_L, HIP_L), ("R", "RightFoot", KNEE_R, HIP_R)):
            gr, pj = fk(local, root)
            # knee toward +Z (the way the body faces)
            hipp, kneep, anklep = pj[BI[hip_n]], pj[BI[knee_n]], pj[BI[foot_n]]
            limb = (anklep - hipp)
            if limb.norm() > 1e-6:
                u = limb / limb.norm()
                off = (kneep - hipp) - u * torch.dot(kneep - hipp, u)
                want = torch.tensor(FWD, dtype=off.dtype)
                want = want - u * torch.dot(want, u)
                # Only correct a knee whose direction is well defined. Near a
                # straight leg the offset is noise, and "correcting" it swings the
                # knee across its circle frame to frame -- a 0.16 m pop.
                # Ramp the correction with how well-defined the knee direction is.
                # A hard threshold means the correction switches on the instant the
                # leg bends, snapping the knee across its circle -- measured as a
                # 0.12 m/frame^2 acceleration spike at the first swing frame.
                if want.norm() > 1e-4 and off.norm() > 1e-5:
                    q = float((off.norm() - KNEE_MIN_OFF * 0.4)
                              / max(1e-6, KNEE_MIN_OFF * 0.6))
                    q = max(0.0, min(1.0, q))
                    q = q * q * (3 - 2 * q)
                    a_ = off / off.norm(); b_ = want / want.norm()
                    ang = math.acos(float(torch.clamp(torch.dot(a_, b_), -1, 1)))
                    if q > 1e-3 and ang > math.radians(1):
                        sgn = 1.0 if float(torch.dot(torch.cross(a_, b_), u)) > 0 else -1.0
                        rot_world_at(local, gr, BI[hip_n], tuple(u.tolist()),
                                     sgn * ang * q)
            # sole flat: cancel the foot's own global rotation back to rest
            gr, _ = fk(local, root)
            p_ = parents[BI[foot_n]]
            local[BI[foot_n]] = gr[p_].T @ torch.eye(3, dtype=local.dtype)

        prev_local = local.clone()
        locals_all[f] = local.numpy()
        roots_all[f] = root.numpy()
        gr, pj = fk(local, root)
        poses[f] = pj.numpy()
        rots[f] = gr.numpy()

    print("  IK residuals on CONSTRAINED keys: lead %.4f m, rear %.4f m, hand %.4f m"
          % (worst["lead"], worst["rear"], worst["hand"]))
    if swing_worst[0]:
        print("  (swing/interpolated preview frames peak at %.4f m -- not constrained)"
              % swing_worst[0])
    assert max(worst.values()) < 0.02, "IK did not reach its targets: %s" % worst

    def mk(cls, frames):
        fi = torch.tensor(frames)
        return cls(sk, fi, torch.tensor(poses[frames]).float(),
                   torch.tensor(rots[frames]).float(), None)

    # Pelvis target at the pour: a sparse hips constraint carrying the lowering
    # that knee flexion supplies, so the model is not forced to find the height
    # by bowing. Without it the only lever the generator has is trunk hinge.
    HIPS = sparse(win("pour"), 3)
    # the pelvis key just confirms the trajectory the root already follows
    for f in HIPS:
        poses[f, BI["Hips"]] = (rest[BI["Hips"]] - np.array([0.0, root_dn[f], 0.0])
                                + FWD * root_fwd[f])

    sets = [
        mk(RightHandConstraintSet, POUR),        # spout over the bed
        mk(RightFootConstraintSet, SUPPORT),     # rear foot supports throughout
        mk(LeftFootConstraintSet, SETTLE),       # planted before the step
        mk(LeftFootConstraintSet, LEAD_LANDED),  # landed forward in a stagger
        mk(HipsConstraintSet, HIPS),             # pelvis lowered by knee flexion
    ]
    per_type = {type(x).__name__: len(x.frame_indices) for x in sets}
    print("  constrained frames per set: %s" % per_type)
    assert all(v < 20 for v in per_type.values()), \
        "a constraint type exceeds 20 keyframes; that is dense conditioning"
    if a.preview_npz:
        fcm = np.ones((N_FRAMES, 4), dtype=bool)
        lo, hi = int(round(WINDOWS_S["lead_released"][0] * FPS)), LEAD_LANDED[0]
        fcm[lo:hi, 0:2] = False          # lead foot airborne during the step
        np.savez(a.preview_npz, local_rot_mats=locals_all, global_rot_mats=rots,
                 posed_joints=poses, root_positions=roots_all,
                 smooth_root_pos=roots_all, foot_contacts=fcm,
                 global_root_heading=np.stack([np.ones(N_FRAMES), np.zeros(N_FRAMES)], 1),
                 fps=FPS, text=np.array("authored contract preview"))
        print("  preview written: %s (%d frames) -- this is the CONTRACT, not a "
              "generated clip" % (a.preview_npz, N_FRAMES))

    save_constraints_lst(a.out, sets)
    summary = {"generator": a.generator, "skeleton_joints": len(names),
               "fps": FPS, "frames": N_FRAMES, "duration_s": DURATION_S,
               "windows_seconds": WINDOWS_S,
               "windows_frames": {"settle": [SETTLE[0], SETTLE[-1]],
                                  "lead_landed": [LEAD_LANDED[0], LEAD_LANDED[-1]],
                                  "pour": [POUR[0], POUR[-1]]},
               "lead_advance_m_generator_units": round(lead_adv, 4),
               "body_scale_vs_character": round(S, 4),
               "spout_target_above_bed_m_generator_units": round(SPOUT_SOLVED, 4),
               "spout_target_above_bed_m_character_units": round(SPOUT_SOLVED / S, 4),
               "lead_advance_m_character_units": LEAD_ADVANCE_M,
               "documented_band_m": list(BAND),
               "lean_allowance_deg": MAX_LEAN_DEG,
               "min_lean_needed_deg": LEAN_NEEDED,
               "pour_tilt_deg": POUR_TILT_DEG,
               "constrained_frames_total": sum(len(s.frame_indices) for s in sets),
               "constrained_frames_per_set": per_type,
               "min_trunk_lean_deg": LEAN_NEEDED,
               "pelvis_drop_m": round(DROP_NEEDED, 4),
               "spout_target_documented_m": SPOUT_TARGET,
               "spout_target_escalated": bool(escalated),
               "note": "no compression to 1.2 s during the architectural comparison"}
    json.dump(summary, open(a.out.replace(".json", "_summary.json"), "w"), indent=2)
    print("  wrote %s (%d sets, %d constrained frames)"
          % (a.out, len(sets), summary["constrained_frames_total"]))


if __name__ == "__main__":
    main()
