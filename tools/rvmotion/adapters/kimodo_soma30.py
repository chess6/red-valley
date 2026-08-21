"""Adapter: Kimodo SOMASkeleton30 -> Red Valley canonical motion (RVM/1).

The second adapter, and the point of the canonical layer: adding a generator
means writing one file like this, not editing the retargeter. Everything below
the canonical boundary is unchanged.

SOMASkeleton30 contains exactly the 27 canonical joints plus Jaw/LeftEye/
RightEye, which are leaves under Head and are dropped. Its names differ from the
canonical set in two places that matter and would silently mis-map if assumed:

    SOMA30  Spine1 Spine2 Chest Neck1 Neck2      -> Spine Spine1 Spine2 Spine3 Neck
    SOMA30  LeftLeg (thigh!) LeftShin            -> LeftUpLeg LeftLeg

`LeftLeg` means the THIGH in SOMA30 and the SHIN in the canonical set. Mapping by
name without checking would put the knee at the hip.

  python3 tools/rvmotion/adapters/kimodo_soma30.py <kimodo_src> <in.npz> <out_base>
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from rvmotion.canonical import RVMotion, mat_to_quat  # noqa: E402

P = np.array([[1.0, 0.0, 0.0],
              [0.0, 0.0, -1.0],
              [0.0, 1.0, 0.0]])
CALIB = os.path.join(os.path.dirname(__file__), "kimodo_soma30.json")

SOMA_TO_CANONICAL = {
    "Hips": "Hips", "Spine1": "Spine", "Spine2": "Spine1", "Chest": "Spine2",
    "Neck1": "Spine3", "Neck2": "Neck", "Head": "Head",
    "RightShoulder": "RightShoulder", "RightArm": "RightArm",
    "RightForeArm": "RightForeArm", "RightHand": "RightHand",
    "RightHandMiddleEnd": "RightHandEnd", "RightHandThumbEnd": "RightHandThumb1",
    "LeftShoulder": "LeftShoulder", "LeftArm": "LeftArm",
    "LeftForeArm": "LeftForeArm", "LeftHand": "LeftHand",
    "LeftHandMiddleEnd": "LeftHandEnd", "LeftHandThumbEnd": "LeftHandThumb1",
    "RightLeg": "RightUpLeg", "RightShin": "RightLeg",
    "RightFoot": "RightFoot", "RightToeBase": "RightToeBase",
    "LeftLeg": "LeftUpLeg", "LeftShin": "LeftLeg",
    "LeftFoot": "LeftFoot", "LeftToeBase": "LeftToeBase",
}
DROP = {"Jaw", "LeftEye", "RightEye"}
CONTACT_CHANNELS = ["LeftFoot", "LeftToeBase", "RightFoot", "RightToeBase"]


def y2z_pos(v): return np.einsum("ij,...j->...i", P, np.asarray(v, dtype=np.float64))
def y2z_rot(R): return np.einsum("ij,...jk,lk->...il", P, np.asarray(R, dtype=np.float64), P)


def build_calibration(src):
    sys.path.insert(0, src)
    import torch
    from kimodo.skeleton.registry import build_skeleton
    sk = build_skeleton(30)
    soma = list(sk.bone_order_names)
    assert set(soma) - DROP == set(SOMA_TO_CANONICAL), \
        "SOMA30 joint set changed; adapter map is stale: %s" % (set(soma) ^ set(SOMA_TO_CANONICAL) - DROP)
    keep = [n for n in soma if n not in DROP]
    canon = [SOMA_TO_CANONICAL[n] for n in keep]
    idx = [soma.index(n) for n in keep]
    old_parent = {i: int(p) for i, p in enumerate(sk.joint_parents)}
    pos_in_keep = {j: k for k, j in enumerate(idx)}
    parents = []
    for j in idx:
        p = old_parent[j]
        while p >= 0 and p not in pos_in_keep:
            p = old_parent[p]
        parents.append(pos_in_keep[p] if p >= 0 else -1)
    ident = torch.eye(3).repeat(1, len(soma), 1, 1)
    _, pj, _ = sk.fk(ident, torch.zeros(1, 3))
    rest = pj[0].numpy()[idx]
    off = np.zeros((len(idx), 3))
    for k in range(len(idx)):
        p = parents[k]
        off[k] = rest[k] if p < 0 else rest[k] - rest[p]
    return {"source": "Kimodo SOMASkeleton30",
            "up_axis_source": "Y", "up_axis_target": "Z",
            "basis_matrix_rows": P.tolist(),
            "basis_note": "positions v'=Pv ; rotations R'=P R P^T",
            "soma_order": soma, "kept_indices": idx,
            "joints": canon, "parents": parents,
            "name_map": SOMA_TO_CANONICAL, "dropped": sorted(DROP),
            "rest_translation_zup": y2z_pos(off).tolist(),
            "rest_quat_wxyz": [[1.0, 0.0, 0.0, 0.0]] * len(idx),
            "contact_channels": CONTACT_CHANNELS}


def load_calibration(src=None):
    if os.path.exists(CALIB):
        return json.load(open(CALIB))
    c = build_calibration(src)
    json.dump(c, open(CALIB, "w"), indent=2)
    return c


def adapt(npz_path, calib):
    d = np.load(npz_path, allow_pickle=True)
    keep = calib["kept_indices"]
    nj = d["posed_joints"].shape[1]
    assert nj == len(calib["soma_order"]), \
        ("npz has %d joints, calibration expects %d -- assert the skeleton, never "
         "assume it from the model name" % (nj, len(calib["soma_order"])))
    local = y2z_rot(d["local_rot_mats"][:, keep])
    glob = y2z_rot(d["global_rot_mats"][:, keep])
    pos = y2z_pos(d["posed_joints"][:, keep])
    root = y2z_pos(d["root_positions"])
    if "global_root_heading" in d.files:
        h = np.asarray(d["global_root_heading"], dtype=np.float64)
        heading = np.arctan2(h[:, 1], h[:, 0]) if h.ndim == 2 else h
    else:
        heading = np.zeros(len(root))
    fc = np.asarray(d["foot_contacts"]).astype(bool)
    return RVMotion(joints=calib["joints"], parents=calib["parents"],
                    rest_translation=calib["rest_translation_zup"],
                    rest_quat=calib["rest_quat_wxyz"], fps=int(d["fps"]),
                    local_quat=mat_to_quat(local), global_quat=mat_to_quat(glob),
                    positions=pos, root_translation=root, root_heading=heading,
                    contacts=fc, contact_channels=calib["contact_channels"],
                    source={"adapter": "kimodo_soma30", "npz": os.path.basename(npz_path),
                            "basis": "Y-up -> Z-up via P R P^T"})


if __name__ == "__main__":
    src, inp, out = sys.argv[1], sys.argv[2], sys.argv[3]
    calib = load_calibration(src)
    m = adapt(inp, calib)
    gq, gp = m.fk()
    dq = np.abs(np.einsum("tij,tij->ti", gq, m.global_quat))
    print("  FK global-rotation agreement: min |dot| %.9f" % dq.min())
    print("  FK position agreement: max err %.9f m" % np.abs(gp - m.positions).max())
    hz = m.positions[:, m.joints.index("Head"), 2].mean()
    fz = m.positions[:, m.joints.index("LeftFoot"), 2].mean()
    print("  up-axis check: head %.3f m, foot %.3f m" % (hz, fz))
    assert hz > fz, "head below feet -- basis conversion is wrong"
    m.save(out)
    print("  wrote %s.rvm.npz, %d frames, %d joints" % (out, m.num_frames, len(m.joints)))
