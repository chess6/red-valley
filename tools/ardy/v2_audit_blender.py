"""v2 audit, Blender half: findings 6 (socket tilt causes the wrist collision)
and 7 (spout height), plus the split face gate that replaces the misleading
aggregate 'face deviation' number.

  blender --background water_can.blend --python v2_audit_blender.py -- <out.json>
"""
import json, math, os, sys
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

OUT = sys.argv[sys.argv.index("--") + 1:][0]
SOIL = 0.22
rig = bpy.data.objects["rv_rigify"]
can = [o for o in bpy.data.objects if o.type == "MESH" and "can" in o.name.lower()][0]
mesh = max([o for o in bpy.data.objects if o.type == "MESH" and o is not can],
           key=lambda o: len(o.data.vertices))
META = json.load(open("art/animation/ardy_pilot/proxy/watering_can_proxy.json"))
TIP = Vector(META["markers"]["spout_tip"])
PB = rig.pose.bones
sc = bpy.context.scene
def upd(): bpy.context.view_layer.update()

GIx = {g.name: g.index for g in mesh.vertex_groups}
GN = {i: n for n, i in GIx.items()}
mesh.data.calc_loop_triangles()
def dom(vi):
    v = mesh.data.vertices[vi]
    return GN.get(max(v.groups, key=lambda g: g.weight).group) if v.groups else None
HANDK = ("DEF-hand.R", "DEF-f_", "DEF-thumb", "DEF-palm")
NONHAND = [t for t in mesh.data.loop_triangles
           if not any((dom(i) or "").startswith(HANDK) for i in t.vertices)]

def overlaps():
    dg = bpy.context.evaluated_depsgraph_get()
    ev = mesh.evaluated_get(dg); m = ev.to_mesh()
    co = [mesh.matrix_world @ v.co for v in m.vertices]
    bt = BVHTree.FromPolygons(co, [tuple(t.vertices) for t in NONHAND], all_triangles=True)
    cev = can.evaluated_get(dg); cm = cev.to_mesh(); cm.calc_loop_triangles()
    ct = BVHTree.FromPolygons([can.matrix_world @ v.co for v in cm.vertices],
                              [tuple(t.vertices) for t in cm.loop_triangles], all_triangles=True)
    ov = ct.overlap(bt)
    parts = {}
    for _ci, bi in ov:
        for vi in NONHAND[bi].vertices:
            n = dom(vi)
            parts[n] = parts.get(n, 0) + 1
    ev.to_mesh_clear(); cev.to_mesh_clear()
    return len(ov), parts

res = {}
# --- F6: is the socket tilt the cause? measure with and without it ----------
POUR_F = 73
sc.frame_set(POUR_F); upd()
n_with, parts_with = overlaps()
tip_with = can.matrix_world @ TIP
sock = PB["prop_socket.R"]
saved = tuple(sock.rotation_euler)
sock.rotation_euler = (0.0, 0.0, 0.0); upd()
n_without, parts_without = overlaps()
tip_without = can.matrix_world @ TIP
sock.rotation_euler = saved; upd()
res["F6_socket_tilt_causes_collision"] = {
    "pour_frame": POUR_F,
    "socket_tilt_deg": round(math.degrees(saved[1]), 2),
    "with_tilt": {"overlap_tris": n_with, "by_bone": parts_with,
                  "spout_above_bed_m": round(tip_with.z - SOIL, 4)},
    "without_tilt": {"overlap_tris": n_without, "by_bone": parts_without,
                     "spout_above_bed_m": round(tip_without.z - SOIL, 4)},
    "confirmed": n_with > 0 and n_without == 0,
}

# --- F7: spout height vs the documented 0.15-0.30 m band --------------------
heights = []
for f in range(56, 97):
    sc.frame_set(f); upd()
    heights.append((can.matrix_world @ TIP).z - SOIL)
res["F7_spout_height"] = {
    "documented_band_m": [0.15, 0.30],
    "pour_window_frames": [56, 96],
    "min_m": round(min(heights), 4), "max_m": round(max(heights), 4),
    "mean_m": round(sum(heights) / len(heights), 4),
    "in_band": all(0.15 <= h <= 0.30 for h in heights),
    "excess_over_band_m": round(min(heights) - 0.30, 4),
    "confirmed": not all(0.15 <= h <= 0.30 for h in heights),
}

# --- E: split face gate — rigid core landmarks vs the jaw/neck blend band ---
head_i = GIx.get("DEF-spine.006")
neck_i = GIx.get("DEF-spine.004")
def wts(v, gi):
    return next((g.weight for g in v.groups if g.group == gi), 0.0)
core, band = [], []
for v in mesh.data.vertices:
    hw, nw = wts(v, head_i), wts(v, neck_i)
    if hw > 0.999 and nw == 0.0: core.append(v.index)     # pure head: must be rigid
    elif hw > 0.01 and nw > 0.01: band.append(v.index)    # deliberate blend band
core_s, band_s = set(core), set(band)
def edges_of(s):
    return [e for e in mesh.data.edges if e.vertices[0] in s and e.vertices[1] in s][:4000]
ec, eb = edges_of(core_s), edges_of(band_s)
def coords():
    dg = bpy.context.evaluated_depsgraph_get(); ev = mesh.evaluated_get(dg); m = ev.to_mesh()
    r = [mesh.matrix_world @ m.vertices[i].co for i in range(len(m.vertices))]
    ev.to_mesh_clear(); return r
sc.frame_set(1); upd(); c0 = coords()
base_c = [(c0[e.vertices[0]] - c0[e.vertices[1]]).length for e in ec]
base_b = [(c0[e.vertices[0]] - c0[e.vertices[1]]).length for e in eb]
worst_c = worst_b = 0.0
for f in (1, 40, 73, 96, 120, 160):
    sc.frame_set(f); upd(); cc = coords()
    if base_c:
        worst_c = max(worst_c, max(abs((cc[e.vertices[0]] - cc[e.vertices[1]]).length - b) / b
                                   for e, b in zip(ec, base_c) if b > 1e-6))
    if base_b:
        worst_b = max(worst_b, max(abs((cc[e.vertices[0]] - cc[e.vertices[1]]).length - b) / b
                                   for e, b in zip(eb, base_b) if b > 1e-6))
res["E_face_gate_split"] = {
    "rigid_core_verts": len(core), "blend_band_verts": len(band),
    "core_worst_edge_strain_pct": round(worst_c * 100, 4),
    "band_worst_edge_strain_pct": round(worst_b * 100, 4),
    "core_gate_pass_lt_0p5pct": worst_c * 100 < 0.5,
    "note": ("the old aggregate gate mixed these two populations, so blend-band "
             "strain (expected) masqueraded as face deformation (unacceptable)"),
}
json.dump(res, open(OUT, "w"), indent=2)
print(json.dumps(res, indent=2))
print("V2_AUDIT_BLENDER_DONE")
