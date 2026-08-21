"""Two scorecards, because they answer two different questions.

A single number would conflate them, and the conflation is not academic: the two
candidate generators ship different skeletons, and one of them (ARDY Core27) must
bow 46 degrees to reach a target the other reaches with none. That difference is
real and matters for production, but it is NOT a statement about which model
generates better motion.

  A. MORPHOLOGY-NORMALISED GENERATOR QUALITY
     Did the generator satisfy the contract IN ITS OWN BODY? Everything is
     expressed in body-relative units -- arm lengths, hip heights, degrees --
     and measured on the NATIVE output before any retargeting. Skeleton size
     cancels; what remains is how well the model obeyed sparse constraints and
     produced plausible motion.

  B. PRODUCTION RESULT
     What actually ships: the clip retargeted onto the Rigify character, holding
     the fixed-size shipping can, judged in absolute metres against the game's
     own contract. Anthropometry deliberately does NOT cancel here, because the
     player will see a character bowing at a flower bed.

  python3 tools/rvmotion/scorecard.py --native <base.rvm> --contract <summary.json> \
      [--production <validation.json>] --out <scorecard.json> --label NAME
"""
import argparse
import json
import math

import numpy as np


def morphology_scorecard(m, contract):
    """Contract satisfaction in the generator's own body."""
    J, POS = m.joints, m.positions
    hip = J.index("Hips")
    sh, wr = J.index("RightArm"), J.index("RightHand")
    fore = J.index("RightForeArm")
    neck = J.index("Neck") if "Neck" in J else J.index("Spine3")
    arm = float(np.linalg.norm(POS[0, fore] - POS[0, sh])
                + np.linalg.norm(POS[0, wr] - POS[0, fore]))
    hip_h = float(POS[0, hip, 2])
    pour = contract["windows_frames"]["pour"]
    pf = list(range(pour[0], min(pour[1] + 1, m.num_frames)))

    v = POS[:, neck] - POS[:, hip]
    lean = np.degrees(np.arctan2(np.linalg.norm(v[:, :2], axis=1), v[:, 2]))
    reach = np.linalg.norm(POS[:, wr] - POS[:, sh], axis=1) / arm
    hips_drop = (POS[0, hip, 2] - POS[:, hip, 2]) / hip_h

    ch = {n: i for i, n in enumerate(m.contact_channels)}
    lf, rf = J.index("LeftFoot"), J.index("RightFoot")
    lead = POS[:, lf, :2]
    advance = float(np.linalg.norm(lead[-1] - lead[0])) / hip_h
    rear_drift = float(np.abs(POS[:, rf, :2] - POS[0, rf, :2]).max()) / hip_h
    airborne = int((m.contacts.sum(axis=1) == 0).sum())

    return {
        "units": "body-relative (arm lengths, hip heights, degrees)",
        "arm_length_m": round(arm, 4), "hip_height_m": round(hip_h, 4),
        "trunk_lean_at_pour_deg": {"mean": round(float(lean[pf].mean()), 1),
                                   "max": round(float(lean.max()), 1)},
        "arm_extension_at_pour": {"mean": round(float(reach[pf].mean()), 3),
                                  "max": round(float(reach.max()), 3)},
        "pelvis_drop_hip_fraction": round(float(hips_drop.max()), 4),
        "lead_foot_advance_hip_fraction": round(advance, 4),
        "rear_foot_drift_hip_fraction": round(rear_drift, 4),
        "airborne_frames": [airborne, int(m.num_frames)],
        "gate_rear_foot_stayed": rear_drift < 0.10,
        "gate_lead_foot_stepped": advance > 0.15,
        "gate_arm_not_hyperextended": float(reach.max()) <= 1.0,
        "gate_no_flight": airborne <= max(1, int(0.05 * m.num_frames)),
    }


def production_scorecard(validation):
    """What ships: absolute metres, the real can, the game's own thresholds."""
    if not validation:
        return {"status": "not built yet"}
    ts = validation.get("task_space", {})
    sp = validation.get("spout", {})
    fc = validation.get("foot_contacts", {})
    col = validation.get("collisions", {})
    jl = validation.get("joint_limits", {})
    return {
        "units": "absolute metres on the shipping character with the fixed can",
        "spout_window_m": [sp.get("window_min_m"), sp.get("window_max_m")],
        "spout_in_band": sp.get("gate_in_band_for_whole_pour_window"),
        "forward_reach_ratio": ts.get("forward_reach_normalised", {}).get("range_ratio"),
        "spine_signed_shape_err_deg": [e.get("max_abs") for e in
                                       ts.get("spine_signed_pitch_per_frame_err_deg", [])],
        "step_events": ts.get("step_events"),
        "foot_skating_peak_cm_s": {k: v.get("peak_slide_cm_per_s")
                                   for k, v in (fc.get("per_foot") or {}).items()},
        "body_collisions": col.get("body_vert_hits_max"),
        "grip_region_contact": col.get("grip_region_vert_hits_max"),
        "joint_limits_ok": all(v for k, v in (jl or {}).items() if k.startswith("gate_")),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--native", required=True)
    ap.add_argument("--contract", required=True)
    ap.add_argument("--production", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--label", required=True)
    a = ap.parse_args()
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from rvmotion.canonical import RVMotion
    m = RVMotion.load(a.native)
    contract = json.load(open(a.contract))
    prod = json.load(open(a.production)) if a.production else None
    out = {"label": a.label,
           "contract": {k: contract.get(k) for k in
                        ("generator", "fps", "frames", "duration_s",
                         "constrained_frames_per_set", "min_trunk_lean_deg",
                         "pelvis_drop_m", "spout_target_documented_m",
                         "spout_target_escalated", "body_scale_vs_character")},
           "A_morphology_normalised": morphology_scorecard(m, contract),
           "B_production": production_scorecard(prod),
           "note": ("A answers 'did the model obey the contract in its own body'; "
                    "B answers 'what does the player see'. Reporting one number "
                    "would hide that ARDY's skeleton must bow where Kimodo's need not.")}
    json.dump(out, open(a.out, "w"), indent=2)
    print(json.dumps(out["A_morphology_normalised"], indent=2))
    print("wrote", a.out)


if __name__ == "__main__":
    main()
