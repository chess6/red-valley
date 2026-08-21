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

# Kimodo COMPUTES in SOMASkeleton30 but EXPORTS in SOMASkeleton77: generate.py
# converts on the way out "for external API". So the checkpoint really is 30
# joints (its stats are 364-wide) AND the npz really has 77 -- both facts are
# true, and reading either one alone gives a wrong adapter. The joints we need
# carry the same names in 77, plus finger chains and toe ends we do not use.
# Contacts widen from 4 channels to 6 (a ToeEnd per foot) and are folded back.
# Stated explicitly rather than derived. SOMA77 contains BOTH `LeftHandThumbEnd`
# and `LeftHandThumb1`, and the 30-joint map sends ThumbEnd -> Thumb1, so reusing
# it collapsed two source joints onto one canonical name and produced a 29-joint
# hierarchy with duplicates.
SOMA77_TO_CANONICAL = {
    "Hips": "Hips", "Spine1": "Spine", "Spine2": "Spine1", "Chest": "Spine2",
    "Neck1": "Spine3", "Neck2": "Neck", "Head": "Head",
    "RightShoulder": "RightShoulder", "RightArm": "RightArm",
    "RightForeArm": "RightForeArm", "RightHand": "RightHand",
    "RightHandMiddleEnd": "RightHandEnd", "RightHandThumb1": "RightHandThumb1",
    "LeftShoulder": "LeftShoulder", "LeftArm": "LeftArm",
    "LeftForeArm": "LeftForeArm", "LeftHand": "LeftHand",
    "LeftHandMiddleEnd": "LeftHandEnd", "LeftHandThumb1": "LeftHandThumb1",
    "RightLeg": "RightUpLeg", "RightShin": "RightLeg",
    "RightFoot": "RightFoot", "RightToeBase": "RightToeBase",
    "LeftLeg": "LeftUpLeg", "LeftShin": "LeftLeg",
    "LeftFoot": "LeftFoot", "LeftToeBase": "LeftToeBase",
}
SOMA77_CONTACTS = ["LeftFoot", "LeftToeBase", "LeftToeEnd",
                   "RightFoot", "RightToeBase", "RightToeEnd"]


def y2z_pos(v): return np.einsum("ij,...j->...i", P, np.asarray(v, dtype=np.float64))
def y2z_rot(R): return np.einsum("ij,...jk,lk->...il", P, np.asarray(R, dtype=np.float64), P)


def build_calibration(src, nbjoints=30):
    sys.path.insert(0, src)
    import torch
    from kimodo.skeleton.registry import build_skeleton
    sk = build_skeleton(nbjoints)
    soma = list(sk.bone_order_names)
    name_map = dict(SOMA_TO_CANONICAL) if nbjoints == 30 else dict(SOMA77_TO_CANONICAL)
    absent = [k for k in name_map if k not in soma]
    assert not absent, "map names absent from the %d-joint skeleton: %s" % (nbjoints, absent)
    assert len(set(name_map.values())) == len(name_map), \
        "two source joints map to one canonical joint"
    diff = set(name_map.values()) ^ set(SOMA_TO_CANONICAL.values())
    assert not diff, "canonical joint set differs for nbjoints=%d: %s" % (nbjoints, diff)
    keep = [n for n in soma if n in name_map]
    canon = [name_map[n] for n in keep]
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
            "nbjoints": nbjoints,
            "soma_order": soma, "kept_indices": idx,
            "joints": canon, "parents": parents,
            "name_map": name_map, "dropped": sorted(set(soma) - set(keep)),
            "rest_translation_zup": y2z_pos(off).tolist(),
            "rest_quat_wxyz": [[1.0, 0.0, 0.0, 0.0]] * len(idx),
            "contact_channels": CONTACT_CHANNELS,
            "source_contact_channels": (SOMA77_CONTACTS if nbjoints != 30
                                        else CONTACT_CHANNELS)}


def load_calibration(src=None, nbjoints=30):
    path = CALIB if nbjoints == 30 else CALIB.replace(".json", "_%d.json" % nbjoints)
    if os.path.exists(path):
        return json.load(open(path))
    c = build_calibration(src, nbjoints)
    json.dump(c, open(path, "w"), indent=2)
    return c


def adapt(npz_path, calib):
    d = np.load(npz_path, allow_pickle=True)
    keep = calib["kept_indices"]
    nj = d["posed_joints"].shape[1]
    assert nj == len(calib["soma_order"]), \
        ("npz has %d joints, calibration expects %d -- assert the skeleton, never "
         "assume it from the model name" % (nj, len(calib["soma_order"])))
    glob = y2z_rot(d["global_rot_mats"][:, keep])
    # Derive LOCAL rotations from the globals for the RETAINED hierarchy.
    #
    # Slicing the source locals is only valid when every dropped joint is a leaf.
    # In the 77-joint export it is not: HandEnd sits below four finger joints that
    # we drop, so its stored local rotation is relative to a parent that no longer
    # exists. Composing those gave a 6 cm FK mismatch. Globals are unambiguous:
    #   local_j = global_parent^T . global_j
    par = np.asarray(calib["parents"], dtype=int)
    local = np.empty_like(glob)
    for j in range(glob.shape[1]):
        p_ = int(par[j])
        local[:, j] = glob[:, j] if p_ < 0 else np.einsum(
            "tji,tjk->tik", glob[:, p_].transpose(0, 2, 1)[:, None][:, 0][:, :, :][:, :, :][:, None][:, 0],
            glob[:, j]) if False else np.matmul(glob[:, p_].transpose(0, 2, 1), glob[:, j])
    pos = y2z_pos(d["posed_joints"][:, keep])
    root = y2z_pos(d["root_positions"])
    if "global_root_heading" in d.files:
        h = np.asarray(d["global_root_heading"], dtype=np.float64)
        heading = np.arctan2(h[:, 1], h[:, 0]) if h.ndim == 2 else h
    else:
        heading = np.zeros(len(root))
    # Kimodo's npz carries no fps field (ARDY's does). The checkpoint config says
    # denoiser.motion_rep.fps = 30, so that is used and PRINTED rather than
    # silently assumed -- a wrong fps would misalign every time-based gate.
    fps = int(d["fps"]) if "fps" in d.files else int(os.environ.get("RV_KIMODO_FPS", "30"))
    print("  fps: %d (%s)" % (fps, "from npz" if "fps" in d.files
                              else "from checkpoint config, npz has no fps field"))
    fc = np.asarray(d["foot_contacts"]).astype(bool)
    src_ch = calib.get("source_contact_channels", calib["contact_channels"])
    if list(src_ch) != list(calib["contact_channels"]):
        # fold the 6-channel export back onto the canonical 4: a ToeEnd contact
        # is the same foot touching, so OR it into that foot's ToeBase channel
        idx = {n: i for i, n in enumerate(src_ch)}
        cols = []
        for c in calib["contact_channels"]:
            col = fc[:, idx[c]]
            if c.endswith("ToeBase"):
                end = c.replace("ToeBase", "ToeEnd")
                if end in idx:
                    col = col | fc[:, idx[end]]
            cols.append(col)
        fc = np.stack(cols, axis=1)
    return RVMotion(joints=calib["joints"], parents=calib["parents"],
                    rest_translation=calib["rest_translation_zup"],
                    rest_quat=calib["rest_quat_wxyz"], fps=fps,
                    local_quat=mat_to_quat(local), global_quat=mat_to_quat(glob),
                    positions=pos, root_translation=root, root_heading=heading,
                    contacts=fc, contact_channels=calib["contact_channels"],
                    source={"adapter": "kimodo_soma30", "npz": os.path.basename(npz_path),
                            "basis": "Y-up -> Z-up via P R P^T"})


if __name__ == "__main__":
    src, inp, out = sys.argv[1], sys.argv[2], sys.argv[3]
    nj = int(np.load(inp, allow_pickle=True)["posed_joints"].shape[1])
    print("  npz declares %d joints" % nj)
    calib = load_calibration(src, nj)
    m = adapt(inp, calib)
    gq, gp = m.fk()
    dq = np.abs(np.einsum("tij,tij->ti", gq, m.global_quat))
    print("  FK global-rotation agreement: min |dot| %.9f" % dq.min())
    # The 77-joint export drives HandEnd through four finger joints we drop, so a
    # rigid Hand->HandEnd offset cannot reproduce it once the fingers articulate.
    # That residual is expected and confined; every other joint must be exact, and
    # this asserts it rather than leaving an unexplained error in the log.
    perj = np.linalg.norm(gp - m.positions, axis=2).max(axis=0)
    soft = {m.joints.index(n) for n in ("LeftHandEnd", "RightHandEnd") if n in m.joints}
    hard = max((v for i, v in enumerate(perj) if i not in soft), default=0.0)
    print("  FK position agreement: %.9f m on load-bearing joints, "
          "%.4f m on HandEnd (fingers dropped, expected)"
          % (hard, max((perj[i] for i in soft), default=0.0)))
    assert hard < 1e-6, "FK position mismatch on a load-bearing joint: %.6f m" % hard
    hz = m.positions[:, m.joints.index("Head"), 2].mean()
    fz = m.positions[:, m.joints.index("LeftFoot"), 2].mean()
    print("  up-axis check: head %.3f m, foot %.3f m" % (hz, fz))
    assert hz > fz, "head below feet -- basis conversion is wrong"
    m.save(out)
    print("  wrote %s.rvm.npz, %d frames, %d joints" % (out, m.num_frames, len(m.joints)))
