"""Smooth the jaw/neck blend band on the production mesh.

The band strains up to 80% under the head rotation a normal clip contains. It is
984 vertices spanning only 0.099 m with head weight running 0.01 to 0.944 -- a
steep gradient over a short distance, so any rotation concentrates the stretch
into a few edge loops.

This is a WEIGHTS change, not geometry: no vertex moves, nothing is sculpted or
retopologised. It widens the transition so the same rotation is shared across more
loops. Measured before and after against a fixed test rotation, and written to a
NEW file so the accepted bind is never overwritten in place.

  blender --background rv_bound.blend --python fix_neck_weights.py -- <out.blend> [iters]
"""
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector

A = sys.argv[sys.argv.index("--") + 1:]
OUT = A[0]
ITERS = int(A[1]) if len(A) > 1 else 12
HEAD, NECK = "DEF-spine.006", "DEF-spine.004"
TEST_DEG = 30.0

rig = next(o for o in bpy.data.objects if o.type == "ARMATURE" and o.name == "rv_rigify")
mesh = max([o for o in bpy.data.objects if o.type == "MESH" and len(o.vertex_groups)],
           key=lambda o: len(o.data.vertices))
gi = {g.name: g.index for g in mesh.vertex_groups}


def wt(v, g):
    return next((x.weight for x in v.groups if x.group == g), 0.0)


band = [v.index for v in mesh.data.vertices
        if wt(v, gi[HEAD]) > 0.01 and wt(v, gi[NECK]) > 0.01]
bandset = set(band)
edges = [e for e in mesh.data.edges
         if e.vertices[0] in bandset and e.vertices[1] in bandset]
print("band: %d verts, %d internal edges" % (len(band), len(edges)))


def deformed():
    dg = bpy.context.evaluated_depsgraph_get()
    ev = mesh.evaluated_get(dg)
    m = ev.to_mesh()
    co = [mesh.matrix_world @ m.vertices[i].co for i in range(len(m.vertices))]
    ev.to_mesh_clear()
    return co


def strain():
    """Worst edge stretch across the band for a fixed head rotation."""
    bpy.context.view_layer.objects.active = rig
    if rig.mode != "POSE":
        bpy.ops.object.mode_set(mode="POSE")
    pb = rig.pose.bones["head" if "head" in rig.pose.bones else HEAD]
    pb.rotation_mode = "XYZ"
    pb.rotation_euler = (0.0, 0.0, 0.0)
    bpy.context.view_layer.update()
    rest = deformed()
    base = [(rest[e.vertices[0]] - rest[e.vertices[1]]).length for e in edges]
    worst = 0.0
    for axis in (0, 2):                       # pitch and yaw of the head
        for sgn in (1.0, -1.0):
            r = [0.0, 0.0, 0.0]
            r[axis] = math.radians(TEST_DEG) * sgn
            pb.rotation_euler = tuple(r)
            bpy.context.view_layer.update()
            cur = deformed()
            for e, b in zip(edges, base):
                if b > 1e-6:
                    d = abs((cur[e.vertices[0]] - cur[e.vertices[1]]).length - b) / b
                    worst = max(worst, d)
    pb.rotation_euler = (0.0, 0.0, 0.0)
    bpy.context.view_layer.update()
    return worst * 100.0


before = strain()
print("band strain BEFORE: %.2f%% (head rotated +-%.0f deg, pitch and yaw)" % (before, TEST_DEG))

# --- smooth the two groups over the band ------------------------------------
bpy.ops.object.mode_set(mode="OBJECT")
bpy.context.view_layer.objects.active = mesh
mesh.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="DESELECT")
bpy.ops.object.mode_set(mode="OBJECT")
for i in band:
    mesh.data.vertices[i].select = True
bpy.ops.object.mode_set(mode="EDIT")
for gname in (HEAD, NECK):
    mesh.vertex_groups.active_index = gi[gname]
    bpy.ops.object.vertex_group_smooth(group_select_mode="ACTIVE",
                                       factor=0.5, repeat=ITERS, expand=0.25)
bpy.ops.object.mode_set(mode="OBJECT")
mesh.select_set(False)

# re-derive the band: smoothing widens it, which is the point
band2 = [v.index for v in mesh.data.vertices
         if wt(v, gi[HEAD]) > 0.01 and wt(v, gi[NECK]) > 0.01]
print("band after smoothing: %d verts (was %d)" % (len(band2), len(band)))

after = strain()
print("band strain AFTER:  %.2f%%" % after)
print("change: %.2f%% -> %.2f%%  (%.0f%% reduction)"
      % (before, after, 100.0 * (before - after) / max(before, 1e-6)))

# the face core must stay rigid -- smoothing must not bleed into it
core = [v for v in mesh.data.vertices
        if wt(v, gi[HEAD]) > 0.999 and wt(v, gi[NECK]) == 0.0]
print("face core verts still fully head-weighted: %d" % len(core))

bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("saved", OUT)
print("NECK_FIX_DONE")
