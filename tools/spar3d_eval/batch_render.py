"""Render every candidate GLB to standardized views + a silhouette matte.

One Blender process for all candidates (importing is far cheaper than process
startup). Read-only: no geometry is modified, only cameras and lights.
  blender --background --python batch_render.py -- <glb_dir> <out_dir> [size]
"""
import glob, json, math, os, sys
import bpy, mathutils

argv = sys.argv[sys.argv.index("--") + 1:]
GLB_DIR, OUT_DIR = argv[0], argv[1]
SIZE = int(argv[2]) if len(argv) > 2 else 420
os.makedirs(OUT_DIR, exist_ok=True)
VIEWS = {"front": 0, "three_quarter": 40, "side": 90, "back": 180}

def build_scene():
    scene = bpy.context.scene
    world = bpy.data.worlds.new("W"); world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[1].default_value = 0.55
    scene.world = world
    scene.render.engine = next(e for e in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES")
                               if e in scene.render.bl_rna.properties["engine"].enum_items.keys())
    scene.render.resolution_x = scene.render.resolution_y = SIZE
    try: scene.view_settings.view_transform = "Standard"
    except TypeError: pass
    return scene

report = {}
for path in sorted(glob.glob(os.path.join(GLB_DIR, "*.glb"))):
    name = os.path.splitext(os.path.basename(path))[0]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=path)
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    if not meshes:
        report[name] = {"error": "no mesh"}; continue

    def extents():
        lo = [float("inf")]*3; hi = [float("-inf")]*3
        for o in meshes:
            for c in o.bound_box:
                w = o.matrix_world @ mathutils.Vector(c)
                for i in range(3): lo[i]=min(lo[i],w[i]); hi[i]=max(hi[i],w[i])
        return lo, hi
    lo, hi = extents()
    ext = [hi[i]-lo[i] for i in range(3)]
    tall = max(range(3), key=lambda i: ext[i])
    if tall != 2:
        rot = mathutils.Matrix.Rotation(math.radians(-90), 4, "X" if tall == 1 else "Y")
        for o in meshes: o.matrix_world = rot @ o.matrix_world
        bpy.context.view_layer.update(); lo, hi = extents()
    size = [hi[i]-lo[i] for i in range(3)]
    centre = [(hi[i]+lo[i])/2 for i in range(3)]
    radius = max(size) or 1.0

    for o in meshes:                              # vertex-colour fallback
        cols = getattr(o.data, "color_attributes", None)
        has_tex = any(m and m.use_nodes and any(n.type=="TEX_IMAGE" for n in m.node_tree.nodes)
                      for m in o.data.materials)
        if cols and len(cols) and not has_tex:
            mat = bpy.data.materials.new(f"vcol_{o.name}"); mat.use_nodes = True
            nt = mat.node_tree; ca = nt.nodes.new("ShaderNodeVertexColor")
            ca.layer_name = cols[0].name
            nt.links.new(ca.outputs["Color"], nt.nodes.get("Principled BSDF").inputs["Base Color"])
            o.data.materials.clear(); o.data.materials.append(mat)

    scene = build_scene()
    key = bpy.data.objects.new("key", bpy.data.lights.new("key", "AREA"))
    key.data.energy = 260 * radius**2; key.data.size = 3*radius
    key.location = (centre[0]+2*radius, centre[1]-2.5*radius, centre[2]+2*radius)
    key.rotation_euler = (math.radians(60), 0, math.radians(40))
    bpy.context.collection.objects.link(key)
    cam_data = bpy.data.cameras.new("cam"); cam_data.lens = 70
    cam = bpy.data.objects.new("cam", cam_data)
    bpy.context.collection.objects.link(cam); scene.camera = cam

    d = radius*3.1
    tris = sum(len(o.data.loop_triangles) for o in meshes
               if (o.data.calc_loop_triangles() or True))
    for vname, yaw in VIEWS.items():
        a = math.radians(yaw + 180)               # SPAR3D emits subject facing away
        cam.location = (centre[0]+d*math.sin(a), centre[1]-d*math.cos(a), centre[2]+radius*0.18)
        cam.rotation_euler = (math.radians(90), 0, a)
        for tag, transparent in (("", False), ("_mask", True)):
            if transparent and vname != "front": continue
            scene.render.film_transparent = transparent
            scene.render.filepath = os.path.join(OUT_DIR, f"{name}_{vname}{tag}.png")
            bpy.ops.render.render(write_still=True)
    scene.render.film_transparent = False
    cam_data.lens = 105
    a = math.radians(180)
    cam.location = (centre[0]+radius*0.95*math.sin(a), centre[1]-radius*0.95*math.cos(a),
                    hi[2]-size[2]*0.10)
    cam.rotation_euler = (math.radians(90), 0, a)
    scene.render.filepath = os.path.join(OUT_DIR, f"{name}_face.png")
    bpy.ops.render.render(write_still=True)
    report[name] = {"triangles": tris, "size": size}
    print(f"rendered {name}", flush=True)

json.dump(report, open(os.path.join(OUT_DIR, "render_report.json"), "w"), indent=2)
print("BATCH RENDER DONE")
