"""Reshape the CC-BY biker boot into a practical brown mid-ankle work boot.

The asset's construction (outsole, welt, upper panels, straps, buckles) is
kept intact: nothing is deleted. The shaft is *compressed* along Z with a
piecewise remap, so every loop, seam and hard-surface detail survives and the
UVs stay valid -- only the proportions change.

    z <= KEEP_Z            unchanged   (outsole, welt, toe box, vamp)
    KEEP_Z .. shaft top    compressed into KEEP_Z .. TARGET_TOP

Attribution for this asset is recorded in SOURCE_LICENSES.md (CC-BY, Mindfront).
"""
import bpy, bmesh
from mathutils import Vector

KEEP_Z = 0.105          # everything below this is real footwear structure
TARGET_TOP = 0.190      # mid-ankle
SHAFT_WIDEN = 1.06      # let the jean leg sit inside the shaft


def measure(obj):
    zs = [(obj.matrix_world @ v.co).z for v in obj.data.vertices]
    return min(zs), max(zs)


def reshape(obj, keep_z=KEEP_Z, target_top=TARGET_TOP, widen=SHAFT_WIDEN):
    lo, hi = measure(obj)
    if hi <= keep_z:
        return {"skipped": "already short"}
    scale = (target_top - keep_z) / (hi - keep_z)

    # per-foot centre, so widening pushes outward from each boot's own axis
    xs = [v.co.x for v in obj.data.vertices]
    cx = {1: sum(x for x in xs if x > 0) / max(1, sum(1 for x in xs if x > 0)),
          -1: sum(x for x in xs if x < 0) / max(1, sum(1 for x in xs if x < 0))}
    ys = [v.co.y for v in obj.data.vertices]
    cy = (min(ys) + max(ys)) / 2

    for v in obj.data.vertices:
        if v.co.z <= keep_z:
            continue
        t = (v.co.z - keep_z) / (hi - keep_z)          # 0 at cut, 1 at old top
        v.co.z = keep_z + (v.co.z - keep_z) * scale
        s = 1.0 + (widen - 1.0) * t                    # flare only up the shaft
        c = cx[1] if v.co.x > 0 else cx[-1]
        v.co.x = c + (v.co.x - c) * s
        v.co.y = cy + (v.co.y - cy) * s
    obj.data.update()
    lo2, hi2 = measure(obj)
    return {"old_top": round(hi, 3), "new_top": round(hi2, 3),
            "compression": round(scale, 3)}


def retexture(obj, rgb=(0.155, 0.075, 0.040), rough=0.46):
    """Brown worn leather, keeping the asset's diffuse detail and normal map."""
    done = []
    for slot in obj.material_slots:
        m = slot.material
        if not m or not m.use_nodes:
            continue
        nt = m.node_tree
        tex = nt.nodes.get("diffuseTexture")
        bsdf = nt.nodes.get("Principled BSDF")
        if not tex or not bsdf:
            continue
        for n in list(nt.nodes):
            if n.name.startswith("RV_"):
                nt.nodes.remove(n)
        grey = nt.nodes.new("ShaderNodeHueSaturation"); grey.name = "RV_grey"
        grey.inputs["Saturation"].default_value = 0.0
        grey.location = (tex.location.x + 200, tex.location.y + 300)
        nt.links.new(tex.outputs["Color"], grey.inputs["Color"])
        mr = nt.nodes.new("ShaderNodeMapRange"); mr.name = "RV_range"
        mr.location = (tex.location.x + 380, tex.location.y + 300)
        mr.inputs["From Min"].default_value = 0.0
        mr.inputs["From Max"].default_value = 0.55
        mr.inputs["To Min"].default_value = 0.55
        mr.inputs["To Max"].default_value = 1.45      # keep the leather's contrast
        mr.clamp = True
        nt.links.new(grey.outputs["Color"], mr.inputs["Value"])
        tint = nt.nodes.new("ShaderNodeMixRGB"); tint.name = "RV_tint"
        tint.blend_type = 'MULTIPLY'
        tint.inputs["Fac"].default_value = 1.0
        tint.location = (tex.location.x + 560, tex.location.y + 300)
        tint.inputs["Color1"].default_value = (*rgb, 1.0)
        nt.links.new(mr.outputs["Result"], tint.inputs["Color2"])
        nt.links.new(tint.outputs["Color"], bsdf.inputs["Base Color"])
        if not bsdf.inputs["Roughness"].is_linked:
            bsdf.inputs["Roughness"].default_value = rough
        if "Specular IOR Level" in bsdf.inputs:
            bsdf.inputs["Specular IOR Level"].default_value = 0.5
        a = bsdf.inputs.get("Alpha")
        if a is not None and a.is_linked:
            for l in list(a.links):
                nt.links.remove(l)
            a.default_value = 1.0
        try:
            m.blend_method = 'OPAQUE'
        except Exception:
            pass
        done.append(m.name)
    return done


def fit_jeans(boots, pants, clearance=0.004):
    """Push any jean vertex that pokes through a boot back inside it."""
    from mathutils.bvhtree import BVHTree
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(boots.evaluated_get(dg), depsgraph=dg)
    me.transform(boots.matrix_world)
    bvh = BVHTree.FromPolygons([v.co.copy() for v in me.vertices],
                               [tuple(p.vertices) for p in me.polygons])
    top = max(v.co.z for v in me.vertices)
    bpy.data.meshes.remove(me)

    moved = 0
    for v in pants.data.vertices:
        p = pants.matrix_world @ v.co
        if p.z > top:                       # above the boot: nothing to do
            continue
        loc, nor, idx, d = bvh.find_nearest(p, 0.12)
        if loc is None:
            continue
        if (p - loc).dot(nor) > -clearance:  # outside, or too close to the shell
            target = loc - nor * clearance   # tuck inside the shaft
            v.co = pants.matrix_world.inverted() @ target
            moved += 1
    pants.data.update()
    return moved
