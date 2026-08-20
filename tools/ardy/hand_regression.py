"""Regression checks for hand curl direction and symmetry.

Both prior curl bugs would have been caught here. The direction test uses each
hand's OWN palm normal, derived from its own thumb mass -- measuring the left
hand against the right hand's normal is exactly how the mirrored-sign error was
introduced. Displacement is measured on the DEFORMED MESH, because a bone with
no weight moves nothing a player would see.

Importable: exec this file, then call run_checks(rig, mesh).
"""
import math
import bpy
from mathutils import Vector

CURL = {"01": 32, "02": 40, "03": 22}
WORKING = ("f_index", "f_middle", "f_ring")
SYM_TOL_MM = 2.0
MIN_TRAVEL_MM = 1.5


def run_checks(rig, mesh, verbose=True):
    PB = rig.pose.bones
    gi = {g.name: g.index for g in mesh.vertex_groups}
    fails = []

    def reset():
        for b in PB:
            b.rotation_mode = "XYZ"
            b.rotation_euler = (0, 0, 0); b.location = (0, 0, 0)
        bpy.context.view_layer.update()

    def palm_normal(s):
        reset()
        hm = rig.matrix_world @ PB["DEF-hand.%s" % s].matrix
        fg = (hm.to_3x3() @ Vector((0, 1, 0))).normalized()
        ti = [gi.get("DEF-thumb.%02d.%s" % (i, s)) for i in (1, 2, 3)]
        tv = [mesh.matrix_world @ v.co for v in mesh.data.vertices
              if any(g.group in ti and g.weight > 0.4 for g in v.groups)]
        fi = [gi.get("DEF-f_%s.%02d.%s" % (d, i, s))
              for d in ("index", "middle") for i in (1, 2)]
        fv = [mesh.matrix_world @ v.co for v in mesh.data.vertices
              if any(g.group in fi and g.weight > 0.4 for g in v.groups)]
        if not tv or not fv: return None
        d = (sum(tv, Vector()) / len(tv)) - (sum(fv, Vector()) / len(fv))
        return (d - fg * d.dot(fg)).normalized()

    def surf(d, s):
        idx = [gi.get("DEF-%s.%02d.%s" % (d, i, s)) for i in (1, 2, 3)]
        dg = bpy.context.evaluated_depsgraph_get()
        ev = mesh.evaluated_get(dg); m = ev.to_mesh()
        pts = [mesh.matrix_world @ m.vertices[v.index].co for v in mesh.data.vertices
               if any(g.group in idx and g.weight > 0.5 for g in v.groups)]
        ev.to_mesh_clear()
        return (sum(pts, Vector()) / len(pts)) if pts else None

    def travel(d, s, sign, n):
        reset(); a = surf(d, s)
        if a is None: return None
        for j, ang in CURL.items():
            nm = "%s.%s.%s" % (d, j, s)
            if nm in PB:
                PB[nm].rotation_mode = "XYZ"
                PB[nm].rotation_euler = (math.radians(ang * sign), 0, 0)
        bpy.context.view_layer.update()
        b = surf(d, s)
        return (b - a).dot(n) * 1000.0

    res = {}
    for s in ("R", "L"):
        n = palm_normal(s)
        if n is None:
            fails.append("hand %s: no thumb or finger surface to derive a palm normal" % s)
            continue
        for d in WORKING:
            c = travel(d, s, +1, n)
            h = travel(d, s, -1, n)
            res[(d, s)] = c
            if c is None:
                if verbose: print("   %s %s: NO SURFACE (unweighted digit)" % (s, d))
                continue
            if c < MIN_TRAVEL_MM:
                fails.append("curl on %s %s moves %+.1f mm; must move TOWARD the palm" % (s, d, c))
            if h is not None and h > -MIN_TRAVEL_MM:
                fails.append("hyperextension on %s %s moves %+.1f mm; must move AWAY" % (s, d, h))
            if verbose:
                print("   %s %-9s curl %+6.1f mm   hyperextend %+6.1f mm" % (s, d, c, h))
    for d in WORKING:
        a, b = res.get((d, "R")), res.get((d, "L"))
        if a is None or b is None: continue
        if abs(a - b) > SYM_TOL_MM:
            fails.append("asymmetry on %s: R %+.1f vs L %+.1f mm (>%.0f mm)"
                         % (d, a, b, SYM_TOL_MM))
        elif verbose:
            print("   symmetry %-9s R %+.1f vs L %+.1f  (delta %.1f mm)" % (d, a, b, abs(a - b)))
    reset()
    return (len(fails) == 0), fails


if __name__ == "__main__":
    rig = bpy.data.objects["rv_rigify"]
    mesh = max([o for o in bpy.data.objects if o.type == "MESH"],
               key=lambda o: len(o.data.vertices))
    print("HAND REGRESSION")
    ok, fails = run_checks(rig, mesh)
    for f in fails: print("   FAIL: %s" % f)
    print("REGRESSION %s" % ("PASS" if ok else "FAIL"))
