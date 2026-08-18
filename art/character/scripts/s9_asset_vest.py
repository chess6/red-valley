"""Convert the MPFB casualsuit05 jacket torso into the concept work vest.

Every removal is topological:
  * jeans / inner shirt go by deleting whole connected components;
  * sleeves go at their authored armhole ring, found by walking edge rings
    inward from each cuff boundary and taking the ring nearest the shoulder
    joint;
  * the body is shortened at a real ring walked up from the hem boundary.

No coordinate-threshold vertex deletion, no booleans, no cloth, no
shrinkwrap projection. The authored shoulders, seams, pockets and folds are
left untouched.
"""
import bpy, bmesh
from mathutils import Vector

SHOULDER = Vector((0.1677, -0.0146, 1.3436))
WRIST = Vector((0.4312, -0.1757, 1.0642))
WAIST_Z = 1.010          # target hem height; snapped to the nearest real ring


def mirror(v):
    return Vector((-v.x, v.y, v.z))


def components(bm):
    seen = set()
    out = []
    for v in bm.verts:
        if v.index in seen:
            continue
        stack = [v]
        mem = []
        while stack:
            x = stack.pop()
            if x.index in seen:
                continue
            seen.add(x.index)
            mem.append(x)
            for e in x.link_edges:
                o = e.other_vert(x)
                if o.index not in seen:
                    stack.append(o)
        out.append(mem)
    return out


def boundary_loops(bm):
    seen = set()
    loops = []
    for v in bm.verts:
        if not v.is_boundary or v.index in seen:
            continue
        stack = [v]
        loop = []
        while stack:
            x = stack.pop()
            if x.index in seen:
                continue
            seen.add(x.index)
            loop.append(x)
            for e in x.link_edges:
                if e.is_boundary:
                    o = e.other_vert(x)
                    if o.index not in seen:
                        stack.append(o)
        loops.append(loop)
    return loops


def rings_from(bm, seed):
    idx = {v.index: 0 for v in seed}
    frontier = list(seed)
    d = 0
    while frontier:
        d += 1
        nxt = []
        for v in frontier:
            for e in v.link_edges:
                o = e.other_vert(v)
                if o.index not in idx:
                    idx[o.index] = d
                    nxt.append(o)
        frontier = nxt
    return idx


def centre(vs):
    return sum((v.co for v in vs), Vector()) / len(vs)


def isolate_jacket(ob):
    """Keep only the largest component reaching shoulder height."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.verts.ensure_lookup_table()
    comps = components(bm)
    jacket = max((c for c in comps if max(v.co.z for v in c) > 1.30),
                 key=len, default=None)
    if jacket is None:
        bm.free()
        return {"error": "no jacket component"}
    keep = set(v.index for v in jacket)
    doomed = [v for v in bm.verts if v.index not in keep]
    bmesh.ops.delete(bm, geom=doomed, context='VERTS')
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()
    return {"kept_verts": len(ob.data.vertices), "components_removed": len(comps) - 1}


def remove_sleeves(ob):
    """Cut each sleeve at the authored armhole ring."""
    info = []
    for side, (sh, wr) in (("L", (SHOULDER, WRIST)),
                           ("R", (mirror(SHOULDER), mirror(WRIST)))):
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        bm.verts.ensure_lookup_table()
        loops = boundary_loops(bm)
        if not loops:
            bm.free()
            info.append({side: "no boundary"})
            continue
        cuff = min(loops, key=lambda l: (centre(l) - wr).length)
        if (centre(cuff) - wr).length > 0.26:
            bm.free()
            info.append({side: "no cuff near wrist"})
            continue
        ring = rings_from(bm, cuff)
        pos, cnt = {}, {}
        for v in bm.verts:
            r = ring.get(v.index)
            if r is None:
                continue
            pos[r] = pos.get(r, Vector()) + v.co
            cnt[r] = cnt.get(r, 0) + 1
        best, bd = None, None
        for r, p in pos.items():
            if cnt[r] < 5:
                continue
            d = ((p / cnt[r]) - sh).length
            if bd is None or d < bd:
                best, bd = r, d
        doomed = [f for f in bm.faces
                  if min((ring.get(v.index, 10**6) for v in f.verts)) < best]
        bmesh.ops.delete(bm, geom=doomed, context='FACES')
        bm.verts.ensure_lookup_table()
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces],
                         context='VERTS')
        bm.to_mesh(ob.data)
        bm.free()
        ob.data.update()
        info.append({side: {"armhole_ring": best, "err_mm": round(bd * 1000, 1)}})
    return info


def shorten_to_waist(ob, waist_z=WAIST_Z):
    """Trim the jacket skirt at a real ring walked up from the hem."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.verts.ensure_lookup_table()
    loops = boundary_loops(bm)
    if not loops:
        bm.free()
        return {"error": "no boundary"}
    hem = min(loops, key=lambda l: centre(l).z)
    ring = rings_from(bm, hem)
    pos, cnt = {}, {}
    for v in bm.verts:
        r = ring.get(v.index)
        if r is None:
            continue
        pos[r] = pos.get(r, Vector()) + v.co
        cnt[r] = cnt.get(r, 0) + 1
    best, bd = None, None
    for r, p in pos.items():
        if cnt[r] < 8:
            continue
        d = abs((p / cnt[r]).z - waist_z)
        if bd is None or d < bd:
            best, bd = r, d
    doomed = [f for f in bm.faces
              if min((ring.get(v.index, 10**6) for v in f.verts)) < best]
    bmesh.ops.delete(bm, geom=doomed, context='FACES')
    bm.verts.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces],
                     context='VERTS')
    bm.to_mesh(bm_mesh := ob.data)
    bm.free()
    ob.data.update()
    return {"hem_ring": best, "err_mm": round(bd * 1000, 1),
            "verts": len(ob.data.vertices)}


def health(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    r = {"verts": len(ob.data.vertices),
         "quads": sum(1 for f in bm.faces if len(f.verts) == 4),
         "tris": sum(1 for f in bm.faces if len(f.verts) == 3),
         "nonmanifold": sum(1 for e in bm.edges if len(e.link_faces) > 2),
         "boundary_edges": sum(1 for e in bm.edges if e.is_boundary),
         "irregular_boundary": sum(
             1 for v in bm.verts
             if v.is_boundary and len([e for e in v.link_edges if e.is_boundary]) != 2)}
    zs = [(ob.matrix_world @ v.co).z for v in ob.data.vertices]
    r["z"] = [round(min(zs), 3), round(max(zs), 3)]
    bm.free()
    return r
