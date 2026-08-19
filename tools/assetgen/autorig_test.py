"""Auto-rig a copy of a character GLB and render a deformation test sheet.

Joint positions are measured from the mesh itself (cross-section profiling)
rather than assumed from proportions, then a simple humanoid armature is bound
with Blender's automatic (heat-map) weights. Nothing is remeshed, decimated or
repaired, and the source file is never written to.

  blender --background --python autorig_test.py -- <glb> <outdir>
"""
import json, math, os, sys
import bpy, mathutils
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:]
SRC, OUT = argv[0], argv[1]
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=SRC)
meshes = [o for o in bpy.data.objects if o.type == "MESH"]
if len(meshes) != 1:
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes: o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.join()
    meshes = [bpy.context.view_layer.objects.active]
obj = meshes[0]
bpy.ops.object.select_all(action="DESELECT")
obj.select_set(True); bpy.context.view_layer.objects.active = obj
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

V = np.array([v.co[:] for v in obj.data.vertices])
zmin, zmax = V[:, 2].min(), V[:, 2].max()
H = zmax - zmin
print(f"mesh: {len(obj.data.vertices):,} verts, height {H:.3f} m")

def band(lo, hi):
    return V[(V[:, 2] >= zmin + lo*H) & (V[:, 2] < zmin + hi*H)]

def widest_z(lo, hi):
    """height (relative) at which |x| extent peaks -- used to find shoulders"""
    best, bz = -1, (lo+hi)/2
    for t in np.linspace(lo, hi, 40):
        b = band(t, t+0.02)
        if len(b) < 20: continue
        w = b[:, 0].max() - b[:, 0].min()
        if w > best: best, bz = w, t
    return bz

# --- lateral half-width profile to separate arms from torso
def torso_halfwidth(zrel):
    b = band(zrel, zrel+0.02)
    if len(b) < 20: return 0.0
    return float(np.percentile(np.abs(b[:, 0]), 55))

sh_z = widest_z(0.72, 0.86)                    # shoulder line
arm_pts = V[(V[:, 2] > zmin + 0.45*H) & (V[:, 2] < zmin + sh_z*H)]
rx = arm_pts[arm_pts[:, 0] > 0]; lx = arm_pts[arm_pts[:, 0] < 0]
def arm_chain(side):
    pts = rx if side > 0 else lx
    out = []
    for t in np.linspace(0.45, sh_z, 26):
        b = pts[(pts[:, 2] >= zmin + t*H) & (pts[:, 2] < zmin + (t+0.02)*H)]
        if len(b) < 8: continue
        far = b[np.abs(b[:, 0]) > np.percentile(np.abs(b[:, 0]), 80)]
        out.append((t, float(far[:, 0].mean()), float(far[:, 1].mean())))
    return out
chain_r, chain_l = arm_chain(1), arm_chain(-1)

def pick(chain, t):
    if not chain: return None
    return min(chain, key=lambda c: abs(c[0]-t))

# leg split: x offset of each leg at mid-thigh
th = band(0.35, 0.40)
leg_x = float(np.percentile(np.abs(th[:, 0]), 60)) if len(th) else 0.09*H
ank = band(0.03, 0.07)
ank_x = float(np.percentile(np.abs(ank[:, 0]), 60)) if len(ank) else leg_x

def Z(r): return zmin + r*H
# Arms merge into the torso near the shoulder, so the lateral-extreme scan
# cannot find them there. Place the shoulder anatomically instead, taking only
# its lateral offset from the measured torso half-width.
SH = 0.82
hw = torso_halfwidth(SH - 0.02) or 0.10*H
sh_r = (SH,  hw*0.98, 0.0)
sh_l = (SH, -hw*0.98, 0.0)
el_r = pick(chain_r, 0.63); el_l = pick(chain_l, 0.63)
wr_r = pick(chain_r, 0.47); wr_l = pick(chain_l, 0.47)
def P(c, fallback_x):
    return (c[1], c[2], Z(c[0])) if c else (fallback_x, 0.0, Z(0.6))

J = {
    "hips":     (0.0, 0.0, Z(0.52)),
    "spine":    (0.0, 0.0, Z(0.62)),
    "chest":    (0.0, 0.0, Z(0.72)),
    "neck":     (0.0, 0.0, Z(sh_z+0.02)),
    "head":     (0.0, 0.0, Z(0.93)),
    "head_top": (0.0, 0.0, Z(1.0)),
    "shoulder.R": P(sh_r, 0.09*H), "elbow.R": P(el_r, 0.20*H), "wrist.R": P(wr_r, 0.22*H),
    "shoulder.L": P(sh_l, -0.09*H), "elbow.L": P(el_l, -0.20*H), "wrist.L": P(wr_l, -0.22*H),
    "hip.R": (leg_x*0.55, 0.0, Z(0.50)), "knee.R": (leg_x*0.8, 0.0, Z(0.28)),
    "ankle.R": (ank_x, 0.0, Z(0.045)),  "toe.R": (ank_x, -0.09*H, Z(0.01)),
    "hip.L": (-leg_x*0.55, 0.0, Z(0.50)), "knee.L": (-leg_x*0.8, 0.0, Z(0.28)),
    "ankle.L": (-ank_x, 0.0, Z(0.045)), "toe.L": (-ank_x, -0.09*H, Z(0.01)),
}
json.dump({k: list(map(float, v)) for k, v in J.items()},
          open(os.path.join(OUT, "joints.json"), "w"), indent=1)
print("shoulder z=%.2f  elbow z=%.2f  wrist z=%.2f  legx=%.3f" %
      (J["shoulder.R"][2], J["elbow.R"][2], J["wrist.R"][2], leg_x))

arm = bpy.data.armatures.new("rig"); rig = bpy.data.objects.new("rig", arm)
bpy.context.collection.objects.link(rig)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode="EDIT")
BONES = [
    ("hips","spine",None), ("spine","chest","hips"), ("chest","neck","spine"),
    ("neck","head","chest"), ("head","head_top","neck"),
    ("clav.R","shoulder.R","chest"), ("upperarm.R","elbow.R","clav.R"),
    ("forearm.R","wrist.R","upperarm.R"),
    ("clav.L","shoulder.L","chest"), ("upperarm.L","elbow.L","clav.L"),
    ("forearm.L","wrist.L","upperarm.L"),
    ("thigh.R","knee.R","hips"), ("shin.R","ankle.R","thigh.R"), ("foot.R","toe.R","shin.R"),
    ("thigh.L","knee.L","hips"), ("shin.L","ankle.L","thigh.L"), ("foot.L","toe.L","shin.L"),
]
HEAD = {"hips":"hips","spine":"spine","chest":"chest","neck":"neck","head":"head",
        "clav.R":"chest","upperarm.R":"shoulder.R","forearm.R":"elbow.R",
        "clav.L":"chest","upperarm.L":"shoulder.L","forearm.L":"elbow.L",
        "thigh.R":"hip.R","shin.R":"knee.R","foot.R":"ankle.R",
        "thigh.L":"hip.L","shin.L":"knee.L","foot.L":"ankle.L"}
created = {}
for name, tail_key, parent in BONES:
    b = arm.edit_bones.new(name)
    b.head = mathutils.Vector(J[HEAD[name]])
    b.tail = mathutils.Vector(J[tail_key])
    if (b.tail - b.head).length < 1e-4: b.tail = b.head + mathutils.Vector((0,0,0.02))
    created[name] = b
for name, _, parent in BONES:
    if parent and parent in created:
        created[name].parent = created[parent]
        created[name].use_connect = False
bpy.ops.object.mode_set(mode="OBJECT")

def weighted_fraction(o):
    n = sum(1 for v in o.data.vertices if any(g.weight > 0.001 for g in v.groups))
    return n / max(1, len(o.data.vertices))

bpy.ops.object.select_all(action="DESELECT")
obj.select_set(True); rig.select_set(True)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.parent_set(type="ARMATURE_AUTO")
frac = weighted_fraction(obj)
print("direct automatic weights -> %.1f%% of vertices weighted" % (100*frac))

BIND = "heat (direct)"
if frac < 0.02:
    # Heat-map skinning needs a topologically connected surface. This mesh is
    # split into UV-seam patches, so the solver fails outright. Weight a welded
    # PROXY instead and transfer the result back by position -- the delivered
    # geometry and its UVs are left exactly as they are.
    print("heat weighting failed on the raw mesh; using welded-proxy transfer")
    BIND = "heat on welded proxy, transferred by position"
    proxy = obj.copy(); proxy.data = obj.data.copy(); proxy.name = "weld_proxy"
    bpy.context.collection.objects.link(proxy)
    for m in list(proxy.modifiers): proxy.modifiers.remove(m)
    proxy.parent = None
    bpy.ops.object.select_all(action="DESELECT")
    proxy.select_set(True); bpy.context.view_layer.objects.active = proxy
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.remove_doubles(threshold=0.0005)
    bpy.ops.object.mode_set(mode="OBJECT")
    print("proxy welded: %d -> %d verts" % (len(obj.data.vertices), len(proxy.data.vertices)))
    bpy.ops.object.select_all(action="DESELECT")
    proxy.select_set(True); rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    print("proxy weighted: %.1f%%" % (100*weighted_fraction(proxy)))

    from mathutils import kdtree
    kd = kdtree.KDTree(len(proxy.data.vertices))
    for i, v in enumerate(proxy.data.vertices): kd.insert(v.co, i)
    kd.balance()
    pnames = {g.index: g.name for g in proxy.vertex_groups}
    for nm in pnames.values():
        if nm not in obj.vertex_groups: obj.vertex_groups.new(name=nm)
    for v in obj.data.vertices:
        _, idx, _ = kd.find(v.co)
        for g in proxy.data.vertices[idx].groups:
            obj.vertex_groups[pnames[g.group]].add([v.index], g.weight, "REPLACE")
    print("transferred -> %.1f%% of delivered vertices weighted" % (100*weighted_fraction(obj)))
    proxy.hide_render = True; proxy.hide_viewport = True
    if not any(m.type == "ARMATURE" for m in obj.modifiers):
        md = obj.modifiers.new("Armature", "ARMATURE"); md.object = rig
    obj.parent = rig

print("BIND METHOD:", BIND, "| groups:", len(obj.vertex_groups))

D = math.radians
V3 = mathutils.Vector

def _rotate_about_head(pb, R):
    """Apply rotation R about the bone's own head, so the joint stays put.
    Rotating the pose matrix directly (R @ m) pivots about the armature origin
    and drags the joint across the character, shearing the mesh."""
    m = pb.matrix.copy()
    T = mathutils.Matrix.Translation(m.to_translation())
    pb.matrix = T @ R.to_matrix().to_4x4() @ T.inverted() @ m
    bpy.context.view_layer.update()

def aim(pb, direction):
    """Reorient a pose bone so its axis points along a world-space direction."""
    cur = (pb.matrix.to_3x3() @ V3((0, 1, 0))).normalized()
    _rotate_about_head(pb, cur.rotation_difference(V3(direction).normalized()))

def twist(pb, degrees, axis=(0, 0, 1)):
    _rotate_about_head(pb, mathutils.Quaternion(V3(axis), D(degrees)))

DOWN, FWD = (0, 0, -1), (0, -1, 0)
POSES = {
 "00_rest": [],
 "01_arms_overhead": [("aim","upperarm.R",( 0.30,0, 1.0)), ("aim","forearm.R",( 0.18,0, 1.0)),
                      ("aim","upperarm.L",(-0.30,0, 1.0)), ("aim","forearm.L",(-0.18,0, 1.0))],
 "02_arms_forward":  [("aim","upperarm.R",( 0.22,-1,0.05)), ("aim","forearm.R",( 0.12,-1,0.05)),
                      ("aim","upperarm.L",(-0.22,-1,0.05)), ("aim","forearm.L",(-0.12,-1,0.05))],
 "03_bent_elbows":   [("aim","upperarm.R",( 0.40,-0.25,-0.85)), ("aim","forearm.R",( 0.25,-1.0,0.15)),
                      ("aim","upperarm.L",(-0.40,-0.25,-0.85)), ("aim","forearm.L",(-0.25,-1.0,0.15))],
 "04_torso_twist":   [("twist","spine",38), ("twist","chest",30), ("twist","neck",-18)],
 "05_deep_crouch":   [("aim","thigh.R",( 0.15,-0.75,-0.65)), ("aim","shin.R",( 0.05, 0.70,-0.72)),
                      ("aim","thigh.L",(-0.15,-0.75,-0.65)), ("aim","shin.L",(-0.05, 0.70,-0.72)),
                      ("aim","foot.R",(0,-1,-0.15)), ("aim","foot.L",(0,-1,-0.15)),
                      ("aim","spine",(0,-0.35,1)), ("aim","chest",(0,-0.25,1))],
 "06_high_step":     [("aim","thigh.R",(0.10,-0.95,-0.30)), ("aim","shin.R",(0.05,-0.15,-1.0)),
                      ("aim","foot.R",(0,-1,-0.2)),
                      ("aim","upperarm.L",(-0.35,-0.55,-0.75))],
 "07_kneel_harvest": [("aim","thigh.R",(0.12,-0.85,-0.50)), ("aim","shin.R",(0.05,0.95,-0.30)),
                      ("aim","thigh.L",(-0.12,-0.55,-0.80)), ("aim","shin.L",(-0.05,0.55,-0.83)),
                      ("aim","spine",(0,-0.55,1)), ("aim","chest",(0,-0.45,1)),
                      ("aim","upperarm.R",(0.30,-0.75,-0.60)), ("aim","forearm.R",(0.15,-0.85,-0.50))],
 "08_walk_contra":   [("aim","thigh.R",(0.05,-0.55,-0.85)), ("aim","shin.R",(0.05,-0.20,-1.0)),
                      ("aim","thigh.L",(-0.05,0.45,-0.90)),
                      ("aim","upperarm.R",(0.25,0.45,-0.86)),
                      ("aim","upperarm.L",(-0.25,-0.50,-0.83)), ("aim","forearm.L",(-0.15,-0.75,-0.65))],
}

scene = bpy.context.scene
world = bpy.data.worlds.new("W"); world.use_nodes = True
world.node_tree.nodes["Background"].inputs[1].default_value = 0.6
scene.world = world
scene.render.engine = next(e for e in ("BLENDER_EEVEE_NEXT","BLENDER_EEVEE","CYCLES")
                           if e in scene.render.bl_rna.properties["engine"].enum_items.keys())
scene.render.resolution_x = scene.render.resolution_y = 1100
try: scene.view_settings.view_transform = "Standard"
except TypeError: pass
key = bpy.data.objects.new("key", bpy.data.lights.new("key","AREA"))
key.data.energy = 300*H**2; key.data.size = 3*H
key.location = (2*H, -2.5*H, 2*H); key.rotation_euler = (D(60),0,D(40))
bpy.context.collection.objects.link(key)
cam_d = bpy.data.cameras.new("cam"); cam_d.lens = 55
cam = bpy.data.objects.new("cam", cam_d); bpy.context.collection.objects.link(cam)
scene.camera = cam
centre = (0, 0, zmin + H*0.52); dist = H*2.4
a = D(35)
cam.location = (centre[0]+dist*math.sin(a), centre[1]-dist*math.cos(a), centre[2]+H*0.10)
cam.rotation_euler = (D(88), 0, a)

bpy.ops.object.mode_set(mode="POSE")
for pose_name, rots in POSES.items():
    for pb in rig.pose.bones:
        pb.matrix_basis.identity()
    bpy.context.view_layer.update()
    for op, bone, val in rots:
        if bone not in rig.pose.bones: continue
        (aim if op == "aim" else twist)(rig.pose.bones[bone], val)
    scene.render.filepath = os.path.join(OUT, f"pose_{pose_name}.png")
    bpy.ops.render.render(write_still=True)
    print("posed+rendered", pose_name, flush=True)
bpy.ops.object.mode_set(mode="OBJECT")
print("AUTORIG TEST DONE")
