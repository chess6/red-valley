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
SPOUT_INSIDE_BED = 0.10
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
    ap.add_argument("--seed-npz", default=None,
                    help="clip to take the neutral standing pose from")
    a = ap.parse_args()
    sys.path.insert(0, a.src)
    FPS = GEN_FPS[a.generator]
    N_FRAMES = int(round(DURATION_S * FPS))
    def win(name):
        t0, t1 = WINDOWS_S[name]
        return list(range(int(round(t0 * FPS)), min(N_FRAMES, int(round(t1 * FPS)) + 1)))
    SETTLE = win("settle")
    LEAD_LANDED = win("lead_landed")
    POUR = win("pour")
    CARRY = SETTLE + win("carry_end")
    print("  %d fps -> %d frames for %.1f s; pour frames %d-%d"
          % (FPS, N_FRAMES, DURATION_S, POUR[0], POUR[-1]))

    import torch
    if a.generator == "ardy":
        from ardy.skeleton.registry import build_skeleton
        from ardy.constraints import (RightHandConstraintSet, LeftFootConstraintSet,
                                      RightFootConstraintSet, save_constraints_lst)
        NJ = 27
    else:
        from kimodo.skeleton.registry import build_skeleton
        from kimodo.constraints import (RightHandConstraintSet, LeftFootConstraintSet,
                                        RightFootConstraintSet, save_constraints_lst)
        NJ = int(os.environ.get("RV_KIMODO_JOINTS", "77"))
    sk = build_skeleton(NJ)
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
    foot_y = min(rest[BI["LeftFoot"], 1], rest[BI["RightFoot"], 1])
    rest = rest - np.array([0.0, foot_y, 0.0])       # soles on the ground

    meta = json.load(open(CAN_META))
    up = np.array([0.0, 1.0, 0.0])                   # generator-native Y-up
    hip_h = float(rest[BI["Hips"]][1])
    S = hip_h / CHARACTER_HIP_H                      # body-scale factor
    soil = SOIL_H * S
    band = (BAND[0] * S, BAND[1] * S)
    lead_adv = LEAD_ADVANCE_M * S
    standoff = SPOUT_INSIDE_BED * S
    print("  body scale %.3f (hip %.3f m vs character %.3f m): bed %.3f, band %.3f-%.3f, "
          "stagger %.3f" % (S, hip_h, CHARACTER_HIP_H, soil, band[0], band[1], lead_adv))

    poses = np.repeat(rest[None], N_FRAMES, axis=0)
    # forward is +Z: generate.py seeds first_heading_angle=0 as "facing +Z"
    FWD = np.array([0.0, 0.0, 1.0])
    lead_start = rest[BI["LeftFoot"]].copy()
    lead_end = lead_start + FWD * lead_adv
    for f in LEAD_LANDED:
        poses[f, BI["LeftFoot"]] = lead_end
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
    # Search lean as well as band depth. Assuming maximum lean is best is wrong:
    # past a point the trunk carries the shoulder FORWARD of the grip and the
    # distance grows again. The reported lean is the smallest that reaches the
    # deepest attainable point -- less trunk hinge for the same target is better.
    best = None
    for above in np.arange(band[1], band[0] - 1e-9, -0.005 * S):
        sp = np.array([0.0, soil + above, 0.0]) + FWD * (lead_adv + standoff)
        g, Rw = wrist_from_spout(sp, POUR_TILT_DEG, meta)
        g[0] = sh0[0] * 0.55
        for lean_d in np.arange(0.0, MAX_LEAN_DEG + 1e-9, 1.0):
            lean = math.radians(float(lean_d))
            sh_try = (sh0 + FWD * (lead_adv * 0.5 + trunk * math.sin(lean))
                      - np.array([0.0, trunk * (1 - math.cos(lean)), 0.0]))
            if np.linalg.norm(g - sh_try) <= arm_len * 0.98:
                best = (float(above), sp, g, Rw, float(lean_d), sh_try)
                break
        if best:
            break
    assert best is not None, (
        "no point in the body-scaled %.3f-%.3f m band is reachable with a %.0f deg "
        "lean and a %.3f m stagger -- the CONTRACT is impossible for this body, "
        "which is a finding, not something to force"
        % (band[0], band[1], MAX_LEAN_DEG, lead_adv))
    SPOUT_SOLVED, spout, grip, R_wrist, LEAN_NEEDED, sh_eff = best
    print("  minimum trunk lean that reaches it: %.0f deg (allowance %.0f)"
          % (LEAN_NEEDED, MAX_LEAN_DEG))
    print("  deepest reachable spout: %.3f m above the bed = %.3f in character "
          "units (band %.2f-%.2f character)"
          % (SPOUT_SOLVED, SPOUT_SOLVED / S, BAND[0], BAND[1]))
    _, R_carry = wrist_from_spout(rest[BI["RightHand"]]
                                  + np.array(meta["markers"]["spout_tip"]), 0.0, meta)
    for f in POUR:
        poses[f, BI["RightHand"]] = grip
    sh, arm = sh0, arm_len
    # The reach is supposed to come from the STEP and the lean, so judge the
    # target against the shoulder where it will actually be, not against a
    # T-pose shoulder standing still.
    need = float(np.linalg.norm(grip - sh_eff))
    print("  spout target %s -> wrist %s" % (np.round(spout, 3), np.round(grip, 3)))
    print("  wrist is %.3f m from the stepped shoulder; arm is %.3f m (%.0f%% extension)"
          % (need, arm, 100.0 * need / arm))
    assert need <= arm * 0.98, (
        "the contract asks for %.0f%% arm extension even after the step; an "
        "unreachable constraint would just force a crouch or a stretched arm. "
        "Move the spout target closer or lengthen the stagger." % (100.0 * need / arm))

    rots = np.repeat(np.eye(3)[None, None], N_FRAMES, axis=1).repeat(len(names), axis=1)
    rots = np.repeat(np.eye(3)[None][None], N_FRAMES, axis=0).repeat(len(names), axis=1)
    for f in POUR:
        rots[f, BI["RightHand"]] = R_wrist
    for f in CARRY:
        rots[f, BI["RightHand"]] = R_carry

    def mk(cls, frames):
        fi = torch.tensor(frames)
        return cls(sk, fi, torch.tensor(poses[frames]).float(),
                   torch.tensor(rots[frames]).float(), None)

    sets = [
        mk(RightHandConstraintSet, POUR),                       # pour only: sparse
        mk(RightFootConstraintSet, list(range(N_FRAMES))),      # rear foot supports
        mk(LeftFootConstraintSet, SETTLE),                      # planted at the start
        mk(LeftFootConstraintSet, LEAD_LANDED),                 # landed forward
    ]
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
               "note": "no compression to 1.2 s during the architectural comparison"}
    json.dump(summary, open(a.out.replace(".json", "_summary.json"), "w"), indent=2)
    print("  wrote %s (%d sets, %d constrained frames)"
          % (a.out, len(sets), summary["constrained_frames_total"]))


if __name__ == "__main__":
    main()
