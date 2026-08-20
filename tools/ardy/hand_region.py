"""Geometry-only hand region and digit centrelines. No vertex-weight tests.

Every previous attempt selected the hand by vertex weight, which is circular:
the weights are the defect being corrected, and welding degrades them further
(hand.R>=0.4 selects 1126 verts raw but only 262 welded, which silently dropped
the pinky). This selects by geometry alone -- a wrist plane perpendicular to the
forearm axis, a flood fill through mesh adjacency from a palm seed, and a
conservative radius used only to reject unrelated geometry.

  blender --background <rv_rigify.blend> --python hand_region.py -- <json_out>
"""
import json, math, os, sys
import bpy, bmesh
from mathutils import Vector

JOUT = sys.argv[sys.argv.index("--") + 1:][0]
rig = bpy.data.objects["rv_rigify"]
src = max([o for o in bpy.data.objects if o.type == "MESH"],
          key=lambda o: len(o.data.vertices))

proxy = src.copy(); proxy.data = src.data.copy(); proxy.name = "geo_proxy"
bpy.context.collection.objects.link(proxy)
bpy.context.view_layer.objects.active = proxy
if proxy.data.shape_keys: proxy.shape_key_clear()
for m in list(proxy.modifiers): proxy.modifiers.remove(m)
bm = bmesh.new(); bm.from_mesh(proxy.data)
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
bm.to_mesh(proxy.data); bm.free(); proxy.data.update()
print("welded proxy: %d verts" % len(proxy.data.vertices))

ADJ = {}
for e in proxy.data.edges:
    a, b = e.vertices
    ADJ.setdefault(a, []).append(b); ADJ.setdefault(b, []).append(a)
P = [proxy.matrix_world @ v.co for v in proxy.data.vertices]

def bone(n):
    b = rig.data.bones[n]
    return (rig.matrix_world @ Vector(b.head_local),
            rig.matrix_world @ Vector(b.tail_local))

OUT = {}
for side in ("R", "L"):
    fh, ft = bone("DEF-forearm." + side)          # forearm axis
    hh, _ = bone("DEF-hand." + side)
    axis = (hh - fh).normalized()                  # points wrist-ward
    plane_p = hh - axis * 0.012                    # wrist plane, just proximal
    def distal(i): return (P[i] - plane_p).dot(axis) > 0.0
    BOUND = 0.16                                   # rejects thigh only
    ok = [i for i in range(len(P))
          if distal(i) and (P[i] - hh).length < BOUND]
    okset = set(ok)
    # seed: closest vertex to a point out in the palm, distal to the plane
    seed_pt = hh + axis * 0.030
    seed = min(okset, key=lambda i: (P[i] - seed_pt).length)
    region, stack = {seed}, [seed]
    while stack:
        x = stack.pop()
        for y in ADJ.get(x, ()):
            if y in okset and y not in region:
                region.add(y); stack.append(y)
    print("=== %s: bound %d, flood-filled region %d verts ==="
          % (side, len(ok), len(region)))

    # digit identification from adjacency alone, never from a spatial guess
    def comps(sel):
        sel = set(sel); seen = set(); out = []
        for s in sel:
            if s in seen: continue
            st = [s]; seen.add(s); c = []
            while st:
                x = st.pop(); c.append(x)
                for y in ADJ.get(x, ()):
                    if y in sel and y not in seen: seen.add(y); st.append(y)
            out.append(c)
        return sorted([c for c in out if len(c) >= 10], key=len, reverse=True)

    best = None
    for d_mm in range(10, 46, 2):
        sel = [i for i in region if (P[i] - hh).length > d_mm / 1000.0]
        cs = comps(sel)
        if len(cs) == 5 and best is None: best = (d_mm, cs)
        if len(cs) >= 3:
            print("   dist>%2d mm : %d comps %s" % (d_mm, len(cs), [len(c) for c in cs[:6]]))
    if not best:
        print("   NO 5-DIGIT SPLIT for %s" % side)
        OUT[side] = dict(region=len(region), digits=None)
        continue
    d_mm, cs = best
    print("   -> 5 digits separate at distance > %d mm from the wrist" % d_mm)
    hm = rig.matrix_world @ rig.pose.bones["DEF-hand." + side].matrix
    fg = (hm.to_3x3() @ Vector((0, 1, 0))).normalized()
    digits = []
    for c in cs:
        pts = [P[i] for i in c]
        cen = sum(pts, Vector()) / len(pts)
        far = max(pts, key=lambda p: (p - hh).length)
        near = min(pts, key=lambda p: (p - hh).length)
        ax = (far - near).normalized()
        proj = sorted(((p - near).dot(ax), p) for p in pts)
        L = proj[-1][0]
        stations = []
        for k in range(4):
            t0, t1 = L * k / 4.0, L * (k + 1) / 4.0
            sl = [p for d, p in proj if t0 <= d <= t1]
            if sl: stations.append(sum(sl, Vector()) / len(sl))
        digits.append(dict(n=len(c),
                           length=round(L, 4),
                           centre=[round(x, 5) for x in cen],
                           stations=[[round(x, 5) for x in s] for s in stations]))
    digits.sort(key=lambda d: -d["length"])
    for d in digits:
        print("      digit %3d verts, length %.4f m" % (d["n"], d["length"]))
    OUT[side] = dict(region=len(region), split_mm=d_mm, digits=digits,
                     hand_head=[round(x, 5) for x in hh],
                     fing=[round(x, 5) for x in fg])
json.dump(OUT, open(JOUT, "w"), indent=2)
print("REGION_DONE")
