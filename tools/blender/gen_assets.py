"""Generate all placeholder GLB assets for Red Valley.

Run headless:
  /opt/blender/blender --background --python tools/blender/gen_assets.py

Low-poly, flat-colour, warm palette matching the concept art. Each asset is
built in an empty scene and exported as its own .glb (whole-scene export, so
no exporter selection flags are needed across Blender versions).
"""
import bpy
import math
import os
import random

random.seed(7)

OUT_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "assets", "models"))
os.makedirs(OUT_DIR, exist_ok=True)

# ----------------------------------------------------------------- palette
PAL = {
    "roof":       (0.62, 0.25, 0.12),
    "roof_dark":  (0.48, 0.18, 0.09),
    "wall":       (0.85, 0.72, 0.48),
    "wood":       (0.55, 0.36, 0.20),
    "wood_dark":  (0.38, 0.24, 0.13),
    "stone":      (0.55, 0.54, 0.50),
    "stone_dark": (0.42, 0.41, 0.38),
    "green":      (0.30, 0.52, 0.22),
    "green_dark": (0.20, 0.38, 0.15),
    "green_lite": (0.45, 0.65, 0.28),
    "cabbage":    (0.55, 0.72, 0.42),
    "tomato_red": (0.78, 0.18, 0.12),
    "wheat_gold": (0.82, 0.66, 0.25),
    "wheat_grn":  (0.55, 0.62, 0.30),
    "flower_wht": (0.92, 0.92, 0.88),
    "cover_wht":  (0.93, 0.93, 0.88),
    "skin":       (0.87, 0.65, 0.48),
    "hair_brn":   (0.32, 0.20, 0.10),
    "hair_red":   (0.45, 0.22, 0.10),
    "shirt":      (0.90, 0.86, 0.75),
    "vest":       (0.45, 0.28, 0.15),
    "denim":      (0.26, 0.33, 0.45),
    "denim_lite": (0.35, 0.45, 0.60),
    "metal":      (0.60, 0.62, 0.65),
    "soil_dark":  (0.30, 0.20, 0.12),
}

_mats = {}

def mat(key):
    if key in _mats and _mats[key].name in bpy.data.materials:
        return _mats[key]
    m = bpy.data.materials.new("m_" + key)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    c = PAL[key]
    # palette is authored in sRGB; Blender sockets are linear
    lin = [pow(v, 2.2) for v in c]
    bsdf.inputs["Base Color"].default_value = (lin[0], lin[1], lin[2], 1.0)
    bsdf.inputs["Roughness"].default_value = 0.92
    _mats[key] = m
    return m

# ----------------------------------------------------------------- helpers

def reset():
    bpy.ops.wm.read_homefile(use_empty=True)
    global _mats
    _mats = {}

def _finish(obj, color, name):
    obj.name = name
    if obj.data.materials:
        obj.data.materials.clear()
    obj.data.materials.append(mat(color))
    return obj

def box(name, color, size=(1, 1, 1), loc=(0, 0, 0), rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.scale = (size[0], size[1], size[2])
    bpy.ops.object.transform_apply(scale=True)
    return _finish(o, color, name)

def cyl(name, color, r=0.5, depth=1.0, loc=(0, 0, 0), rot=(0, 0, 0), verts=8, r2=None):
    if r2 is None:
        bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=depth, location=loc, rotation=rot)
    else:
        bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r, radius2=r2, depth=depth, location=loc, rotation=rot)
    return _finish(bpy.context.active_object, color, name)

def cone(name, color, r=0.5, depth=1.0, loc=(0, 0, 0), rot=(0, 0, 0), verts=8):
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r, radius2=0, depth=depth, location=loc, rotation=rot)
    return _finish(bpy.context.active_object, color, name)

def ico(name, color, r=0.5, loc=(0, 0, 0), subdiv=1, squash=1.0):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=subdiv, radius=r, location=loc)
    o = bpy.context.active_object
    if squash != 1.0:
        o.scale = (1.0, 1.0, squash)
        bpy.ops.object.transform_apply(scale=True)
    return _finish(o, color, name)

def prism(name, color, width, length, height, loc=(0, 0, 0)):
    """Triangular gable-roof prism: ridge along Y, peak pointing up."""
    hw, hl = width / 2.0, length / 2.0
    verts = [(-hw, -hl, 0), (hw, -hl, 0), (hw, hl, 0), (-hw, hl, 0),
             (0, -hl, height), (0, hl, height)]
    faces = [(0, 1, 4), (2, 3, 5), (1, 2, 5, 4), (3, 0, 4, 5), (3, 2, 1, 0)]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    o = bpy.data.objects.new(name, mesh)
    o.location = loc
    bpy.context.collection.objects.link(o)
    bpy.context.view_layer.objects.active = o
    return _finish(o, color, name)

def join_all(name):
    objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    joined = bpy.context.active_object
    joined.name = name
    bpy.ops.object.shade_flat()
    return joined

def export(name):
    path = os.path.join(OUT_DIR, name + ".glb")
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", export_yup=True)
    print("exported", path)

def asset_done(name):
    join_all(name)
    export(name)


# ----------------------------------------------------------------- buildings

def build_farmhouse():
    reset()
    box("body", "wall", (5.2, 4.0, 2.6), (0, 0, 1.3))
    prism("roof", "roof", 6.0, 4.6, 1.7, (0, 0, 2.55))
    box("door", "wood_dark", (0.9, 0.12, 1.8), (0.9, -2.02, 0.9))
    box("window1", "shirt", (1.0, 0.1, 0.9), (-1.2, -2.02, 1.5))
    box("window2", "shirt", (0.9, 0.1, 0.9), (0, 2.02, 1.5))
    box("chimney", "stone", (0.5, 0.5, 1.6), (1.6, 0.8, 3.3))
    box("step", "stone_dark", (1.2, 0.5, 0.18), (0.9, -2.3, 0.09))
    # window frames
    box("frame1", "wood", (1.12, 0.08, 0.1), (-1.2, -2.03, 1.99))
    box("frame2", "wood", (1.12, 0.08, 0.1), (-1.2, -2.03, 1.01))
    asset_done("farmhouse")

def build_sarah_house():
    reset()
    box("body", "wood", (4.2, 3.4, 2.4), (0, 0, 1.2))
    prism("roof", "roof_dark", 4.8, 4.0, 1.4, (0, 0, 2.35))
    box("door", "wood_dark", (0.85, 0.12, 1.7), (-0.8, -1.72, 0.85))
    box("window", "shirt", (0.9, 0.1, 0.8), (0.9, -1.72, 1.5))
    asset_done("sarah_house")

def build_shed():
    reset()
    box("body", "wood_dark", (2.6, 2.2, 1.9), (0, 0, 0.95))
    prism("roof", "wood", 3.0, 2.6, 0.9, (0, 0, 1.85))
    box("door", "wood", (1.0, 0.1, 1.5), (0, -1.12, 0.75))
    asset_done("shed")

def build_windmill_base():
    reset()
    cyl("tower", "wood", r=0.9, r2=0.45, depth=6.0, loc=(0, 0, 3.0), verts=6)
    box("head", "wood_dark", (1.0, 1.0, 0.9), (0, 0, 6.3))
    asset_done("windmill_base")

def build_windmill_blades():
    reset()
    for i in range(4):
        a = i * math.pi / 2
        box(f"blade{i}", "shirt", (0.35, 0.05, 2.4),
            (math.sin(a) * 1.35, 0, math.cos(a) * 1.35), (0, a, 0))
    box("hub", "wood_dark", (0.3, 0.3, 0.3), (0, 0, 0))
    asset_done("windmill_blades")

def build_well():
    reset()
    cyl("ring", "stone", r=0.75, depth=0.8, loc=(0, 0, 0.4), verts=10)
    cyl("hole", "soil_dark", r=0.55, depth=0.1, loc=(0, 0, 0.82), verts=10)
    box("post1", "wood", (0.14, 0.14, 1.6), (0.6, 0, 1.2))
    box("post2", "wood", (0.14, 0.14, 1.6), (-0.6, 0, 1.2))
    prism("wellroof", "roof", 1.8, 1.5, 0.55, (0, 0, 1.95))
    asset_done("well")

def build_fence():
    reset()
    box("post1", "wood", (0.12, 0.12, 1.0), (-0.94, 0, 0.5))
    box("post2", "wood", (0.12, 0.12, 1.0), (0.94, 0, 0.5))
    box("rail1", "wood_dark", (2.0, 0.07, 0.12), (0, 0, 0.78))
    box("rail2", "wood_dark", (2.0, 0.07, 0.12), (0, 0, 0.42))
    asset_done("fence")

def build_crate():
    reset()
    box("crate", "wood", (1.0, 0.8, 0.7), (0, 0, 0.35))
    box("lid", "wood_dark", (1.06, 0.86, 0.1), (0, 0, 0.72))
    box("plank", "wood_dark", (0.12, 0.82, 0.72), (0, 0, 0.36))
    asset_done("crate")

def build_bin():
    reset()
    box("bin", "wood_dark", (1.2, 0.9, 0.8), (0, 0, 0.4))
    box("rim", "wood", (1.3, 1.0, 0.12), (0, 0, 0.8))
    asset_done("bin")

def build_tree(n, canopy_color):
    reset()
    cyl("trunk", "wood_dark", r=0.22, r2=0.15, depth=2.2, loc=(0, 0, 1.1), verts=6)
    blobs = [(0, 0, 2.9, 1.25)]
    for i in range(3):
        a = random.uniform(0, math.tau)
        blobs.append((math.cos(a) * 0.7, math.sin(a) * 0.7,
                      2.4 + random.uniform(0.2, 0.9), random.uniform(0.6, 0.95)))
    for i, (x, y, z, r) in enumerate(blobs):
        ico(f"can{i}", canopy_color, r=r, loc=(x, y, z), squash=0.85)
    asset_done(f"tree{n}")

def build_rock():
    reset()
    ico("rock", "stone", r=0.5, loc=(0, 0, 0.25), squash=0.6)
    ico("rock2", "stone_dark", r=0.3, loc=(0.4, 0.2, 0.15), squash=0.6)
    asset_done("rock")

def build_row_cover():
    reset()
    bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=1.0, depth=1.7,
                                        location=(0, 0, 0.1), rotation=(math.radians(90), 0, 0))
    o = bpy.context.active_object
    o.scale = (0.95, 0.42, 1.0)
    bpy.ops.object.transform_apply(scale=True)
    m = bpy.data.materials.new("m_cover")
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (0.93, 0.93, 0.88, 1.0)
    b.inputs["Roughness"].default_value = 0.8
    b.inputs["Alpha"].default_value = 0.85
    m.surface_render_method = "BLENDED"
    o.data.materials.append(m)
    o.name = "row_cover"
    export("row_cover")

# ----------------------------------------------------------------- characters

def build_character(name, shirt, pants, hair, hair_style="pony"):
    reset()
    # legs
    box("legL", pants, (0.16, 0.2, 0.72), (-0.11, 0, 0.36))
    box("legR", pants, (0.16, 0.2, 0.72), (0.11, 0, 0.36))
    # torso
    box("torso", shirt, (0.44, 0.26, 0.62), (0, 0, 1.03))
    if name == "farmer":
        box("vest", "vest", (0.48, 0.29, 0.44), (0, 0, 0.95))
    else:
        box("bib", pants, (0.3, 0.29, 0.3), (0, 0, 1.1))
    # arms
    box("armL", shirt, (0.12, 0.18, 0.6), (-0.30, 0, 1.02))
    box("armR", shirt, (0.12, 0.18, 0.6), (0.30, 0, 1.02))
    box("handL", "skin", (0.11, 0.16, 0.12), (-0.30, 0, 0.68))
    box("handR", "skin", (0.11, 0.16, 0.12), (0.30, 0, 0.68))
    # head
    box("head", "skin", (0.3, 0.28, 0.32), (0, 0, 1.53))
    box("hairtop", hair, (0.34, 0.32, 0.12), (0, 0.0, 1.72))
    box("hairback", hair, (0.34, 0.1, 0.3), (0, 0.17, 1.55))
    if hair_style == "pony":
        box("pony", hair, (0.12, 0.12, 0.34), (0, 0.24, 1.38))
    else:
        box("bun", hair, (0.18, 0.14, 0.16), (0, 0.24, 1.62))
    asset_done(name)

# ----------------------------------------------------------------- crops

def plant_positions():
    return [(-0.42, -0.42), (0.45, -0.35), (-0.35, 0.45), (0.42, 0.4), (0.02, 0.03)]

def build_sprout():
    reset()
    for i, (x, y) in enumerate(plant_positions()):
        cone(f"s{i}", "green_lite", r=0.045, depth=0.16, loc=(x, y, 0.08), verts=5)
    asset_done("crop_sprout")

def _leaf_blob(i, x, y, z, r, color):
    ico(f"leaf{i}", color, r=r, loc=(x, y, z), squash=0.55)

def build_tomato(stage):
    reset()
    idx = 0
    for (x, y) in plant_positions()[:4]:
        if stage == "young":
            cyl(f"stem{idx}", "green_dark", r=0.025, depth=0.3, loc=(x, y, 0.15), verts=5)
            _leaf_blob(idx, x, y, 0.3, 0.14, "green_lite")
        else:
            cyl(f"stem{idx}", "green_dark", r=0.035, depth=0.62, loc=(x, y, 0.31), verts=5)
            _leaf_blob(idx, x + 0.05, y, 0.42, 0.20, "green")
            _leaf_blob(idx + 100, x - 0.06, y + 0.05, 0.6, 0.17, "green_lite")
            if stage == "mature":
                for j in range(3):
                    a = j * 2.1 + idx
                    ico(f"fruit{idx}_{j}", "tomato_red", r=0.055,
                        loc=(x + math.cos(a) * 0.13, y + math.sin(a) * 0.13, 0.34 + j * 0.11))
        idx += 1
    asset_done("crop_tomato_" + stage)

def build_cabbage(stage):
    reset()
    idx = 0
    for (x, y) in plant_positions()[:4]:
        if stage == "young":
            _leaf_blob(idx, x, y, 0.07, 0.11, "cabbage")
        elif stage == "grown":
            _leaf_blob(idx, x, y, 0.1, 0.17, "cabbage")
            _leaf_blob(idx + 100, x, y, 0.14, 0.11, "green_lite")
        else:
            _leaf_blob(idx, x, y, 0.1, 0.2, "green")
            ico(f"head{idx}", "cabbage", r=0.14, loc=(x, y, 0.16))
        idx += 1
    asset_done("crop_cabbage_" + stage)

def build_potato(stage):
    reset()
    idx = 0
    for (x, y) in plant_positions()[:5]:
        if stage == "young":
            _leaf_blob(idx, x, y, 0.09, 0.10, "green")
        else:
            _leaf_blob(idx, x, y, 0.12, 0.16, "green")
            _leaf_blob(idx + 100, x + 0.05, y - 0.04, 0.2, 0.11, "green_dark")
            if stage == "mature":
                ico(f"fl{idx}", "flower_wht", r=0.035, loc=(x, y, 0.32))
        idx += 1
    asset_done("crop_potato_" + stage)

def build_wheat(stage):
    reset()
    color = {"young": "green_lite", "grown": "wheat_grn", "mature": "wheat_gold"}[stage]
    h = {"young": 0.25, "grown": 0.5, "mature": 0.6}[stage]
    idx = 0
    for gx in (-0.45, 0, 0.45):
        for gy in (-0.45, 0, 0.45):
            x = gx + random.uniform(-0.05, 0.05)
            y = gy + random.uniform(-0.05, 0.05)
            cyl(f"tuft{idx}", color, r=0.09, r2=0.035, depth=h, loc=(x, y, h / 2), verts=5)
            if stage == "mature":
                box(f"ear{idx}", "wheat_gold", (0.09, 0.09, 0.16), (x, y, h + 0.06))
            idx += 1
    asset_done("crop_wheat_" + stage)

def build_dead_crop():
    reset()
    idx = 0
    for (x, y) in plant_positions()[:4]:
        cyl(f"stalk{idx}", "wood_dark", r=0.02, depth=0.22,
            loc=(x, y, 0.11), rot=(random.uniform(-0.5, 0.5), random.uniform(-0.5, 0.5), 0), verts=4)
        _leaf_blob(idx, x + 0.05, y, 0.05, 0.09, "soil_dark")
        idx += 1
    asset_done("crop_dead")

# ----------------------------------------------------------------- hills ring

def build_hills():
    reset()
    random.seed(11)
    for i in range(14):
        a = i / 14.0 * math.tau
        dist = random.uniform(95, 130)
        r = random.uniform(28, 55)
        ico(f"hill{i}", "green_dark" if i % 3 else "green",
            r=r, loc=(math.cos(a) * dist, math.sin(a) * dist, -r * 0.72), subdiv=2, squash=1.0)
    for i in range(7):
        a = i / 7.0 * math.tau + 0.2
        dist = random.uniform(190, 240)
        h = random.uniform(28, 48)
        cone(f"mount{i}", "stone", r=h * 1.6, depth=h,
             loc=(math.cos(a) * dist, math.sin(a) * dist, h * 0.3), verts=7)
    asset_done("hills")

# ----------------------------------------------------------------- run all

build_farmhouse()
build_sarah_house()
build_shed()
build_windmill_base()
build_windmill_blades()
build_well()
build_fence()
build_crate()
build_bin()
build_tree(1, "green")
build_tree(2, "green_lite")
build_rock()
build_row_cover()
build_character("farmer", "shirt", "denim", "hair_brn", "pony")
build_character("sarah", "denim_lite", "denim", "hair_red", "bun")
build_sprout()
for s in ("young", "grown", "mature"):
    build_tomato(s)
    build_cabbage(s)
    build_potato(s)
    build_wheat(s)
build_dead_crop()
build_hills()
print("ALL ASSETS DONE")
