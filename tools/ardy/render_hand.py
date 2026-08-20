"""Rest-hand close-ups, plain and weight-coded, both sides.

The colour pass paints each vertex by the digit chain that owns most of its
weight, which is the only way to see whether the chains landed on the real
digits -- capture counts alone cannot show a chain sitting between two fingers.

  blender --background --python render_hand.py -- <rig.glb> <outdir> [tag]
"""
import math, os, sys
import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
GLB, OUT = argv[0], argv[1]
TAG = argv[2] if len(argv) > 2 else "rest"
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)
rig = [o for o in bpy.data.objects if o.type == "ARMATURE"][0]
obj = max([o for o in bpy.data.objects if o.type == "MESH" and len(o.vertex_groups)],
          key=lambda o: len(o.data.vertices))
for o in list(bpy.data.objects):
    if o.type == "MESH" and o is not obj and "can" not in o.name.lower():
        bpy.data.objects.remove(o, do_unlink=True)

COL = {"thumb": (0.95, 0.25, 0.20, 1), "index": (0.20, 0.75, 0.95, 1),
       "middle": (0.30, 0.85, 0.35, 1), "ring": (0.95, 0.80, 0.20, 1),
       "pinky": (0.75, 0.35, 0.95, 1)}
gn = {g.index: g.name for g in obj.vertex_groups}
att = obj.data.color_attributes.new("digitcol", "FLOAT_COLOR", "POINT")
for v in obj.data.vertices:
    c = (0.62, 0.62, 0.64, 1)
    if v.groups:
        top = max(v.groups, key=lambda g: g.weight)
        nm = gn.get(top.group, "")
        for d, col in COL.items():
            if nm.startswith(d + "."): c = col
    att.data[v.index].color = c

mat = bpy.data.materials.new("digit"); mat.use_nodes = True
nt = mat.node_tree
bsdf = nt.nodes["Principled BSDF"]
ca = nt.nodes.new("ShaderNodeVertexColor"); ca.layer_name = "digitcol"
nt.links.new(ca.outputs["Color"], bsdf.inputs["Base Color"])
bsdf.inputs["Roughness"].default_value = 0.6

sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x = sc.render.resolution_y = 900
sc.view_settings.view_transform = "Standard"
sc.render.image_settings.file_format = "PNG"
try:
    sc.eevee.use_raytracing = True; sc.eevee.use_shadows = True
except AttributeError: pass
bpy.ops.object.light_add(type="SUN", location=(2, -3, 4))
k = bpy.context.object; k.data.energy = 4.5
k.rotation_euler = (math.radians(42), 0, math.radians(28))
bpy.ops.object.light_add(type="AREA", location=(-3, -2, 1.5))
f = bpy.context.object; f.data.energy = 260; f.data.size = 4
f.rotation_euler = (math.radians(78), 0, math.radians(-48))
sc.world = sc.world or bpy.data.worlds.new("W"); sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs[0].default_value = (.30, .34, .40, 1)
cd = bpy.data.cameras.new("C"); cam = bpy.data.objects.new("C", cd)
sc.collection.objects.link(cam); sc.camera = cam; cd.lens = 55

bpy.context.view_layer.update()
focus = (rig.matrix_world @ rig.pose.bones["hand.R"].matrix).to_translation() \
        + (rig.matrix_world @ rig.pose.bones["hand.R"].matrix).to_3x3() @ Vector((0, 0.04, 0))
orig = list(obj.data.materials)

def shoot(name, dist=0.34):
    for az, tag in ((-75, "outer"), (105, "inner"), (180, "back")):
        a = math.radians(az)
        cam.location = focus + Vector((math.sin(a) * dist, -math.cos(a) * dist, 0.07))
        cam.rotation_euler = (focus - cam.location).to_track_quat("-Z", "Y").to_euler()
        sc.render.filepath = os.path.join(OUT, "%s_%s_%s.png" % (TAG, name, tag))
        bpy.ops.render.render(write_still=True)
        print("RENDERED", sc.render.filepath)

shoot("plain")
obj.data.materials.clear(); obj.data.materials.append(mat)
shoot("weights")
print("HAND_RENDER_DONE")
