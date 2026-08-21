"""Build a CC0 MPFB/MakeHuman control character.

Purpose (docs/ASSET_BLOCKERS.md, option B): the Rodin mesh's hands are a fused
mass, and four separate attempts to recover per-digit weights failed. That leaves
one question unanswered -- are the finger defects caused by the TOPOLOGY, or by
our binding? A body with known-clean, documented topology answers it, because if
the same pipeline produces clean digits here then the pipeline is fine and the
mesh is the problem.

This is a TEST ASSET, not a replacement character. MakeHuman's base mesh and
system assets are CC0, so it carries no licence risk.

  blender --background --python build_mpfb_control.py -- <outdir>
"""
import importlib
import os
import sys

import bpy

OUT = sys.argv[sys.argv.index("--") + 1:][0]
os.makedirs(OUT, exist_ok=True)

MPFB = "bl_ext.user_default.mpfb"
HumanService = importlib.import_module(MPFB + ".services.humanservice").HumanService
try:
    ObjectService = importlib.import_module(MPFB + ".services.objectservice").ObjectService
except Exception:
    ObjectService = None

bpy.ops.wm.read_factory_settings(use_empty=True)

print("creating base human ...")
basemesh = HumanService.create_human()
print("  created:", basemesh.name, "verts", len(basemesh.data.vertices))

# The default MakeHuman base is androgynous and unscaled; we only care about
# topology here, so no shaping is applied. Anything else would be art authoring.
bpy.context.view_layer.objects.active = basemesh
basemesh.select_set(True)

print("adding the default (deform) rig ...")
try:
    HumanService.add_builtin_rig(basemesh, "default")
    print("  builtin rig added")
except Exception as e:
    print("  add_builtin_rig failed (%s); trying operator" % e)
    try:
        bpy.ops.mpfb.add_standard_rig()
    except Exception as e2:
        print("  operator also failed:", e2)

arm = next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)
print("armature:", arm.name if arm else "NONE",
      "bones:", len(arm.data.bones) if arm else 0)

# ---- the measurement this asset exists for --------------------------------
def digit_report(mesh):
    groups = {g.name: g.index for g in mesh.vertex_groups}
    fingers = {}
    for gname, gi in groups.items():
        low = gname.lower()
        if any(k in low for k in ("finger", "thumb", "index", "middle", "ring", "pinky")):
            n = sum(1 for v in mesh.data.vertices
                    if any(g.group == gi and g.weight > 0.5 for g in v.groups))
            fingers[gname] = n
    return fingers

if arm:
    fr = digit_report(basemesh)
    named = sorted(fr.items())
    print("\ndigit-bearing vertex groups: %d" % len(named))
    for n, c in named[:24]:
        print("   %-28s %4d verts weighted > 0.5" % (n, c))
    unweighted = [n for n, c in named if c == 0]
    print("groups with ZERO dominant verts: %d %s"
          % (len(unweighted), unweighted[:6]))
    print("VERDICT digits_separable: %s" % (len(named) > 0 and not unweighted))

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "mpfb_control.blend"))
print("saved", os.path.join(OUT, "mpfb_control.blend"))
print("MPFB_CONTROL_DONE")
