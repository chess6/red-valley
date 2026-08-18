"""Shorten the shirt sleeves to just below the elbow, topologically.

The cut lands on an EXISTING edge ring, found by walking the quad tube inward
from the sleeve's own cuff boundary. Nothing is selected by coordinate
threshold, so the resulting boundary is a single continuous loop with no torn
edges and no damage to unrelated geometry.

Then the boundary ring is extruded twice to form a rolled cuff with real
thickness and a modest fold.
"""
import bpy, bmesh
from mathutils import Vector

ELBOW = Vector((0.3129, -0.0132, 1.1683))
WRIST = Vector((0.4312, -0.1757, 1.0642))
CUT_T = 0.30          # along elbow -> wrist; 0.3 == just below the elbow


def mirror(v):
    return Vector((-v.x, v.y, v.z))


def boundary_loops(bm):
    """Group boundary vertices into connected loops."""
    seen = set()
    loops = []
    for v in bm.verts:
        if not v.is_boundary or v.index in seen:
            continue
        loop = []
        stack = [v]
        while stack:
            x = stack.pop()
            if x.index in seen:
                continue
            seen.add(x.index)
            loop.append(x)
            for e in x.link_edges:
                if not e.is_boundary:
                    continue
                o = e.other_vert(x)
                if o.index not in seen:
                    stack.append(o)
        loops.append(loop)
    return loops


def ring_index_from(bm, seed_verts):
    """Topological distance (in edges) from a seed loop -- constant values form
    the quad tube's edge rings."""
    idx = {v.index: 0 for v in seed_verts}
    frontier = list(seed_verts)
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


def shorten_sleeve(obj, elbow, wrist, cut_t=CUT_T, roll=True):
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()

    target = elbow + (wrist - elbow) * cut_t
    # the cuff loop is the boundary loop nearest this arm's wrist
    loops = boundary_loops(bm)
    if not loops:
        bm.free()
        return {"error": "no boundary loops on shirt"}
    def loop_centre(l):
        return sum((v.co for v in l), Vector()) / len(l)
    cuff = min(loops, key=lambda l: (loop_centre(l) - wrist).length)
    if (loop_centre(cuff) - wrist).length > 0.22:
        bm.free()
        return {"error": "no cuff loop near this wrist",
                "nearest": round((loop_centre(cuff) - wrist).length, 3)}

    ring = ring_index_from(bm, cuff)
    # average position per ring, then pick the ring nearest the cut plane
    pos, cnt = {}, {}
    for v in bm.verts:
        r = ring.get(v.index)
        if r is None:
            continue
        pos[r] = pos.get(r, Vector()) + v.co
        cnt[r] = cnt.get(r, 0) + 1
    best_r, best_d = None, None
    for r, p in pos.items():
        if cnt[r] < 6:            # ignore stray fans, keep true rings
            continue
        c = p / cnt[r]
        d = (c - target).length
        if best_d is None or d < best_d:
            best_r, best_d = r, d

    # drop every face that reaches nearer the cuff than the chosen ring
    doomed = [f for f in bm.faces
              if min((ring.get(v.index, 10 ** 6) for v in f.verts)) < best_r]
    bmesh.ops.delete(bm, geom=doomed, context='FACES')
    bm.verts.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')

    info = {"cut_ring": best_r, "ring_err_mm": round(best_d * 1000, 1),
            "faces_removed": len(doomed)}

    if roll:
        # the new boundary near the cut is the cuff edge; roll it outward+back
        axis = (wrist - elbow).normalized()
        loops2 = boundary_loops(bm)
        if loops2:
            cuff2 = min(loops2, key=lambda l: (loop_centre(l) - target).length)
            edges = [e for e in bm.edges if e.is_boundary and
                     e.verts[0] in cuff2 and e.verts[1] in cuff2]
            if edges:
                centre = loop_centre(cuff2)
                def radial(v):
                    r = v.co - (centre + axis * ((v.co - centre).dot(axis)))
                    return r.normalized() if r.length > 1e-6 else Vector((0, 0, 1))
                ex = bmesh.ops.extrude_edge_only(bm, edges=edges)
                nv = [g for g in ex["geom"] if isinstance(g, bmesh.types.BMVert)]
                for v in nv:                       # outward flare + toward wrist
                    v.co += radial(v) * 0.010 + axis * 0.014
                ne = [g for g in ex["geom"] if isinstance(g, bmesh.types.BMEdge) and g.is_boundary]
                ex2 = bmesh.ops.extrude_edge_only(bm, edges=ne)
                nv2 = [g for g in ex2["geom"] if isinstance(g, bmesh.types.BMVert)]
                for v in nv2:                      # fold back up the arm = roll
                    v.co += radial(v) * 0.002 - axis * 0.020
                info["roll_verts"] = len(nv) + len(nv2)

    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    me.update()
    return info


def run():
    shirt = bpy.data.objects["RV_Shirt"]
    res = {}
    for side, (el, wr) in (("L", (ELBOW, WRIST)),
                           ("R", (mirror(ELBOW), mirror(WRIST)))):
        res[side] = shorten_sleeve(shirt, el, wr)
    # report boundary health
    bm = bmesh.new(); bm.from_mesh(shirt.data)
    res["boundary_verts"] = sum(1 for v in bm.verts if v.is_boundary)
    res["irregular"] = sum(1 for v in bm.verts
                           if v.is_boundary and
                           len([e for e in v.link_edges if e.is_boundary]) != 2)
    res["nonmanifold"] = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    res["verts"] = len(shirt.data.vertices)
    bm.free()
    return res
