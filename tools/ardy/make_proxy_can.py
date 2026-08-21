"""Generate the diagnostic watering-can proxy for the ARDY pilot.

NOT a game asset. This is measurement apparatus: primitive geometry whose
purpose is to carry an exact grip point and spout tip so `water_can` alignment
can be tested numerically instead of judged by eye. It is deliberately kept out
of tools/blender/gen_assets.py and out of assets/ so it cannot drift into the
shipping set.

  blender --background --python tools/ardy/make_proxy_can.py

Contract (mirrored by the real can that replaces it):
  * mesh origin sits AT the grip point
  * `grip_origin` empty at the origin
  * `spout_tip` empty at the centre of the spout opening
  * prop local -Z runs along the forearm when parented to prop_socket.R
"""
import json
import math
import os
import sys

import bpy
from mathutils import Matrix

OUT_DIR = "/home/thomas/Dev/red-valley/art/animation/ardy_pilot/proxy"
os.makedirs(OUT_DIR, exist_ok=True)

# Real-world-ish watering can, metres. Values chosen so the proxy occupies the
# same volume a real can would -- a wrong-sized proxy would give a misleading
# grip and spout reading.
#
# Layout, with the ORIGIN AT THE GRIP (where the hand closes on the handle):
#   handle bar : along X, through the origin -- this is what the hand wraps
#   body       : hangs below and slightly behind the grip
#   spout      : leaves the lower body, angles forward and down to the tip
# Dimensions sized to the MEASURED hand, not guessed. The previous proxy failed
# the grip because its body was a 0.085 m radius cylinder whose top sat only
# 0.0825 m below the grip -- exactly where the thumb and index have to be, so no
# collision-free pose existed at any closure.
#
#   hand width across the handle axis .......... 0.095 m (measured)
#   required clear span between the struts ..... 0.115 m (hand + 10 mm each side)
#   required drop from bar to body top ......... 0.075 m (fingers wrap and hang
#                                                 below the bar) + margin
HAND_W = 0.095
BAR_R, BAR_LEN = 0.011, 0.140      # 22 mm bar: graspable, not a rod
STRUT_R = 0.008
CLEAR_SPAN = BAR_LEN - 2 * STRUT_R  # 0.124 m > 0.115 required
BODY_R, BODY_H = 0.075, 0.200
BODY_TOP_DROP = 0.130               # bar -> body top, vs 0.0825 before
SPOUT_R = 0.014

BODY_C = (0.0, 0.020, -(BODY_TOP_DROP + BODY_H / 2.0))
SHOULDER_Z = -BODY_TOP_DROP
SPOUT_BASE = (0.0, -0.050, -(BODY_TOP_DROP + BODY_H * 0.85))
SPOUT_TIP = (0.0, -0.300, -0.150)   # long spout rising toward the body top

bpy.ops.wm.read_factory_settings(use_empty=True)

def cyl(name, r, h, loc, rot=(0, 0, 0), verts=18):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=h, location=loc,
                                        rotation=rot, vertices=verts)
    o = bpy.context.active_object
    o.name = name
    return o

def tube(name, a, b, r):
    """Cylinder spanning two points -- used for the spout and handle struts."""
    ax, ay, az = a
    bx, by, bz = b
    dx, dy, dz = bx-ax, by-ay, bz-az
    length = math.sqrt(dx*dx + dy*dy + dz*dz)
    mid = ((ax+bx)/2, (ay+by)/2, (az+bz)/2)
    # XYZ Euler composes as Rz @ Ry @ Rx, so Rz(rot_z) @ Ry(rot_y) maps the
    # cylinder's +Z axis to (sin ry cos rz, sin ry sin rz, cos ry). No extra
    # quarter turn: adding one yaws the spout 90 deg across the body.
    rot_y = math.acos(max(-1.0, min(1.0, dz/length)))
    rot_z = math.atan2(dy, dx)
    o = cyl(name, r, length, mid)
    o.rotation_euler = (0.0, rot_y, rot_z)
    return o

parts = []
parts.append(cyl("can_body", BODY_R, BODY_H, BODY_C))
parts.append(cyl("can_handle_bar", BAR_R, BAR_LEN, (0.0, 0.0, 0.0),
                 rot=(0.0, math.radians(90), 0.0)))
# Open arch: each strut sweeps from a bar end down to the body shoulder in two
# segments, so the opening the hand passes through is genuinely clear.
for sx in (-BAR_LEN / 2, BAR_LEN / 2):
    mid = (sx * 0.92, 0.012, SHOULDER_Z * 0.45)
    parts.append(tube("can_strut", (sx, 0.0, 0.0), mid, STRUT_R))
    parts.append(tube("can_strut", mid, (sx * 0.52, 0.020, SHOULDER_Z), STRUT_R))
parts.append(tube("can_spout", SPOUT_BASE, SPOUT_TIP, SPOUT_R))

bpy.ops.object.select_all(action="DESELECT")
for o in parts:
    o.select_set(True)
bpy.context.view_layer.objects.active = parts[0]
bpy.ops.object.join()
can = bpy.context.active_object
can.name = "watering_can_proxy"
# The join inherits the first operand's origin (the body centre). The contract
# requires the origin to sit AT the grip, so move it to the world origin --
# otherwise every prop attached to prop_socket.R hangs off by the body offset.
bpy.context.scene.cursor.location = (0.0, 0.0, 0.0)
bpy.ops.object.origin_set(type="ORIGIN_CURSOR")

mat = bpy.data.materials.new("proxy_diagnostic")
mat.use_nodes = True
bsdf = mat.node_tree.nodes.get("Principled BSDF")
bsdf.inputs["Base Color"].default_value = (0.16, 0.42, 0.55, 1.0)   # obviously not a real prop
bsdf.inputs["Roughness"].default_value = 0.55
can.data.materials.append(mat)

# --- measurement markers -------------------------------------------------
tip = SPOUT_TIP

def marker(name, loc):
    e = bpy.data.objects.new(name, None)
    e.empty_display_type = "PLAIN_AXES"
    e.empty_display_size = 0.03
    e.location = loc
    bpy.context.collection.objects.link(e)
    e.parent = can
    return e

marker("grip_origin", (0.0, 0.0, 0.0))
marker("spout_tip", tip)

# grip_anchor: the exact centre AND axis of the handle bar, as a full frame.
# The bar is a cylinder along local X through the origin, so:
#   anchor Y -> bar axis          (the bone runs along the handle)
#   anchor Z -> toward the body   (the way a gripping palm faces)
#   anchor X -> Y x Z, right-handed
# Attaching the can as `sock @ anchor_local.inverted()` makes grip_anchor and
# prop_socket.R exactly coincident, so there is no drift to accumulate.
GRIP_ANCHOR_BASIS = Matrix(((0.0, 1.0,  0.0, 0.0),
                            (1.0, 0.0,  0.0, 0.0),
                            (0.0, 0.0, -1.0, 0.0),
                            (0.0, 0.0,  0.0, 1.0)))
ga = bpy.data.objects.new("grip_anchor", None)
ga.empty_display_type = "ARROWS"
ga.empty_display_size = 0.04
bpy.context.collection.objects.link(ga)
ga.parent = can
ga.matrix_world = GRIP_ANCHOR_BASIS

glb = os.path.join(OUT_DIR, "watering_can_proxy.glb")
bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB",
                          use_selection=False, export_apply=True,
                          export_cameras=False, export_lights=False)

meta = {
    "NOT_FOR_SHIPPING": True,
    "purpose": "ARDY pilot alignment measurement only",
    "units": "metres",
    "contract": {
        "mesh_origin": "grip point",
        "prop_local_-Z": "runs along the forearm when parented to prop_socket.R",
    },
    "markers": {
        "grip_origin": [0.0, 0.0, 0.0],
        "spout_tip": [round(v, 5) for v in tip],
        "grip_anchor": [0.0, 0.0, 0.0],
    },
    "grip_anchor_basis_rows": [list(r) for r in GRIP_ANCHOR_BASIS],
    "grip_anchor_contract": ("Y along the handle bar, Z toward the can body; "
                             "coincide this frame with prop_socket.R"),
    "spout_tip_offset_from_grip_m": round(math.dist((0, 0, 0), tip), 4),
    "dimensions_m": {
        "body_radius": BODY_R, "body_height": BODY_H,
        "spout_radius": SPOUT_R, "handle_bar_length": BAR_LEN,
        "handle_bar_diameter": round(BAR_R * 2, 4),
        "handle_clear_span": round(CLEAR_SPAN, 4),
        "hand_width_measured": HAND_W,
        "clear_span_margin": round(CLEAR_SPAN - HAND_W, 4),
        "bar_to_body_top": BODY_TOP_DROP,
    },
    "triangles": len(can.data.loop_triangles) if can.data.loop_triangles else None,
}
can.data.calc_loop_triangles()
meta["triangles"] = len(can.data.loop_triangles)
json.dump(meta, open(os.path.join(OUT_DIR, "watering_can_proxy.json"), "w"), indent=2)
print("PROXY_WRITTEN", glb)
print(json.dumps(meta, indent=2))
