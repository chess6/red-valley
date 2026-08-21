"""Red Valley canonical motion representation (RVM/1) — source independent.

Everything downstream of an adapter speaks this and only this. A new generator
(Kimodo, HY-Motion, hand-authored) is added by writing one adapter, never by
touching the retargeter.

Design rules learned from the v1 failure:
  * ROTATIONS ARE THE PAYLOAD. v1 carried only joint positions and re-derived
    orientation by aiming a bone at the next joint, which cannot represent
    axial twist at all (minimal-arc rotation has zero component about its own
    axis). RVM carries local AND global unit quaternions.
  * Z-UP, always. The adapter does the complete basis change for positions and
    rotations (R' = P R P^T), never a component swap.
  * Quaternion sign continuity is part of the format, not a consumer's problem.
  * Root translation is carried in full. An in-place clip is produced by
    subtracting a documented ground-plane trajectory, never by dropping the
    channel.
  * Contacts are source labels, not a height guess.
  * Interaction phases and end-effector targets travel WITH the motion, so a
    prop can be driven from the same file the body is driven from.

Layout: <name>.rvm.npz (arrays) + <name>.rvm.json (schema, hierarchy, phases).
"""
import json
import os

import numpy as np

FORMAT = "RVM/1"


def quat_normalize(q):
    n = np.linalg.norm(q, axis=-1, keepdims=True)
    n = np.where(n < 1e-12, 1.0, n)
    return q / n


def quat_hemisphere(q):
    """Make a (T, J, 4) quaternion track continuous: no sign flips between frames.

    q and -q are the same rotation but interpolate along opposite arcs, so a
    stray flip shows up as a joint spinning the long way round.
    """
    q = np.array(q, dtype=np.float64, copy=True)
    for t in range(1, q.shape[0]):
        d = np.einsum("ij,ij->i", q[t], q[t - 1])
        q[t][d < 0.0] *= -1.0
    return q


def mat_to_quat(m):
    """(..., 3, 3) rotation matrices -> (..., 4) wxyz quaternions, branch-safe."""
    m = np.asarray(m, dtype=np.float64)
    t = m[..., 0, 0] + m[..., 1, 1] + m[..., 2, 2]
    q = np.empty(m.shape[:-2] + (4,), dtype=np.float64)
    # four branches, each numerically stable in its own region
    b0 = t > 0.0
    b1 = (~b0) & (m[..., 0, 0] >= m[..., 1, 1]) & (m[..., 0, 0] >= m[..., 2, 2])
    b2 = (~b0) & (~b1) & (m[..., 1, 1] >= m[..., 2, 2])
    b3 = ~(b0 | b1 | b2)
    s = np.sqrt(np.maximum(t + 1.0, 1e-12)) * 2.0
    q[b0] = np.stack([0.25 * s, (m[..., 2, 1] - m[..., 1, 2]) / s,
                      (m[..., 0, 2] - m[..., 2, 0]) / s,
                      (m[..., 1, 0] - m[..., 0, 1]) / s], -1)[b0]
    s = np.sqrt(np.maximum(1.0 + m[..., 0, 0] - m[..., 1, 1] - m[..., 2, 2], 1e-12)) * 2.0
    q[b1] = np.stack([(m[..., 2, 1] - m[..., 1, 2]) / s, 0.25 * s,
                      (m[..., 0, 1] + m[..., 1, 0]) / s,
                      (m[..., 0, 2] + m[..., 2, 0]) / s], -1)[b1]
    s = np.sqrt(np.maximum(1.0 - m[..., 0, 0] + m[..., 1, 1] - m[..., 2, 2], 1e-12)) * 2.0
    q[b2] = np.stack([(m[..., 0, 2] - m[..., 2, 0]) / s,
                      (m[..., 0, 1] + m[..., 1, 0]) / s, 0.25 * s,
                      (m[..., 1, 2] + m[..., 2, 1]) / s], -1)[b2]
    s = np.sqrt(np.maximum(1.0 - m[..., 0, 0] - m[..., 1, 1] + m[..., 2, 2], 1e-12)) * 2.0
    q[b3] = np.stack([(m[..., 1, 0] - m[..., 0, 1]) / s,
                      (m[..., 0, 2] + m[..., 2, 0]) / s,
                      (m[..., 1, 2] + m[..., 2, 1]) / s, 0.25 * s], -1)[b3]
    return quat_normalize(q)


def quat_to_mat(q):
    q = quat_normalize(np.asarray(q, dtype=np.float64))
    w, x, y, z = q[..., 0], q[..., 1], q[..., 2], q[..., 3]
    return np.stack([
        1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y),
        2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x),
        2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y),
    ], -1).reshape(q.shape[:-1] + (3, 3))


class RVMotion:
    """One clip. Arrays are (T, ...) with T frames; quaternions are wxyz."""

    def __init__(self, joints, parents, rest_translation, rest_quat, fps,
                 local_quat, global_quat, positions, root_translation,
                 root_heading, contacts, contact_channels,
                 phases=None, ee_targets=None, source=None):
        self.joints = list(joints)
        self.parents = np.asarray(parents, dtype=np.int32)
        self.rest_translation = np.asarray(rest_translation, dtype=np.float64)
        self.rest_quat = quat_normalize(np.asarray(rest_quat, dtype=np.float64))
        self.fps = int(fps)
        self.local_quat = quat_hemisphere(quat_normalize(np.asarray(local_quat)))
        self.global_quat = quat_hemisphere(quat_normalize(np.asarray(global_quat)))
        self.positions = np.asarray(positions, dtype=np.float64)
        self.root_translation = np.asarray(root_translation, dtype=np.float64)
        self.root_heading = np.asarray(root_heading, dtype=np.float64)
        self.contacts = np.asarray(contacts)
        self.contact_channels = list(contact_channels)
        self.phases = list(phases or [])
        self.ee_targets = list(ee_targets or [])
        self.source = dict(source or {})
        self.validate()

    # -- invariants the format guarantees to every consumer ------------------
    def validate(self):
        T, J = self.local_quat.shape[0], len(self.joints)
        assert self.local_quat.shape == (T, J, 4), "local_quat shape"
        assert self.global_quat.shape == (T, J, 4), "global_quat shape"
        assert self.positions.shape == (T, J, 3), "positions shape"
        assert self.root_translation.shape == (T, 3), "root_translation shape"
        assert self.parents.shape == (J,) and self.parents[0] == -1, "hierarchy"
        for j in range(1, J):
            assert 0 <= self.parents[j] < j, "parents must be topologically ordered"
        assert self.contacts.shape[0] == T, "contacts frames"
        assert self.contacts.shape[1] == len(self.contact_channels), "contact channels"
        for arr, nm in ((self.local_quat, "local_quat"), (self.global_quat, "global_quat"),
                        (self.positions, "positions"), (self.root_translation, "root")):
            assert np.isfinite(arr).all(), "%s not finite" % nm
        for nm, q in (("local", self.local_quat), ("global", self.global_quat)):
            err = np.abs(np.linalg.norm(q, axis=-1) - 1.0).max()
            assert err < 1e-6, "%s quaternions not unit (%.2e)" % (nm, err)
            d = np.einsum("tij,tij->ti", q[1:], q[:-1])
            assert d.min() >= -1e-9, "%s quaternions flip hemisphere" % nm

    @property
    def num_frames(self): return self.local_quat.shape[0]

    def fk(self):
        """Rebuild global rotations and positions from local quats + hierarchy."""
        T, J = self.num_frames, len(self.joints)
        gq = np.zeros((T, J, 4)); gp = np.zeros((T, J, 3))
        lm = quat_to_mat(self.local_quat)
        rm = quat_to_mat(self.rest_quat)
        gm = np.zeros((T, J, 3, 3))
        for j in range(J):
            p = int(self.parents[j])
            local = rm[j][None] @ lm[:, j]
            if p < 0:
                gm[:, j] = local
                gp[:, j] = self.root_translation
            else:
                gm[:, j] = gm[:, p] @ local
                gp[:, j] = gp[:, p] + np.einsum("tij,j->ti", gm[:, p], self.rest_translation[j])
            gq[:, j] = mat_to_quat(gm[:, j])
        return gq, gp

    def slice(self, start, end):
        """Half-open [start, end) crop that keeps phases and targets aligned."""
        sl = slice(start, end)
        ph = [dict(p, start=max(0, p["start"] - start), end=min(end - start, p["end"] - start))
              for p in self.phases if p["end"] > start and p["start"] < end]
        tg = [dict(t, frame=t["frame"] - start) for t in self.ee_targets
              if start <= t.get("frame", -1) < end]
        return RVMotion(self.joints, self.parents, self.rest_translation, self.rest_quat,
                        self.fps, self.local_quat[sl], self.global_quat[sl],
                        self.positions[sl], self.root_translation[sl],
                        self.root_heading[sl], self.contacts[sl], self.contact_channels,
                        ph, tg, dict(self.source, cropped_from=[start, end]))

    def save(self, base):
        os.makedirs(os.path.dirname(base) or ".", exist_ok=True)
        np.savez_compressed(base + ".rvm.npz",
                            local_quat=self.local_quat, global_quat=self.global_quat,
                            positions=self.positions, root_translation=self.root_translation,
                            root_heading=self.root_heading, contacts=self.contacts,
                            rest_translation=self.rest_translation, rest_quat=self.rest_quat,
                            parents=self.parents)
        json.dump({"format": FORMAT, "up_axis": "Z", "quaternion_order": "wxyz",
                   "fps": self.fps, "frames": int(self.num_frames),
                   "joints": self.joints, "parents": self.parents.tolist(),
                   "contact_channels": self.contact_channels,
                   "phases": self.phases, "ee_targets": self.ee_targets,
                   "source": self.source},
                  open(base + ".rvm.json", "w"), indent=2)
        return base + ".rvm.npz"

    @staticmethod
    def load(base):
        base = base[:-8] if base.endswith(".rvm.npz") else base
        a = np.load(base + ".rvm.npz")
        m = json.load(open(base + ".rvm.json"))
        return RVMotion(m["joints"], a["parents"], a["rest_translation"], a["rest_quat"],
                        m["fps"], a["local_quat"], a["global_quat"], a["positions"],
                        a["root_translation"], a["root_heading"], a["contacts"],
                        m["contact_channels"], m.get("phases"), m.get("ee_targets"),
                        m.get("source"))
