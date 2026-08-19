"""Acceptance tests for ARDY pilot clips, per docs/SKELETON_SPEC.md.

Measures the criteria numerically rather than by eye. Runs against a rigged
GLB that may or may not carry animation; with no animation it degrades to a
rest-pose report, which is a useful smoke test of the harness itself.

  blender --background --python tools/ardy/acceptance.py -- <rigged.glb> <can.glb> [clip]

Criteria (SKELETON_SPEC.md):
  walk_fwd  : root translation zero; foot slide < 3 cm/step at 4.3 m/s; loops
  water_can : grip holds without drift; spout within +-5 cm of soil at 0.45 s
"""
import json, math, os, sys
import bpy, mathutils

argv = sys.argv[sys.argv.index("--") + 1:]
RIG_GLB, CAN_GLB = argv[0], argv[1]
CLIP = argv[2] if len(argv) > 2 else "auto"

TOL_POS = 0.05          # +-5 cm alignment tolerance
SOIL_HEIGHT = 0.22      # plot bed top, metres (src/world/plot.gd PLOT_SIZE bed)
WALK_SPEED = 4.3
SYNC_WATER = 0.45       # seconds

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=RIG_GLB)
rig = [o for o in bpy.data.objects if o.type == "ARMATURE"][0]
mesh = [o for o in bpy.data.objects if o.type == "MESH"][0]

before = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=CAN_GLB)
can = [o for o in bpy.data.objects if o not in before and o.type == "MESH"][0]
meta = json.load(open(CAN_GLB.replace(".glb", ".json")))
OFF = {k: mathutils.Vector(v) for k, v in meta["markers"].items()}

can.parent = rig
can.parent_type = "BONE"
can.parent_bone = "prop_socket.R"
bpy.context.view_layer.update()
BONE_FROM_PROP = mathutils.Matrix.Rotation(math.radians(90), 4, "X")

def place_can():
    sock = rig.matrix_world @ rig.pose.bones["prop_socket.R"].matrix
    can.matrix_world = sock @ BONE_FROM_PROP

def world(name):
    """Read from the DEPSGRAPH-EVALUATED rig: rig.pose on the original object is
    not updated by frame_set alone, which silently yields identical poses on
    every frame (and therefore a meaningless 0.0 for every measurement)."""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = rig.evaluated_get(dg)
    return (ev.matrix_world @ ev.pose.bones[name].matrix).to_translation()

action = rig.animation_data.action if rig.animation_data else None
if action:
    f0, f1 = (int(round(v)) for v in action.frame_range)
else:
    f0 = f1 = bpy.context.scene.frame_current
fps = bpy.context.scene.render.fps
frames = list(range(f0, f1 + 1))
print("clip frames: %d-%d @ %d fps (%.2f s)" % (f0, f1, fps, (f1 - f0) / max(1, fps)))

samples = []
for f in frames:
    bpy.context.scene.frame_set(f)
    bpy.context.view_layer.update()
    bpy.context.evaluated_depsgraph_get().update()
    place_can()
    bpy.context.view_layer.update()
    samples.append({
        "f": f,
        "root": world("root").copy(),
        "hips": world("hips").copy(),
        "foot.L": world("foot.L").copy(),
        "foot.R": world("foot.R").copy(),
        "socket": world("prop_socket.R").copy(),
        "grip": (can.matrix_world @ OFF["grip_origin"]).copy(),
        "spout": (can.matrix_world @ OFF["spout_tip"]).copy(),
    })

results = {}

# --- root motion: must be in-place
root_delta = max((s["root"] - samples[0]["root"]).length for s in samples)
results["root_translation_max_m"] = round(root_delta, 5)
results["root_in_place"] = root_delta < 1e-4

# --- grip integrity: the can must not slide out of the hand
grip_drift = max((s["grip"] - s["socket"]).length for s in samples)
results["grip_to_socket_max_m"] = round(grip_drift, 5)
results["grip_holds"] = grip_drift < 1e-3

# --- foot sliding: planted foot should not skate
def slide(side):
    worst = 0.0
    for a, b in zip(samples, samples[1:]):
        pa, pb = a["foot." + side], b["foot." + side]
        if min(pa.z, pb.z) < 0.06:                    # treat as planted
            worst = max(worst, (mathutils.Vector((pb.x - pa.x, pb.y - pa.y, 0))).length)
    return worst
if len(samples) > 1:
    results["foot_slide_max_per_frame_m"] = round(max(slide("L"), slide("R")), 5)
    per_step = results["foot_slide_max_per_frame_m"] * fps / max(1e-6, WALK_SPEED)
    results["foot_slide_ok"] = results["foot_slide_max_per_frame_m"] < 0.03
else:
    results["foot_slide_max_per_frame_m"] = None

# --- loop seam (locomotion only)
if len(samples) > 2:
    seam = (samples[-1]["hips"] - samples[0]["hips"]).length
    results["loop_seam_hips_m"] = round(seam, 5)

# --- spout alignment at the water sync point
sync_f = f0 + int(round(SYNC_WATER * fps))
s = min(samples, key=lambda x: abs(x["f"] - sync_f))
results["spout_at_sync"] = {
    "frame": s["f"],
    "world": [round(v, 4) for v in s["spout"]],
    "height_above_soil_m": round(s["spout"].z - SOIL_HEIGHT, 4),
    "within_tolerance": abs(s["spout"].z - SOIL_HEIGHT) <= TOL_POS,
}

print(json.dumps(results, indent=2))
verdict = []
if not results["root_in_place"]:
    verdict.append("FAIL root motion present (must be in-place)")
if not results["grip_holds"]:
    verdict.append("FAIL grip drifts from socket")
if results.get("foot_slide_max_per_frame_m") and not results.get("foot_slide_ok"):
    verdict.append("FAIL foot sliding above 3 cm")
print("VERDICT:", "; ".join(verdict) if verdict else "all measured criteria pass")
