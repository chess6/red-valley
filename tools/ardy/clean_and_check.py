"""Drop the superseded legacy vertex groups and measure the thumb properly.

  blender --background <rv_bound.blend> --python clean_and_check.py -- <out.blend>
"""
import collections, sys
import bpy
from mathutils import Vector

OUT = sys.argv[sys.argv.index("--") + 1:][0]
rig = bpy.data.objects["rv_rigify"]
mesh = max([o for o in bpy.data.objects if o.type == "MESH"],
           key=lambda o: len(o.data.vertices))

legacy = [g.name for g in mesh.vertex_groups if not g.name.startswith("DEF-")]
for n in legacy: mesh.vertex_groups.remove(mesh.vertex_groups[n])
print("removed %d legacy groups from the old rig: %s..." % (len(legacy), legacy[:6]))

GI = {g.name: g.index for g in mesh.vertex_groups}
GN = {i: n for n, i in GI.items()}
def dom(v):
    return GN.get(max(v.groups, key=lambda g: g.weight).group) if v.groups else None
def share(v, key):
    t = sum(g.weight for g in v.groups)
    if t <= 0: return 0.0
    return sum(g.weight for g in v.groups if key in GN.get(g.group, "")) / t

for side in ("R", "L"):
    tv = [v for v in mesh.data.vertices if (dom(v) or "").startswith("DEF-thumb") and
          (dom(v) or "").endswith(side)]
    if not tv:
        print("THUMB.%s: 0 vertices dominated by a thumb bone -- FAILED" % side); continue
    fa = sum(1 for v in tv if share(v, "forearm") > 0.25)
    avg = sum(share(v, "forearm") for v in tv) / len(tv)
    print("THUMB.%s: %d verts dominated by thumb bones; mean forearm share %.3f; "
          "%d with forearm >0.25" % (side, len(tv), avg, fa))

cnt = collections.Counter()
for v in mesh.data.vertices:
    d = dom(v)
    if d: cnt[d] += 1
fing = {k: c for k, c in cnt.items()
        if any(x in k for x in ("thumb", "f_index", "f_middle", "f_ring", "f_pinky"))}
print("DIGIT-dominated vertices: %d across %d bones" % (sum(fing.values()), len(fing)))
for d in ("thumb", "f_index", "f_middle", "f_ring", "f_pinky"):
    R = sum(c for k, c in fing.items() if d in k and k.endswith(".R"))
    L = sum(c for k, c in fing.items() if d in k and k.endswith(".L"))
    print("   %-9s R=%-5d L=%-5d" % (d, R, L))
print("groups now: %d (all DEF-)" % len(mesh.vertex_groups))
nw = sum(1 for v in mesh.data.vertices if not v.groups)
print("unweighted verts: %d" % nw)
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("CLEAN_DONE")
