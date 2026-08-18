"""Deterministic GLB validation report: triangle count, texture sizes, UV
presence, non-manifold edges, bounding box. No repair, no authoring -- pure
inspection, per docs/ASSET_POLICY.md's "Validation" allowance.

Run headless:
  /opt/blender/blender --background --python tools/assetgen/glb_validate.py -- \
      --glb path/to/asset.glb --out report.json
"""
import bmesh
import bpy
import json
import sys


def args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = {"glb": None, "out": None}
    i = 0
    while i < len(argv):
        if argv[i] == "--glb":
            out["glb"] = argv[i + 1]; i += 2
        elif argv[i] == "--out":
            out["out"] = argv[i + 1]; i += 2
        else:
            i += 1
    if not out["glb"] or not out["out"]:
        raise SystemExit("usage: --glb <path> --out <report.json>")
    return out


def main():
    a = args()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=a["glb"])

    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if not meshes:
        json.dump({"glb": a["glb"], "error": "no mesh objects found on import"},
                   open(a["out"], "w"), indent=2)
        raise SystemExit(1)

    report = {"glb": a["glb"], "objects": []}
    tri_total = 0
    for obj in meshes:
        depsgraph = bpy.context.evaluated_depsgraph_get()
        eval_obj = obj.evaluated_get(depsgraph)
        mesh = eval_obj.to_mesh()
        mesh.calc_loop_triangles()
        tris = len(mesh.loop_triangles)
        tri_total += tris
        vert_count = len(mesh.vertices)
        has_uv = bool(mesh.uv_layers)

        bm = bmesh.new()
        bm.from_mesh(mesh)
        non_manifold = sum(1 for e in bm.edges if not e.is_manifold)
        bm.free()
        eval_obj.to_mesh_clear()

        bbox = [tuple(round(c, 4) for c in v) for v in obj.bound_box]
        xs = [v[0] for v in bbox]; ys = [v[1] for v in bbox]; zs = [v[2] for v in bbox]

        textures = []
        for slot in obj.material_slots:
            mat = slot.material
            if not mat or not mat.use_nodes:
                continue
            for node in mat.node_tree.nodes:
                if node.type == "TEX_IMAGE" and node.image:
                    img = node.image
                    textures.append({"name": img.name, "width": img.size[0], "height": img.size[1]})

        report["objects"].append({
            "name": obj.name,
            "vertex_count": vert_count,
            "triangle_count": tris,
            "non_manifold_edges": non_manifold,
            "has_uv": has_uv,
            "bounding_box_dims": [round(max(xs) - min(xs), 4), round(max(ys) - min(ys), 4), round(max(zs) - min(zs), 4)],
            "materials": len(obj.material_slots),
            "textures": textures,
        })

    report["triangle_count_total"] = tri_total
    with open(a["out"], "w") as f:
        json.dump(report, f, indent=2)
    print(f"validate: {a['glb']} -> {tri_total} tris, {len(meshes)} object(s) -> {a['out']}")


main()
