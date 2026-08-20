"""Locate each digit's centreline from the WELDED surface's own topology.

Segmenting on the raw glTF mesh fails: it splits vertices at UV/normal seams, so
the hand is topologically disconnected (largest component above the knuckle was
87 of ~500 verts). Welding collapses 70,042 verts to 24,980 and restores
connectivity, after which a cut plane separates the digits exactly.

  blender --background --python digit_sections.py -- <src.glb> <json_out>
"""
import json, math, os, sys
import bpy, bmesh
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
SRC, JOUT = argv[0], argv[1]

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=SRC)
rig = [o for o in bpy.data.objects if o.type == "ARMATURE"][0]
mesh = max([o for o in bpy.data.objects if o.type == "MESH" and len(o.vertex_groups)],
           key=lambda o: len(o.data.vertices))
if mesh.data.shape_keys:
    bpy.context.view_layer.objects.active = mesh
    mesh.shape_key_clear()
bm = bmesh.new(); bm.from_mesh(mesh.data)
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
bm.to_mesh(mesh.data); bm.free(); mesh.data.update()
print("welded to %d verts" % len(mesh.data.vertices))

GI = {g.name: g.index for g in mesh.vertex_groups}
def wt(v, n):
    i = GI.get(n)
    return next((g.weight for g in v.groups if g.group == i), 0.0) if i is not None else 0.0

def frame(side):
    hv = [v for v in mesh.data.vertices if wt(v, "hand." + side) >= 0.4]
    co = [mesh.matrix_world @ v.co for v in hv]
    hm = rig.matrix_world @ rig.data.bones["hand." + side].matrix_local
    fg = (hm.to_3x3() @ Vector((0, 1, 0))).normalized(); o = hm.to_translation()
    t = [(c - o).dot(fg) for c in co]; lo, hi = min(t), max(t)
    palm = [c for c, tt in zip(co, t) if lo + .20 * (hi - lo) <= tt <= lo + .55 * (hi - lo)]
    pc = sum(palm, Vector()) / len(palm)
    u = Vector((0, 0, 1)).cross(fg)
    if u.length < 1e-6: u = Vector((1, 0, 0)).cross(fg)
    u.normalize(); v2 = fg.cross(u).normalized()
    sxx = syy = sxy = 0.0
    for c in palm:
        d = c - pc; a, b = d.dot(u), d.dot(v2)
        sxx += a * a; syy += b * b; sxy += a * b
    th = .5 * math.atan2(2 * sxy, sxx - syy)
    e1 = (u * math.cos(th) + v2 * math.sin(th)).normalized(); e2 = fg.cross(e1).normalized()
    v1 = sum(((c - pc).dot(e1)) ** 2 for c in palm)
    vv = sum(((c - pc).dot(e2)) ** 2 for c in palm)
    br, nr = (e1, e2) if v1 > vv else (e2, e1)
    if nr.dot(Vector((0, -1, 0))) < 0: nr = -nr
    return dict(cen=sum(co, Vector()) / len(co), bar=br, nrm=nr, fing=fg,
                o=o, lo=lo, hi=hi)

ADJ = {}
for e in mesh.data.edges:
    a, b = e.vertices
    ADJ.setdefault(a, []).append(b); ADJ.setdefault(b, []).append(a)

def components(idxs):
    idxs = set(idxs); seen = set(); out = []
    for s in idxs:
        if s in seen: continue
        stack, comp = [s], []
        seen.add(s)
        while stack:
            x = stack.pop(); comp.append(x)
            for y in ADJ.get(x, ()):
                if y in idxs and y not in seen:
                    seen.add(y); stack.append(y)
        out.append(comp)
    return sorted(out, key=len, reverse=True)

RESULT = {}
for side in ("R", "L"):
    F = frame(side)
    cen, BAR, NRM, FING = F["cen"], F["bar"], F["nrm"], F["fing"]
    sgn = 1.0 if side == "R" else -1.0
    region = []
    for v in mesh.data.vertices:
        p = mesh.matrix_world @ v.co
        if (p - cen).length > 0.090: continue
        if (p - F["o"]).dot(FING) < F["lo"] - 0.006: continue
        if wt(v, "hand." + side) >= 0.40 or wt(v, "forearm." + side) >= 0.40:
            region.append(v.index)
    P = {i: mesh.matrix_world @ mesh.data.vertices[i].co for i in region}
    def coord(i):
        d = P[i] - cen
        return (d.dot(BAR) * 1000.0 * sgn, d.dot(NRM) * 1000.0, d.dot(FING) * 1000.0)
    print("=== hand %s: region %d verts (welded) ===" % (side, len(region)))
    best = None
    for cut in range(-6, 22, 2):
        sel = [i for i in region if coord(i)[2] > cut]
        comps = [c for c in components(sel) if len(c) >= 12]
        if len(comps) == 4 and (best is None or len(sel) > best[1]):
            best = (cut, len(sel), comps)
        print("   cut fing>%+3d : %d comps sizes %s"
              % (cut, len(comps), [len(c) for c in comps[:6]]))
    if not best:
        print("   NO CLEAN 4-DIGIT CUT for %s" % side); continue
    cut, _, comps = best
    comps.sort(key=lambda c: sum(coord(i)[0] for i in c) / len(c))
    names = ["f_pinky", "f_ring", "f_middle", "f_index"]
    digits = {}
    for nm, comp in zip(names, comps):
        fs = [coord(i)[2] for i in comp]
        lo_, hi_ = min(fs), max(fs)
        stations = []
        for k in range(5):
            z = lo_ + (hi_ - lo_) * k / 4.0
            sl = [i for i in comp if abs(coord(i)[2] - z) <= max(2.5, (hi_ - lo_) / 8.0)]
            if len(sl) < 3: continue
            b = sum(coord(i)[0] for i in sl) / len(sl)
            n = sum(coord(i)[1] for i in sl) / len(sl)
            f = sum(coord(i)[2] for i in sl) / len(sl)
            stations.append([round(b, 1), round(n, 1), round(f, 1), len(sl)])
        digits[nm] = stations
        print("   %-9s %d verts, fing %.0f..%.0f, centres %s"
              % (nm, len(comp), lo_, hi_, stations))
    RESULT[side] = dict(cut=cut, digits=digits,
                        cen=[round(x, 6) for x in cen],
                        bar=[round(x, 6) for x in BAR],
                        nrm=[round(x, 6) for x in NRM],
                        fing=[round(x, 6) for x in FING])
json.dump(RESULT, open(JOUT, "w"), indent=2)
print("SECTIONS_DONE")
