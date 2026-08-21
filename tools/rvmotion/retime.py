"""Crop and time-scale a canonical clip, with the compression factor reported.

Game one-shots are shorter than mocap-natural motion, so some compression is
normal; the point is that it is stated, not buried. Rotations are resampled by
slerp (never by lerping matrices), contacts by nearest neighbour so a label is
never invented between two frames.

  python3 tools/rvmotion/retime.py <in.rvm> <out.rvm> --crop a,b --frames N \
      [--sync src_frame=out_frame] [--report r.json]
"""
import json
import sys

import numpy as np

sys.path.insert(0, __file__.rsplit("/", 2)[0])
from rvmotion.canonical import RVMotion, quat_normalize  # noqa: E402


def slerp(q0, q1, t):
    q0 = quat_normalize(q0); q1 = quat_normalize(q1)
    d = (q0 * q1).sum(-1, keepdims=True)
    q1 = np.where(d < 0, -q1, q1); d = np.abs(d)
    ang = np.arccos(np.clip(d, -1.0, 1.0))
    s = np.sin(ang)
    small = s < 1e-6
    w0 = np.where(small, 1.0 - t, np.sin((1.0 - t) * ang) / np.where(small, 1.0, s))
    w1 = np.where(small, t, np.sin(t * ang) / np.where(small, 1.0, s))
    return quat_normalize(w0 * q0 + w1 * q1)


def retime(m, a, b, n_out, sync=None):
    src = m.slice(a, b)
    n_in = src.num_frames
    if sync is None:
        u = np.linspace(0.0, n_in - 1.0, n_out)
    else:
        s_in, s_out = sync
        s_in = s_in - a
        # two linear segments so the named sync moment lands on its output frame
        u = np.concatenate([np.linspace(0.0, s_in, s_out, endpoint=False),
                            np.linspace(s_in, n_in - 1.0, n_out - s_out)])
    i0 = np.clip(np.floor(u).astype(int), 0, n_in - 1)
    i1 = np.clip(i0 + 1, 0, n_in - 1)
    t = (u - i0)[:, None, None]
    lq = slerp(src.local_quat[i0], src.local_quat[i1], t)
    gq = slerp(src.global_quat[i0], src.global_quat[i1], t)
    tt = (u - i0)[:, None]
    pos = src.positions[i0] * (1 - tt[..., None]) + src.positions[i1] * tt[..., None]
    root = src.root_translation[i0] * (1 - tt) + src.root_translation[i1] * tt
    head = src.root_heading[i0] * (1 - (u - i0)) + src.root_heading[i1] * (u - i0)
    contacts = src.contacts[np.round(u).astype(int).clip(0, n_in - 1)]
    return RVMotion(src.joints, src.parents, src.rest_translation, src.rest_quat,
                    src.fps, lq, gq, pos, root, head, contacts, src.contact_channels,
                    src.phases, src.ee_targets,
                    dict(src.source, retimed_from=[a, b], out_frames=n_out,
                         compression=round(n_in / float(n_out), 3))), n_in


if __name__ == "__main__":
    INP, OUTP = sys.argv[1], sys.argv[2]
    def arg(k, d=None):
        return next((sys.argv[i + 1] for i, x in enumerate(sys.argv) if x == k), d)
    a, b = [int(x) for x in arg("--crop").split(",")]
    n_out = int(arg("--frames"))
    sy = arg("--sync")
    sync = tuple(int(x) for x in sy.split("=")) if sy else None
    m = RVMotion.load(INP)
    out, n_in = retime(m, a, b, n_out, sync)
    comp = n_in / float(n_out)
    rep = {"crop": [a, b], "source_frames": n_in, "source_duration_s": round(n_in / m.fps, 3),
           "output_frames": n_out, "output_duration_s": round(n_out / out.fps, 3),
           "time_compression": round(comp, 3),
           "sync": {"source_frame": sync[0], "output_frame": sync[1],
                    "output_time_s": round(sync[1] / out.fps, 3)} if sync else None,
           "compression_verdict": ("acceptable for a game one-shot" if comp <= 2.5
                                   else "EXCESSIVE -- reported, not hidden")}
    print(json.dumps(rep, indent=2))
    r = arg("--report")
    if r: json.dump(rep, open(r, "w"), indent=2)
    out.save(OUTP)
    print("wrote", OUTP + ".rvm.npz")
