"""Extend the accepted rv_rig with symmetric finger chains.

Three deform bones per digit, five digits per hand, parented under hand.R/.L.
Existing body bones are untouched; only weight already sitting on hand.R/hand.L
is redistributed into the new chains, so no non-hand weight changes.

Digits are located from the mesh, not assumed: the fingertip band is split along
the across-palm axis at its largest gaps, which separates cleanly even though the
finger mesh is too coarse for spatial clustering (vertex spacing exceeds the
inter-digit gap, so DBSCAN at 4 mm returns singletons).

  blender --background --python add_fingers.py -- <src.glb> <out.glb>
"""
import json, math, os, sys
import bpy
from mathutils import Vector, Matrix
from mathutils.kdtree import KDTree

argv = sys.argv[sys.argv.index("--") + 1:]
SRC, OUT = argv[0], argv[1]
os.makedirs(os.path.dirname(OUT), exist_ok=True)

DIGITS = ["thumb", "index", "middle", "ring", "pinky"]
PHAL = [0.45, 0.30, 0.25]          # proximal / middle / distal share of length
TIP_BAND = 0.78                     # fraction along the hand where tips are read
KNUCKLE = 0.55

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=SRC)
rig = [o for o in bpy.data.objects if o.type == "ARMATURE"][0]
obj = max([o for o in bpy.data.objects if o.type == "MESH" and len(o.vertex_groups)],
          key=lambda o: len(o.data.vertices))
for o in list(bpy.data.objects):
    if o.type == "MESH" and o is not obj:
        bpy.data.objects.remove(o, do_unlink=True)   # stray Icosphere helper

bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode="POSE")
PB = rig.pose.bones
GI = {g.name: g.index for g in obj.vertex_groups}

def wt(v, n):
    i = GI.get(n)
    return next((g.weight for g in v.groups if g.group == i), 0.0) if i is not None else 0.0

def hand_frame(side):
    hv = [v for v in obj.data.vertices if wt(v, "hand." + side) >= 0.5]
    co = [obj.matrix_world @ v.co for v in hv]
    hm = rig.matrix_world @ PB["hand." + side].matrix
    fing = (hm.to_3x3() @ Vector((0, 1, 0))).normalized()
    o = hm.to_translation()
    t = [(c - o).dot(fing) for c in co]
    lo, hi = min(t), max(t)
    palm = [c for c, tt in zip(co, t) if lo + 0.20 * (hi - lo) <= tt <= lo + 0.55 * (hi - lo)]
    pc = sum(palm, Vector()) / len(palm)
    u = Vector((0, 0, 1)).cross(fing)
    if u.length < 1e-6: u = Vector((1, 0, 0)).cross(fing)
    u.normalize(); v2 = fing.cross(u).normalized()
    sxx = syy = sxy = 0.0
    for c in palm:
        d = c - pc; a, b = d.dot(u), d.dot(v2)
        sxx += a * a; syy += b * b; sxy += a * b
    th = 0.5 * math.atan2(2 * sxy, sxx - syy)
    e1 = (u * math.cos(th) + v2 * math.sin(th)).normalized()
    e2 = fing.cross(e1).normalized()
    v1 = sum(((c - pc).dot(e1)) ** 2 for c in palm)
    v2v = sum(((c - pc).dot(e2)) ** 2 for c in palm)
    bar, nrm = (e1, e2) if v1 > v2v else (e2, e1)
    if nrm.dot(Vector((0, -1, 0))) < 0: nrm = -nrm
    return dict(verts=hv, co=co, t=t, lo=lo, hi=hi, o=o, fing=fing,
                bar=bar, nrm=nrm, pc=pc)

def track_tube(start, d0, coords, kd, max_len, step=0.0045, radius=0.011):
    """Walk down a digit, re-centring on the local cross-section each step.

    Straight chains do not work here: the rest fingers are curled, so a chain
    drawn knuckle-to-tip passes through air and only captures the tips. Tracking
    re-centres on the mesh at every station, so the chain follows the curl.
    """
    pts = [start.copy()]
    p, d, L = start.copy(), d0.normalized(), 0.0
    while L < max_len:
        nb = [coords[j] for (_, j, _) in kd.find_range(p, radius)]
        if len(nb) < 4: break
        c = sum(nb, Vector()) / len(nb)
        c = c - d * (c - p).dot(d)          # re-centre across the tube only
        nxt = c + d * step
        nb2 = [coords[j] for (_, j, _) in kd.find_range(nxt, radius)]
        if len(nb2) >= 4:
            c2 = sum(nb2, Vector()) / len(nb2)
            nd = (c2 - p)
            if nd.length > 1e-5:
                d = (d * 0.55 + nd.normalized() * 0.45).normalized()
        p = c + d * step
        pts.append(p.copy()); L += step
    return pts

def resample(pts, n=4):
    """n points evenly spaced by arc length along the tracked polyline."""
    if len(pts) < 2: return [pts[0]] * n
    seg = [(pts[i + 1] - pts[i]).length for i in range(len(pts) - 1)]
    tot = sum(seg)
    out, acc, i = [pts[0]], 0.0, 0
    for k in range(1, n):
        target = tot * k / (n - 1)
        while i < len(seg) and acc + seg[i] < target:
            acc += seg[i]; i += 1
        if i >= len(seg): out.append(pts[-1]); continue
        f = (target - acc) / max(1e-9, seg[i])
        out.append(pts[i].lerp(pts[i + 1], f))
    return out

def build(side):
    F = hand_frame(side)
    span = F["hi"] - F["lo"]
    o, fing, bar, nrm, pc = F["o"], F["fing"], F["bar"], F["nrm"], F["pc"]
    coords = F["co"]
    kd = KDTree(len(coords))
    for i, c in enumerate(coords): kd.insert(c, i)
    kd.balance()

    # Tips are the one part of this hand that IS separable -- split the tip band
    # along the across-palm axis at its three largest gaps.
    band = [(c, (c - pc).dot(bar)) for c, tt in zip(coords, F["t"])
            if tt > F["lo"] + 0.86 * span]
    band.sort(key=lambda x: x[1])
    gaps = sorted(((band[i + 1][1] - band[i][1], i) for i in range(len(band) - 1)),
                  reverse=True)[:3]
    cuts = sorted(i for _, i in gaps)
    groups, prev = [], 0
    for cidx in cuts + [len(band) - 1]:
        groups.append(band[prev:cidx + 1]); prev = cidx + 1
    groups = [g for g in groups if len(g) >= 4]

    proud = [c for c in coords if (c - pc).dot(nrm) > 0.012]
    u_thumb = sum((c - o).dot(bar) for c in proud) / max(1, len(proud))
    sgn = 1.0 if u_thumb > (pc - o).dot(bar) else -1.0
    groups.sort(key=lambda g: sum(x[1] for x in g) / len(g), reverse=(sgn < 0))

    chains, tracks = {}, {}
    names = ["index", "middle", "ring", "pinky"][:len(groups)]
    for name, g in zip(names, groups):
        tip = sum((c for c, _ in g), Vector()) / len(g)
        pts = track_tube(tip, -fing, coords, kd, max_len=0.46 * span)
        pts.reverse()                                  # base -> tip
        tracks[name] = pts
        chains[name] = resample(pts, 4)
    # thumb: start at the most distal vertex standing proud of the palm
    if proud:
        tipv = max(proud, key=lambda c: (c - o).dot(fing) + (c - pc).dot(nrm))
        pts = track_tube(tipv, -(fing * 0.6 + nrm * 0.4).normalized(),
                         coords, kd, max_len=0.42 * span)
        pts.reverse()
        tracks["thumb"] = pts
        chains["thumb"] = resample(pts, 4)
    print("  %s: tip groups %s  thumb side %+.0f" % (side, [len(g) for g in groups], sgn))
    for n_, ch in chains.items():
        L = sum((ch[i + 1] - ch[i]).length for i in range(3))
        print("     %-7s tracked %2d pts, chain length %.4f m" % (n_, len(tracks[n_]), L))
    return F, chains

RESULT = {}
for side in ("R", "L"):
    RESULT[side] = build(side)

bpy.ops.object.mode_set(mode="OBJECT")
bpy.ops.object.mode_set(mode="EDIT")
inv = rig.matrix_world.inverted()
for side, (F, chains) in RESULT.items():
    for dname in DIGITS:
        if dname not in chains: continue
        pts = chains[dname]
        parent = rig.data.edit_bones["hand." + side]
        for i in range(3):
            eb = rig.data.edit_bones.new("%s.%02d.%s" % (dname, i + 1, side))
            eb.head = inv @ pts[i]
            eb.tail = inv @ pts[i + 1]
            eb.parent = parent
            eb.use_connect = False
            eb.use_deform = True
            parent = eb
bpy.ops.object.mode_set(mode="POSE")
PB = rig.pose.bones
print("bones now: %d (was 23)" % len(rig.data.bones))

# --- weights: redistribute ONLY what already sits on hand.R / hand.L ----------
def seg_dist(p, a, b):
    ab = b - a
    L2 = ab.length_squared
    s = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, (p - a).dot(ab) / L2))
    return (p - (a + ab * s)).length

for side, (F, chains) in RESULT.items():
    hg = obj.vertex_groups["hand." + side]
    for dname in chains:
        for i in (1, 2, 3):
            n = "%s.%02d.%s" % (dname, i, side)
            if n not in obj.vertex_groups: obj.vertex_groups.new(name=n)
    GI2 = {g.name: g.index for g in obj.vertex_groups}
    segs = {d: [(chains[d][i], chains[d][i + 1]) for i in range(3)]
            for d in DIGITS if d in chains}
    CAP = 0.013
    captured = {d: 0 for d in segs}
    for v in obj.data.vertices:
        w = wt(v, "hand." + side)
        if w <= 0.0: continue
        p = obj.matrix_world @ v.co
        best, bd = None, 1e9
        for dname in segs:
            d = min(seg_dist(p, a, b) for a, b in segs[dname])
            if d < bd: bd, best = d, dname
        if bd > CAP: continue
        inv_d = [1.0 / max(1e-4, seg_dist(p, a, b)) ** 2 for a, b in segs[best]]
        tot = sum(inv_d)
        for i, share in enumerate(inv_d, start=1):
            obj.vertex_groups["%s.%02d.%s" % (best, i, side)].add(
                [v.index], w * share / tot, "REPLACE")
        hg.add([v.index], 0.0, "REPLACE")
        captured[best] += 1
    print("  %s captured: %s" % (side, captured))

bpy.ops.object.mode_set(mode="OBJECT")
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", use_selection=False,
                          export_apply=False, export_morph=True, export_skins=True)
print("FINGERS_DONE", OUT)
