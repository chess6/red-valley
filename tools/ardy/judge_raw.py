"""Judge raw ARDY motion BEFORE retargeting, against the water_can target.

Deep crouches are rejected here so no rental time is spent retargeting them.

  python judge_raw.py <clip.npz> [clip.npz ...]

Target (approved):
  * mostly upright: forward lean 10-20 deg, hip drop < 0.10 m
  * both feet planted throughout
  * right hand down and forward, held away from the thigh
  * hand height 0.55-0.85 m, which puts the spout 0.15-0.30 m over a 0.22 m bed
    (the proxy can's grip->spout tip is 0.323 m)
"""
import json, sys, os
import numpy as np

MAP = json.load(open(os.path.join(os.path.dirname(__file__), "..", "..",
                "art", "animation", "ardy_pilot", "retarget_map.json")))
NAMES = MAP["source_joint_order"]
SI = {n: i for i, n in enumerate(NAMES)}
RIG_H = 1.9005
SOIL = 0.22

HIP_DROP_MAX   = 0.10          # deeper than this is a crouch, not a lean
LEAN_MIN, LEAN_MAX = 8.0, 24.0 # deg of trunk forward lean at the pour
HAND_LO, HAND_HI = 0.55, 0.85  # m, puts the spout 0.15-0.30 m over the bed
HAND_OUT_MIN   = 0.16          # m lateral clearance hand-to-hip: can clears the thigh
FWD_MIN        = 0.10          # m the hand must be forward of the hips

def judge(path):
    d = np.load(path, allow_pickle=True)
    J = d["posed_joints"]; fc = d["foot_contacts"]; fps = int(d["fps"])
    s = RIG_H / float(J[:, SI["Head"], 1].max() - J[:, SI["RightToeBase"], 1].min())
    P = J * s
    hips_y = P[:, SI["Hips"], 1]
    hip_drop = float(hips_y.max() - hips_y.min())
    # trunk lean: Hips->Spine3, +ve forward (+Z is forward in ARDY)
    v = P[:, SI["Spine3"]] - P[:, SI["Hips"]]
    lean = np.degrees(np.arctan2(v[:, 2], v[:, 1]))
    rh = P[:, SI["RightHand"]]
    hip_r = P[:, SI["RightUpLeg"]]
    lateral = np.abs(rh[:, 0] - hip_r[:, 0])
    forward = rh[:, 2] - P[:, SI["Hips"], 2]
    L = fc[:, 0] | fc[:, 1]; R = fc[:, 2] | fc[:, 3]
    planted = float((L & R).mean())
    # the pour frame = lowest right hand while still in the target band
    k = int(np.argmin(np.abs(rh[:, 1] - (HAND_LO + HAND_HI) / 2)))
    res = {
        "clip": os.path.basename(path),
        "hip_drop_m": round(hip_drop, 4),
        "lean_at_pour_deg": round(float(lean[k]), 2),
        "hand_height_min_m": round(float(rh[:, 1].min()), 4),
        "hand_height_at_pour_m": round(float(rh[k, 1]), 4),
        "hand_lateral_from_hip_m": round(float(lateral[k]), 4),
        "hand_forward_of_hips_m": round(float(forward[k]), 4),
        "both_feet_planted_frac": round(planted, 3),
        "pour_frame": k,
    }
    fails = []
    if hip_drop >= HIP_DROP_MAX: fails.append("hip drop %.3f m -- crouch, not a lean" % hip_drop)
    if not (LEAN_MIN <= res["lean_at_pour_deg"] <= LEAN_MAX):
        fails.append("trunk lean %.1f deg outside %.0f-%.0f" % (res["lean_at_pour_deg"], LEAN_MIN, LEAN_MAX))
    if not (HAND_LO <= res["hand_height_at_pour_m"] <= HAND_HI):
        fails.append("hand %.2f m outside %.2f-%.2f (spout would miss 0.15-0.30 m over soil)"
                     % (res["hand_height_at_pour_m"], HAND_LO, HAND_HI))
    if res["hand_lateral_from_hip_m"] < HAND_OUT_MIN:
        fails.append("hand only %.3f m from the hip -- can would foul the thigh" % res["hand_lateral_from_hip_m"])
    if res["hand_forward_of_hips_m"] < FWD_MIN:
        fails.append("hand only %.3f m forward of hips -- not reaching out" % res["hand_forward_of_hips_m"])
    if planted < 0.85: fails.append("feet planted only %.0f%% of frames" % (100*planted))
    res["FAILURES"] = fails
    res["VERDICT"] = "PASS" if not fails else "FAIL"
    return res

if __name__ == "__main__":
    out = [judge(p) for p in sys.argv[1:]]
    print(json.dumps(out, indent=2))
    ok = [r for r in out if r["VERDICT"] == "PASS"]
    print("\n%d/%d pass" % (len(ok), len(out)))
    for r in out:
        print("  %-16s %-5s hip_drop %.3f lean %+6.1f hand_z %.2f lat %.3f fwd %+.3f"
              % (r["clip"], r["VERDICT"], r["hip_drop_m"], r["lean_at_pour_deg"],
                 r["hand_height_at_pour_m"], r["hand_lateral_from_hip_m"], r["hand_forward_of_hips_m"]))
