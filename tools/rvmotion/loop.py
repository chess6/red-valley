"""Phase-aware cycle extraction and seam closure, in canonical space.

v1 required the loop to be verbatim contiguous frames, which left an 8.2 cm
body-space seam because no pair of raw frames is ever exactly cyclic. That
constraint was self-imposed, not a production requirement: every shipped game
walk cycle is seam-closed. Here the seam residual is distributed smoothly
across the whole cycle (each joint rotates a fraction t/N of the closing delta),
which closes it exactly while spreading the correction thinly enough to be
invisible -- and the result is measured, not asserted.

Cycle candidates come from the SOURCE's own contact labels: a cycle must begin
and end at the same point in the gait phase (same contact pattern, same foot
leading), which is what makes the loop read as continuous.

  python3 tools/rvmotion/loop.py <in.rvm> <out.rvm> [--report r.json]
"""
import json
import sys

import numpy as np

sys.path.insert(0, __file__.rsplit("/", 2)[0])
from rvmotion.canonical import RVMotion, quat_to_mat, mat_to_quat, quat_normalize  # noqa: E402

INP, OUTP = sys.argv[1], sys.argv[2]
REPORT = next((sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == "--report"), None)
m = RVMotion.load(INP)
T = m.num_frames
C = m.contacts.astype(int)
POS, LQ = m.positions, m.local_quat


def body_space(f):
    """Pose relative to the hips, so a cycle is judged on the body, not the world."""
    return POS[f] - POS[f, 0]


def phase_key(f):
    return tuple(C[f])


def seam_cost(a, b):
    dp = np.linalg.norm(body_space(a) - body_space(b), axis=1).mean()
    va = body_space(min(a + 1, T - 1)) - body_space(a)
    vb = body_space(min(b + 1, T - 1)) - body_space(b)
    dv = np.linalg.norm(va - vb, axis=1).mean()
    return dp + 4.0 * dv, dp, dv


# --- candidate cycles: one full STRIDE, foot-strike to the same foot's next
# strike. Matching contact *patterns* is not enough -- (1,1,1,1) double support
# occurs several times per stride and at the stopping pose, which is how an
# earlier draft picked a 0.75 s window at the very end of the clip.
FPS = m.fps
MIN_N, MAX_N = int(0.6 * FPS), int(2.2 * FPS)
ch = {n: i for i, n in enumerate(m.contact_channels)}

def strikes(name):
    on = C[:, ch[name]].astype(bool)
    return [f for f in range(1, T) if on[f] and not on[f - 1]]

# steady-state only: drop the first and last 10% (acceleration / stopping)
lo, hi = int(0.10 * T), int(0.90 * T)
cands = []
for foot in ("LeftFoot", "RightFoot"):
    st = [f for f in strikes(foot) if lo <= f <= hi]
    for a, b in zip(st[:-1], st[1:]):
        if MIN_N <= b - a <= MAX_N:
            cands.append((a, b, foot))
if not cands:
    raise SystemExit("no full stride found between contact strikes -- "
                     "refusing to fabricate a cycle from mismatched phases")
def candidate_seam(a, b):
    """Score with the SAME metric the gate uses, on the raw (unclosed) crop."""
    P = POS
    pred = 2.0 * (P[b - 1] - P[b - 1, 0]) - (P[b - 2] - P[b - 2, 0])
    return float(np.linalg.norm((P[a] - P[a, 0]) - pred, axis=1).max())
scored = []
for a, b, foot in cands:
    _c, dp, dv = seam_cost(a, b)
    scored.append((candidate_seam(a, b), a, b, dp, dv, foot))
scored.sort()
print("stride candidates scored (seam m): " +
      ", ".join("[%d,%d)=%.3f" % (a, b, c) for c, a, b, *_ in scored))
cost, A, B, dp0, dv0, FOOT = scored[0]
N = B - A
print("stride candidates: %d; chose %s-strike to %s-strike" % (len(cands), FOOT, FOOT))
print("cycle [%d, %d)  %d frames = %.3f s   raw seam: pose %.4f m, vel %.4f m/f"
      % (A, B, N, N / FPS, dp0, dv0))

clip = m.slice(A, B)

# --- close the seam: distribute the residual across the whole cycle ---------
def qmul(a, b):
    w1, x1, y1, z1 = a[..., 0], a[..., 1], a[..., 2], a[..., 3]
    w2, x2, y2, z2 = b[..., 0], b[..., 1], b[..., 2], b[..., 3]
    return np.stack([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
                     w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
                     w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2], -1)

def qconj(a):
    return np.stack([a[..., 0], -a[..., 1], -a[..., 2], -a[..., 3]], -1)

def qpow(q, t):
    q = quat_normalize(q)
    w = np.clip(q[..., 0], -1.0, 1.0)
    ang = np.arccos(w)
    s = np.sin(ang)
    axis = np.where(s[..., None] > 1e-8, q[..., 1:] / np.where(s[..., None] < 1e-8, 1, s[..., None]),
                    np.zeros_like(q[..., 1:]))
    na = ang * t
    return np.concatenate([np.cos(na)[..., None], axis * np.sin(na)[..., None]], -1)

# frame after the last one of the cycle should equal frame 0: use source frame B
lq = clip.local_quat.copy()
tail = m.local_quat[B]                                  # what the source does next
delta = qmul(lq[0], qconj(tail))                        # rotation closing the gap
delta = np.where(delta[..., :1] < 0, -delta, delta)     # shortest arc
n = lq.shape[0]
for t in range(n):
    w = t / float(n)                                    # 0 at the start, ->1 at the seam
    lq[t] = qmul(qpow(delta, w), lq[t])
lq = quat_normalize(lq)

# Root: a locomotion cycle is SUPPOSED to advance by one stride, so closing the
# raw root would cancel the walk and leave the feet skating against a body that
# never moves. Close only the residual about the cycle's own linear trend.
root = clip.root_translation.copy()
root_tail = m.root_translation[B]
tt = np.arange(n + 1)[:, None]
trend_fit = np.linalg.lstsq(np.hstack([tt, np.ones_like(tt)]),
                            np.vstack([root, root_tail[None]]), rcond=None)[0]
trend = np.hstack([np.arange(n)[:, None], np.ones((n, 1))]) @ trend_fit
trend_next = np.array([[n, 1.0]]) @ trend_fit
resid = root - trend
resid_tail = root_tail - trend_next[0]
rdelta = resid[0] - resid_tail
for t in range(n):
    root[t] = root[t] + rdelta * (t / float(n))
print("root: stride advance %.3f m kept; closed residual %.4f m"
      % (float(np.linalg.norm(trend_next[0][:2] - trend[0][:2])),
         float(np.linalg.norm(rdelta))))

closed = RVMotion(clip.joints, clip.parents, clip.rest_translation, clip.rest_quat,
                  clip.fps, lq, clip.global_quat, clip.positions, root,
                  clip.root_heading, clip.contacts, clip.contact_channels,
                  clip.phases, clip.ee_targets,
                  dict(clip.source, loop_cycle=[A, B], seam_closed=True))
# rebuild global rotations and positions from the corrected locals
gq, gp = closed.fk()
closed.global_quat = gq
closed.positions = gp
closed.validate()

def bs(P, f): return P[f] - P[f, 0]

def seam_metrics(mo):
    """Seam error = the VELOCITY discontinuity across the wrap, measured as
    extrapolation error.

    Two earlier metrics were wrong and both flattered or damned the clip for the
    wrong reason. "frame 0 vs frame n-1" is one legitimate frame of motion.
    "wrap step vs the cycle's median step" punishes any joint that happens to sit
    at a velocity turning point at the seam -- the swinging hand is nearly
    stationary at both ends of a stride, so a correctly closed loop scored 4.8 cm.

    What a viewer actually perceives as a hitch is a sudden change of velocity.
    So: linearly extrapolate the wrapped sequence one frame past the end and
    compare with where the loop actually restarts."""
    P, n_ = mo.positions, mo.num_frames
    pred = 2.0 * bs(P, n_ - 1) - bs(P, n_ - 2)        # continue the last step
    err = np.linalg.norm(bs(P, 0) - pred, axis=1)      # vs where it actually resumes
    # Compare against EVERY interior transition. A single arbitrary interior
    # sample is not evidence about the cycle -- an earlier version used frame 2
    # and nothing else.
    inner_all = np.array([
        np.linalg.norm(bs(P, i + 1) - (2.0 * bs(P, i) - bs(P, i - 1)), axis=1).max()
        for i in range(1, n_ - 1)])
    q = mo.local_quat
    def qang(a, b): return np.degrees(2 * np.arccos(np.clip(np.abs((a * b).sum(-1)), 0, 1)))
    a_in, a_out = qang(q[n_ - 1], q[n_ - 2]), qang(q[0], q[n_ - 1])
    return {"seam_extrapolation_err_max_m": float(err.max()),
            "seam_extrapolation_err_mean_m": float(err.mean()),
            "worst_joint": mo.joints[int(err.argmax())],
            "interior_err_median_m": float(np.median(inner_all)),
            "interior_err_p90_m": float(np.percentile(inner_all, 90)),
            "interior_err_max_m": float(inner_all.max()),
            "seam_percentile_within_interior": float(100.0 * np.mean(err.max() > inner_all)),
            "seam_angular_step_change_max_deg": float(np.abs(a_out - a_in).max())}

raw_metrics = seam_metrics(clip)
metrics = seam_metrics(closed)
seam_after = metrics["seam_extrapolation_err_max_m"]
vel_disc = metrics["seam_extrapolation_err_mean_m"]
ang_disc = metrics["seam_angular_step_change_max_deg"]

rep = {"cycle": [A, B], "frames": n, "duration_s": round(n / FPS, 4),
       "stride_foot": FOOT,
       "seam_before_closure": {k: round(v, 5) if isinstance(v, float) else v
                               for k, v in raw_metrics.items()},
       "seam_after_closure": {k: round(v, 5) if isinstance(v, float) else v
                              for k, v in metrics.items()},
       "gate_documented_seam_lt_1cm": {
           "value_m": round(seam_after, 5), "pass": seam_after < 0.01,
           "note": ("NOT MET. At 20 fps a swinging foot covers ~12 cm per frame, and "
                    "the SAME extrapolation test applied inside the cycle has a median of "
                    "%.3f m -- so a 1 cm absolute gate is stricter than the motion "
                    "itself and cannot be met by any crop of this source."
                    % metrics["interior_err_median_m"])},
       "gate_proposed_seam_no_worse_than_interior": {
           "seam_m": round(seam_after, 5),
           "interior_median_m": round(metrics["interior_err_median_m"], 5),
           "interior_p90_m": round(metrics["interior_err_p90_m"], 5),
           "pass": seam_after <= metrics["interior_err_median_m"],
           "status": "PROPOSED AND NOT APPROVED -- reported for information only",
           "rationale": ("A loop reads as continuous when the wrap frame is no more "
                         "abrupt than a normal frame of the same motion. This is "
                         "resolution- and speed-independent, unlike a fixed distance. "
                         "PROPOSED -- awaiting approval; the documented 1 cm figure is "
                         "reported above unchanged.")},
       "contacts_at_ends": [C[A].tolist(), C[B].tolist()]}
print(json.dumps(rep, indent=2))
if REPORT: json.dump(rep, open(REPORT, "w"), indent=2)
closed.save(OUTP)
print("wrote", OUTP + ".rvm.npz")
