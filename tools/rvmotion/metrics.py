"""Task-space metrics, corrected.

Every function here replaces an earlier measurement that was wrong in a way that
flattered the result. The failure mode was always the same: a quantity that is
cheap to compute stood in for the one that actually matters.

  unsigned pitch      -> signed sagittal pitch about the character's heading,
                         because |horizontal| cannot tell a forward curve from a
                         backward arch
  max-over-clip       -> per-frame comparison, because two clips can share a
                         maximum and disagree everywhere else
  foot vs pelvis      -> contact-event detection, because a stationary foot
                         appears to move whenever the pelvis hinges
  |shoulder->wrist|   -> that vector in CHEST-LOCAL space plus shoulder flexion,
                         because a constant length only says the elbow held its
                         configuration; the arm can still swing from the shoulder
"""
import math

import numpy as np


def heading_frame(hips_pos, chest_pos, heading_rad=None):
    """Right-handed (forward, left, up) basis for sagittal measurements.

    `forward` is the character's facing on the ground plane. Using the source's
    own heading channel when available avoids deriving facing from a leaning
    torso, which rotates as the character bends.
    """
    up = np.array([0.0, 0.0, 1.0])
    if heading_rad is not None:
        fwd = np.array([math.sin(heading_rad), -math.cos(heading_rad), 0.0])
    else:
        v = chest_pos - hips_pos
        v = np.array([v[0], v[1], 0.0])
        fwd = np.array([0.0, -1.0, 0.0]) if np.linalg.norm(v) < 1e-6 else v / np.linalg.norm(v)
    n = np.linalg.norm(fwd)
    fwd = fwd / n if n > 1e-9 else np.array([0.0, -1.0, 0.0])
    left = np.cross(up, fwd)
    return fwd, left / max(1e-9, np.linalg.norm(left)), up


def signed_sagittal_pitch(vec, fwd, up):
    """Signed pitch of a segment: +ve leans FORWARD, -ve leans back.

    atan2(|horizontal|, z) discards the sign entirely and reports a backward
    arch and a forward bend as the same number."""
    f = float(np.dot(vec, fwd))
    u = float(np.dot(vec, up))
    return math.degrees(math.atan2(f, u))


def spine_profile(points, fwd, up):
    """Signed pitch of every consecutive segment, one frame."""
    return [signed_sagittal_pitch(points[i + 1] - points[i], fwd, up)
            for i in range(len(points) - 1)]


def per_frame_error(rig_series, src_series):
    """Compare the SAME frames, and separate a constant offset from dynamics.

    Two skeletons calibrated from different rest poses (A-pose vs T-pose) carry a
    constant bias by construction. That bias is not a tracking failure, but it
    swamps a raw RMSE, so both are reported: `rmse` includes it and
    `rmse_debiased` is the part that actually reflects following the motion.
    Reporting only one of them would be misleading in one direction or the other.
    """
    a = np.asarray(rig_series, dtype=float)
    b = np.asarray(src_series, dtype=float)
    d = a - b
    bias = float(d.mean())
    dz = d - bias
    return {"rmse": float(np.sqrt((d ** 2).mean())),
            "max_abs": float(np.abs(d).max()),
            "bias": bias,
            "rmse_debiased": float(np.sqrt((dz ** 2).mean())),
            "max_abs_debiased": float(np.abs(dz).max())}


def arm_in_chest_frame(shoulder, wrist, chest_basis):
    """shoulder->wrist expressed in chest-local axes, plus shoulder flexion.

    chest_basis: 3x3 with columns (forward, left, up) of the chest.
    Flexion is measured in the sagittal plane from the chest's DOWN axis, so
    +90 deg means the arm is horizontal in front of the body."""
    v = np.asarray(wrist) - np.asarray(shoulder)
    local = chest_basis.T @ v
    f, u = float(local[0]), float(local[2])
    flexion = math.degrees(math.atan2(f, -u))
    return {"local": [float(x) for x in local],
            "length": float(np.linalg.norm(v)),
            "flexion_deg": flexion,
            "abduction_deg": math.degrees(math.asin(
                max(-1.0, min(1.0, float(local[1]) / max(1e-9, np.linalg.norm(v))))))}


def detect_steps(contacts, foot_ground_xy, min_air_frames=1, min_advance_m=0.05,
                 cyclic=False):
    """A step is an EVENT, not a displacement.

    release -> at least `min_air_frames` airborne -> new contact whose ground
    position has advanced at least `min_advance_m`. Measuring how far a foot
    moves relative to the pelvis detects no such thing: the foot sits still and
    the pelvis hinges over it, and the difference is reported as a step.
    """
    on = np.asarray(contacts).astype(bool)
    xy = np.asarray(foot_ground_xy, dtype=float)
    n0 = len(on)
    if cyclic:
        # A one-stride loop contains at most one landing per foot, and it may sit
        # across the wrap. Scanning the clip once finds zero events and reports a
        # normal walk as having no steps -- which is what the first version did.
        on = np.concatenate([on, on])
        xy = np.concatenate([xy, xy + (xy[-1] - xy[0])])
    steps, air = [], 0
    last_anchor = xy[0] if on[0] else None
    for f in range(1, len(on)):
        if on[f - 1] and not on[f]:
            last_anchor = xy[f - 1]
            air = 0
        elif not on[f]:
            air += 1
        elif not on[f - 1] and on[f]:
            if last_anchor is not None and air >= min_air_frames:
                adv = float(np.linalg.norm(xy[f] - last_anchor))
                if adv >= min_advance_m:
                    steps.append({"land_frame": int(f), "advance_m": round(adv, 4),
                                  "air_frames": int(air)})
            air = 0
    if cyclic:
        seen, uniq = set(), []
        for st in steps:
            k = st["land_frame"] % n0
            if k in seen:
                continue
            seen.add(k)
            st["land_frame"] = int(k)
            uniq.append(st)
        steps = uniq
    return {"count": len(steps), "steps": steps,
            "total_advance_m": round(sum(s["advance_m"] for s in steps), 4)}


def stability(positions_xy, contacts=None):
    """Total PATH travelled, not net displacement.

    A support foot that shuffles 20 cm back and forth and ends where it started
    scores ~0 on net displacement and looks perfectly planted to a gate that only
    measures endpoints. It is exactly what a viewer calls "wiggling". Path is the
    honest measure; the ratio of path to net says how much of the motion went
    nowhere.
    """
    p = np.asarray(positions_xy, dtype=float)
    steps = np.linalg.norm(np.diff(p, axis=0), axis=1)
    path = float(steps.sum())
    net = float(np.linalg.norm(p[-1] - p[0]))
    out = {"path_m": path, "net_m": net,
           "wander_ratio": round(path / max(net, 1e-6), 2),
           "peak_step_m": float(steps.max()) if len(steps) else 0.0}
    if contacts is not None:
        on = np.asarray(contacts).astype(bool)
        held = [steps[i] for i in range(len(steps)) if on[i] and on[i + 1]]
        out["path_while_planted_m"] = float(np.sum(held)) if held else 0.0
    return out


def target_error(achieved_xyz, target_xyz):
    """Did the pose actually reach the thing it was asked to reach?

    Range- and ratio-style metrics can look healthy while the end effector never
    goes near its target, because they compare the SHAPE of a trajectory rather
    than its destination.
    """
    a = np.asarray(achieved_xyz, dtype=float)
    t = np.asarray(target_xyz, dtype=float)
    d = np.linalg.norm(a - t, axis=-1)
    return {"mean_m": float(d.mean()), "max_m": float(d.max()), "min_m": float(d.min())}
