"""Adapter: ARDY CoreSkeleton27 -> Red Valley canonical motion (RVM/1).

The ONLY place that knows anything about ARDY. Everything source-specific --
the basis change, the joint map, the rest offsets, the contact channel order --
is emitted into ardy_core27.json so a second generator (Kimodo, HY-Motion) gets
its own adapter file rather than edits to the retargeter.

Basis change, stated once and applied consistently:

    ARDY is Y-up with +Z forward; Red Valley (Blender/Godot import) is Z-up
    with -Y forward.

        P = [[1, 0,  0],
             [0, 0, -1],
             [0, 1,  0]]

    positions  v' = P v
    rotations  R' = P R P^T          <-- a similarity transform, NOT a
                                         component swap. Swapping Euler
                                         components changes handedness and
                                         silently mirrors every twist.

  python3 tools/rvmotion/adapters/ardy_core27.py <ardy_checkout> <in.npz> <out_base>
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from rvmotion.canonical import RVMotion, mat_to_quat, quat_to_mat  # noqa: E402

P = np.array([[1.0, 0.0, 0.0],
              [0.0, 0.0, -1.0],
              [0.0, 1.0, 0.0]])

CONTACT_CHANNELS = ["LeftFoot", "LeftToeBase", "RightFoot", "RightToeBase"]
CALIB = os.path.join(os.path.dirname(__file__), "ardy_core27.json")


def y2z_pos(v):
    return np.einsum("ij,...j->...i", P, np.asarray(v, dtype=np.float64))


def y2z_rot(R):
    R = np.asarray(R, dtype=np.float64)
    return np.einsum("ij,...jk,lk->...il", P, R, P)


def build_calibration(ardy_src):
    """Derive the rest pose from ARDY itself and freeze it into committed data."""
    sys.path.insert(0, ardy_src)
    import torch
    from ardy.skeleton.registry import build_skeleton
    sk = build_skeleton(27)
    J = len(sk.bone_order_names)
    ident = torch.eye(3).repeat(1, J, 1, 1)
    _, pj, _ = sk.fk(ident, torch.zeros(1, 3))
    rest = pj[0].numpy()                       # Y-up rest positions
    parents = [int(p) for p in sk.joint_parents]
    off = np.zeros((J, 3))
    for j in range(J):
        p = parents[j]
        off[j] = rest[j] if p < 0 else rest[j] - rest[p]
    return {
        "source": "ARDY CoreSkeleton27",
        "up_axis_source": "Y", "up_axis_target": "Z",
        "basis_matrix_rows": P.tolist(),
        "basis_note": "positions v'=Pv ; rotations R'=P R P^T (similarity, not a component swap)",
        "joints": list(sk.bone_order_names),
        "parents": parents,
        "rest_translation_zup": y2z_pos(off).tolist(),
        "rest_quat_wxyz": [[1.0, 0.0, 0.0, 0.0]] * J,
        "rest_quat_note": "ARDY composes global = parent_global @ local with no rest rotation",
        "contact_channels": CONTACT_CHANNELS,
        "hip_joint_idx": [19, 23],
    }


def load_calibration(ardy_src=None):
    if os.path.exists(CALIB):
        return json.load(open(CALIB))
    if ardy_src is None:
        raise SystemExit("no committed calibration and no ardy checkout to derive it from")
    c = build_calibration(ardy_src)
    json.dump(c, open(CALIB, "w"), indent=2)
    return c


def adapt(npz_path, calib, phases=None, ee_targets=None):
    d = np.load(npz_path, allow_pickle=True)
    local = y2z_rot(d["local_rot_mats"])       # (T,J,3,3)
    glob = y2z_rot(d["global_rot_mats"])
    pos = y2z_pos(d["posed_joints"])
    root = y2z_pos(d["root_positions"])
    if "global_root_heading" in d.files:
        h = np.asarray(d["global_root_heading"], dtype=np.float64)
        heading = np.arctan2(h[:, 1], h[:, 0]) if h.ndim == 2 else h
    else:
        heading = np.zeros(len(root))
    contacts = np.asarray(d["foot_contacts"]).astype(bool)
    return RVMotion(
        joints=calib["joints"], parents=calib["parents"],
        rest_translation=calib["rest_translation_zup"], rest_quat=calib["rest_quat_wxyz"],
        fps=int(d["fps"]), local_quat=mat_to_quat(local), global_quat=mat_to_quat(glob),
        positions=pos, root_translation=root, root_heading=heading,
        contacts=contacts, contact_channels=calib["contact_channels"],
        phases=phases, ee_targets=ee_targets,
        source={"adapter": "ardy_core27", "npz": os.path.basename(npz_path),
                "basis": "Y-up -> Z-up via P R P^T"})


if __name__ == "__main__":
    ardy_src, inp, out = sys.argv[1], sys.argv[2], sys.argv[3]
    calib = load_calibration(ardy_src)
    m = adapt(inp, calib)
    # adapter self-check: FK from the canonical local quats must reproduce the
    # adapted global rotations and positions. If the basis change were wrong
    # (or Euler-swapped) this is where it shows up.
    gq, gp = m.fk()
    dq = np.abs(np.einsum("tij,tij->ti", gq, m.global_quat))
    print("  FK global-rotation agreement: min |dot| %.9f (1.0 == identical)" % dq.min())
    print("  FK position agreement: max err %.9f m" % np.abs(gp - m.positions).max())
    print("  up-axis check: mean head height %.3f m (Z), mean foot height %.3f m"
          % (m.positions[:, m.joints.index("Head"), 2].mean(),
             m.positions[:, m.joints.index("LeftFoot"), 2].mean()))
    m.save(out)
    print("  wrote %s.rvm.npz (+ .json), %d frames" % (out, m.num_frames))
