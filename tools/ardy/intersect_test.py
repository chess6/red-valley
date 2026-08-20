"""Per-frame mesh self-intersection test: arm geometry vs torso/clothing.

Lateral clearance is not sufficient -- an arm can be laterally clear and still
pass through the belly, or laterally close and still be in front of the body.
This evaluates the actual deformed mesh each frame, splits vertices by dominant
bone weight, and tests whether arm vertices lie INSIDE the torso surface using
the nearest-surface normal test.

  blender --background --python intersect_test.py -- <rigged.glb> [step]
"""
import json, sys
import bpy, mathutils
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:]
GLB = argv[0]
STEP = int(argv[1]) if len(argv) > 1 else 2

ARM = {"forearm.R", "forearm.L", "hand.R", "hand.L"}
TORSO = {"hips", "spine", "chest"}

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)
rig = [o for o in bpy.data.objects if o.type == "ARMATURE"][0]
# pick the skinned character, not whatever mesh happens to be first
cands = [o for o in bpy.data.objects if o.type == "MESH" and len(o.vertex_groups)]
if not cands:
    raise SystemExit("no skinned mesh found")
obj = max(cands, key=lambda o: len(o.data.vertices))
print("testing mesh:", obj.name, len(obj.data.vertices), "verts")
gname = {g.index: g.name for g in obj.vertex_groups}

arm_v, torso_v = [], []
for v in obj.data.vertices:
    if not v.groups: continue
    top = max(v.groups, key=lambda g: g.weight)
    n = gname.get(top.group)
    if top.weight < 0.5: continue
    if n in ARM: arm_v.append(v.index)
    elif n in TORSO: torso_v.append(v.index)
torso_set, arm_set = set(torso_v), set(arm_v)
obj.data.calc_loop_triangles()
torso_tris, arm_tris = [], []
for t in obj.data.loop_triangles:
    vs = tuple(t.vertices)
    if all(i in torso_set for i in vs): torso_tris.append(vs)
    elif all(i in arm_set for i in vs): arm_tris.append(vs)
print("arm verts: %d | torso verts: %d | arm tris: %d | torso tris: %d"
      % (len(arm_v), len(torso_v), len(arm_tris), len(torso_tris)))

act = rig.animation_data.action
f0, f1 = (int(round(v)) for v in act.frame_range)
dg = bpy.context.evaluated_depsgraph_get()

worst = {"frame": None, "pairs": 0}
frames = []
for f in range(f0, f1 + 1, STEP):
    bpy.context.scene.frame_set(f)
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    m = ev.to_mesh()
    co = [v.co.copy() for v in m.vertices]
    # True surface-vs-surface test: overlapping triangle pairs between the arm
    # shell and the torso shell. Needs no closed volume, unlike a normal test,
    # which misclassifies on an open patch.
    bvh_t = BVHTree.FromPolygons(co, torso_tris, all_triangles=True)
    bvh_a = BVHTree.FromPolygons(co, arm_tris, all_triangles=True)
    pairs = bvh_a.overlap(bvh_t)
    frames.append({"frame": f, "pairs": len(pairs)})
    if len(pairs) > worst["pairs"]:
        worst = {"frame": f, "pairs": len(pairs)}
    ev.to_mesh_clear()

bad = [x for x in frames if x["pairs"] > 0]
print(json.dumps({"frames_tested": len(frames),
                  "frames_with_intersection": len(bad),
                  "pct_frames_clean": round(100 * (1 - len(bad) / max(1, len(frames))), 1),
                  "worst": worst}, indent=2))
for x in bad[:12]:
    print("   frame %3d: %d intersecting triangle pairs" % (x["frame"], x["pairs"]))
