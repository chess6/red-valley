"""Prove a saved contract actually encodes the motion it claims, before spending.

The first A/B run produced no step from either generator because the contract
pinned the root at rest, making a forward step geometrically impossible. That was
free to detect and cost a paid run to discover. This asserts, from the SAVED file
via the generator's own loader:

  * the root advances (root_2d is not constant)
  * the lead foot has two distinct ground positions, start and landed
  * the rear foot has exactly one
  * every set stays under 20 keyframes

  python3 tools/rvmotion/prove_contract.py --generator {ardy,kimodo} --src S --file F
"""
import argparse
import sys

import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--generator", required=True, choices=["ardy", "kimodo"])
    ap.add_argument("--src", required=True)
    ap.add_argument("--file", required=True)
    ap.add_argument("--joints", type=int, default=None)
    a = ap.parse_args()
    sys.path.insert(0, a.src)
    if a.generator == "ardy":
        from ardy.skeleton.registry import build_skeleton
        from ardy.constraints import load_constraints_lst
        nj = a.joints or 27
    else:
        from kimodo.skeleton.registry import build_skeleton
        from kimodo.constraints import load_constraints_lst
        nj = a.joints or 30
    sk = build_skeleton(nj)
    BI = sk.bone_index
    cs = load_constraints_lst(a.file, sk)
    fails = []

    def gate(name, ok, detail):
        print("  %-42s %s  (%s)" % (name, "PASS" if ok else "FAIL", detail))
        if not ok:
            fails.append(name)

    gate("%d constraint sets loaded" % len(cs), len(cs) >= 4, "expected >= 4")
    for c in cs:
        gate("%s < 20 keyframes" % type(c).__name__, len(c.frame_indices) < 20,
             "%d frames" % len(c.frame_indices))

    # Saved positions are ROOT-RELATIVE. Judging a world-fixed foot without
    # adding the root back reports it as moving exactly as far as the body did --
    # which is how the first version failed a rear foot that was in fact planted.
    have_root = [c for c in cs if hasattr(c, "root_2d")]
    if have_root:
        r2 = np.concatenate([c.root_2d.numpy() for c in have_root], axis=0)
        span = float(np.ptp(r2, axis=0).max())
        gate("root advances across the clip", span > 0.05, "root_2d span %.4f m" % span)
    else:
        # Kimodo's sets carry no root_2d, so stored positions are already absolute
        # and must NOT have a root added back.
        print("  %-42s %s  (%s)" % ("root channel", "N/A",
              "this generator's sets carry no root_2d; positions are absolute"))

    def world(c, joint):
        """root-relative -> world, for the ground plane."""
        p = c.global_joints_positions[:, BI[joint]].numpy().copy()
        if have_root and hasattr(c, "root_2d"):
            r = c.root_2d.numpy()
            p[:, 0] += r[:, 0]
            p[:, 2] += r[:, 1]
        return p

    lead = [c for c in cs if "LeftFoot" in getattr(c, "joint_names", [])]
    pos = [world(c, "LeftFoot") for c in lead]
    if pos:
        allp = np.concatenate(pos, axis=0)
        spread = float(np.ptp(allp, axis=0).max())
        gate("lead foot has a start AND a landed spot", spread > 0.15,
             "spread %.4f m over %d keys" % (spread, len(allp)))
    rear = [c for c in cs if "RightFoot" in getattr(c, "joint_names", [])]
    if rear:
        rp = np.concatenate([world(c, "RightFoot") for c in rear], axis=0)
        gate("rear foot stays put", float(np.ptp(rp, axis=0).max()) < 0.05,
             "spread %.4f m" % float(np.ptp(rp, axis=0).max()))
    hand = [c for c in cs if "RightHand" in getattr(c, "joint_names", [])]
    if hand:
        hp = np.concatenate([world(c, "RightHand") for c in hand], axis=0)
        gate("hand target is a single pour pose", float(np.ptp(hp, axis=0).max()) < 0.15,
             "spread %.4f m" % float(np.ptp(hp, axis=0).max()))
    print("RESULT:", "CONTRACT ENCODES THE MOTION" if not fails else "FAILED: %s" % fails)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
