"""Deform-only GLB export with the prop socket preserved.

v1 exported with export_def_bones=True while prop_socket.R had use_deform=False,
so the socket -- the whole prop attachment contract -- was silently dropped from
both shipped GLBs and no Godot-side test caught it. Here the socket is a deform
bone, and the export is asserted afterwards rather than assumed.

  blender --background <clip.blend> --python export_glb.py -- <out.glb> <anim_name> [--strip-prop]
"""
import json, os, struct, sys
import bpy
from mathutils import Matrix

A = sys.argv[sys.argv.index("--") + 1:]
GLB, ANIM = A[0], A[1]
STRIP = "--strip-prop" in A
os.makedirs(os.path.dirname(GLB) or ".", exist_ok=True)
rig = bpy.data.objects["rv_rigify"]
bpy.context.view_layer.objects.active = rig
if rig.mode != "OBJECT": bpy.ops.object.mode_set(mode="OBJECT")

meshes = [o for o in bpy.data.objects if o.type == "MESH"]
can = next((o for o in meshes if "can" in o.name.lower()), None)
body = max([o for o in meshes if o is not can], key=lambda o: len(o.data.vertices))

# record the prop attachment against the socket AND against DEF-hand.R, so a
# Godot BoneAttachment3D can use either
if can is not None:
    sc = bpy.context.scene
    sc.frame_set(sc.frame_start)
    bpy.context.view_layer.update()
    W = rig.matrix_world
    rel_sock = (W @ rig.pose.bones["DEF-prop_socket.R"].matrix).inverted() @ can.matrix_world
    rel_hand = (W @ rig.pose.bones["DEF-hand.R"].matrix).inverted() @ can.matrix_world
    json.dump({"socket_bone": "DEF-prop_socket.R",
               "can_local_to_socket": [list(r) for r in rel_sock],
               "fallback_bone": "DEF-hand.R",
               "can_local_to_hand": [list(r) for r in rel_hand],
               "note": ("Godot: BoneAttachment3D on DEF-prop_socket.R needs no offset "
                        "beyond can_local_to_socket; the DEF-hand.R fallback exists so "
                        "the contract survives a rig without the socket.")},
              open(os.path.join(os.path.dirname(GLB), "prop_attachment.json"), "w"), indent=2)

act = rig.animation_data.action
act.name = ANIM
for a in list(bpy.data.actions):
    if a is not act: bpy.data.actions.remove(a)
KEEP = {body.name, rig.name}
if can is not None and not STRIP: KEEP.add(can.name)
for o in list(bpy.data.objects):
    if o.name not in KEEP: bpy.data.objects.remove(o, do_unlink=True)
for o in bpy.data.objects: o.select_set(o.name in KEEP)
bpy.context.view_layer.objects.active = rig
bpy.ops.export_scene.gltf(filepath=GLB, export_format="GLB", use_selection=True,
                          export_def_bones=True, export_animations=True,
                          export_frame_range=True, export_skins=True, export_morph=False)

d = open(GLB, "rb").read(); off = 12; js = None
while off < len(d):
    clen, ctype = struct.unpack("<II", d[off:off + 8]); off += 8
    if ctype == 0x4E4F534A: js = json.loads(d[off:off + clen])
    off += clen
names = [n.get("name", "") for n in js["nodes"]]
joints = js["skins"][0]["joints"]
jnames = [js["nodes"][i].get("name", "") for i in joints]
res = {"glb": GLB, "size_mb": round(len(d) / 1048576, 2), "nodes": len(js["nodes"]),
       "skins": len(js["skins"]), "joints": len(joints),
       "non_def_joints": [n for n in jnames if not n.startswith("DEF-")],
       "prop_socket_in_skin": any("prop_socket" in n for n in jnames),
       "animations": [a.get("name") for a in js.get("animations", [])]}
print(json.dumps(res, indent=2))
assert len(js["skins"]) == 1, "expected exactly one skin"
assert not res["non_def_joints"], "non-deform joints leaked into the export"
assert len(res["animations"]) == 1 and res["animations"][0] == ANIM, "animation name/count"
if can is not None and not STRIP:
    assert res["prop_socket_in_skin"], "prop socket did not survive export"
print("EXPORT_OK")
