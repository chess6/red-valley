"""Stage 2 -- layered garments for the Red Valley protagonist.

Each garment is grown from the *evaluated* (shape-keyed) body surface so it
fits the actual sculpt, then given standoff, drape, real thickness and hems:

    region select -> outward standoff -> relax (garments skim, not shrink-wrap)
                  -> fold noise -> solidify -> subsurf

Body-part predicates (hand/head/foot) keep each garment off the wrong anatomy
-- without them the torso pieces swallow the hands.

Layer standoff keeps the stack from interpenetrating:
    skin 0 < shirt < pants < vest < belt < boots
"""
import bpy, bmesh, math
from mathutils import Vector
import mathutils.noise as mnoise

J = {"neck": 1.408, "clavicle": 1.338, "elbow_z": 1.168,
     "wrist_z": 1.064, "pelvis": 0.892, "knee": 0.450, "ankle": 0.074}
SHOULDER_L = Vector((0.1677, -0.0146, 1.3436))
ELBOW_L = Vector((0.3129, -0.0132, 1.1683))
WRIST_L = Vector((0.4312, -0.1757, 1.0642))
BODY = "RV_Body"


def log(*a):
    print("[S2]", *a, flush=True)


def mirror(v):
    return Vector((-v.x, v.y, v.z))


def evaluated_body():
    ob = bpy.data.objects[BODY]
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg), depsgraph=dg)
    me.transform(ob.matrix_world)
    return ob, me


def helper_vert_mask(ob, me):
    g = ob.vertex_groups.get("HelperGeometry")
    if g is None:
        return [False] * len(me.vertices)
    gi = g.index
    return [any(x.group == gi and x.weight > 0.5 for x in v.groups) for v in me.vertices]


def arm_t(p):
    """(param, dist) along shoulder(0)->elbow(1)->wrist(2) for the nearer arm."""
    best = None
    for sh, el, wr in ((SHOULDER_L, ELBOW_L, WRIST_L),
                       (mirror(SHOULDER_L), mirror(ELBOW_L), mirror(WRIST_L))):
        for i, (a, b) in enumerate(((sh, el), (el, wr))):
            ab = b - a
            t = max(0.0, min(1.0, (p - a).dot(ab) / ab.length_squared))
            d = (p - (a + ab * t)).length
            if best is None or d < best[1]:
                best = (i + t, d)
    return best


# ---- body-part predicates --------------------------------------------------
def is_hand(p):
    """True beyond the wrist plane. A plain radius cannot separate hand from
    forearm (elbow->wrist is only ~0.22 m, shorter than the finger reach), so
    project onto the forearm axis instead: t > 1 means past the wrist."""
    for el, wr in ((ELBOW_L, WRIST_L), (mirror(ELBOW_L), mirror(WRIST_L))):
        ab = wr - el
        t = (p - el).dot(ab) / ab.length_squared
        if t > 1.02 and (p - wr).length < 0.32:
            return True
    return False


def is_head(p):
    return p.z > J["neck"] + 0.012


def is_foot(p):
    return p.z < J["ankle"] + 0.010


def build_shell(name, keep_fn, standoff, thickness, subsurf=2, relax=8,
                fold_scale=(24, 24, 30), fold_amp=0.0, fold_mask=None,
                inflate=0.0, remesh=None, post=None):
    ob, me = evaluated_body()
    helpers = helper_vert_mask(ob, me)

    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    doomed = [v for i, v in enumerate(bm.verts) if helpers[i] or not keep_fn(v.co)]
    bmesh.ops.delete(bm, geom=doomed, context='VERTS')
    bm.verts.ensure_lookup_table()
    if not len(bm.verts):
        bm.free(); bpy.data.meshes.remove(me)
        raise RuntimeError(f"{name}: empty region")

    bm.normal_update()
    for v in bm.verts:
        v.co += v.normal * standoff

    # relax: a garment skims the body, it does not wrap every contour
    for _ in range(relax):
        bmesh.ops.smooth_vert(bm, verts=bm.verts[:], factor=0.55,
                              use_axis_x=True, use_axis_y=True, use_axis_z=True)

    # re-inflate what relaxing pulled in, so cloth keeps volume
    if inflate:
        bm.normal_update()
        for v in bm.verts:
            v.co += v.normal * inflate

    if fold_amp > 0.0:
        bm.normal_update()
        for v in bm.verts:
            m = 1.0 if fold_mask is None else fold_mask(v.co)
            if m <= 0.0:
                continue
            q = Vector((v.co.x * fold_scale[0], v.co.y * fold_scale[1], v.co.z * fold_scale[2]))
            n = mnoise.noise(q) + 0.5 * mnoise.noise(q * 2.13)
            v.co += v.normal * (n * fold_amp * m)

    if post:
        post(bm)

    new_me = bpy.data.meshes.new(name)
    bm.to_mesh(new_me)
    bm.free()
    bpy.data.meshes.remove(me)

    g = bpy.data.objects.new(name, new_me)
    bpy.context.scene.collection.objects.link(g)
    for f in g.data.polygons:
        f.use_smooth = True

    # voxel remesh fuses fiddly anatomy (toes) into one solid form -- boots
    if remesh:
        rm = g.modifiers.new("Remesh", 'REMESH')
        rm.mode = 'VOXEL'
        rm.voxel_size = remesh
        rm.use_smooth_shade = True
        bpy.context.view_layer.objects.active = g
        bpy.ops.object.modifier_apply(modifier=rm.name)
        for _ in range(2):
            bpy.ops.object.modifier_add(type='SMOOTH')
            g.modifiers[-1].factor = 0.7
            g.modifiers[-1].iterations = 6
            bpy.ops.object.modifier_apply(modifier=g.modifiers[-1].name)

    sol = g.modifiers.new("Thickness", 'SOLIDIFY')
    sol.thickness = thickness
    sol.offset = 1.0
    sol.use_rim = True
    ss = g.modifiers.new("Smooth", 'SUBSURF')
    ss.levels = 1
    ss.render_levels = subsurf
    log(f"built {name}: verts={len(new_me.vertices)} polys={len(new_me.polygons)}")
    return g


def boolean_cut(target, cutter):
    """Subtract cutter from target and delete the cutter."""
    m = target.modifiers.new("Cut", 'BOOLEAN')
    m.operation = 'DIFFERENCE'
    m.object = cutter
    m.solver = 'EXACT'
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.modifier_apply(modifier=m.name)
    bpy.data.objects.remove(cutter, do_unlink=True)


def make_v_neck_cutter(apex_z, top_z, half_top):
    """Triangular prism through the chest: apex low + centred, opening upward."""
    verts = [(-half_top, -0.40, top_z), (half_top, -0.40, top_z), (0.0, -0.40, apex_z),
             (-half_top, 0.10, top_z), (half_top, 0.10, top_z), (0.0, 0.10, apex_z)]
    faces = [(0, 1, 2), (5, 4, 3), (0, 3, 4, 1), (1, 4, 5, 2), (2, 5, 3, 0)]
    me = bpy.data.meshes.new("VCut")
    me.from_pydata(verts, [], faces)
    me.update()
    o = bpy.data.objects.new("VCut", me)
    bpy.context.scene.collection.objects.link(o)
    return o


def make_armhole_cutter(shoulder, radius, length=0.55):
    """Capsule down the arm axis to carve a clean armhole."""
    axis = (ELBOW_L - SHOULDER_L).normalized()
    if shoulder.x < 0:
        axis = Vector((-axis.x, axis.y, axis.z))
    centre = shoulder + axis * (length * 0.42)
    bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=radius, depth=length,
                                        location=centre)
    o = bpy.context.object
    o.rotation_euler = axis.to_track_quat('Z', 'Y').to_euler()
    return o


def build_boots():
    """Boot upper grown from the foot surface itself (heavy relaxation melts the
    toes into a boot form) plus a bmesh sole slab. Primitive boxes read as
    stacked cubes, and remeshing shrank the geometry away."""
    upper = build_shell(
        "RV_Boots", lambda p: p.z < 0.262, standoff=0.024, thickness=0.010,
        relax=22, inflate=0.016, subsurf=2,
        fold_scale=(38, 38, 38), fold_amp=0.0016)

    # sole slab, welded on as loose geometry (same opaque material)
    ob, me = evaluated_body()
    helpers = helper_vert_mask(ob, me)
    bm = bmesh.new()
    for sign in (1, -1):
        pts = [v.co for i, v in enumerate(me.vertices)
               if not helpers[i] and v.co.z < 0.10 and (v.co.x * sign) > 0.05]
        if not pts:
            continue
        xs = [p.x for p in pts]; ys = [p.y for p in pts]
        xc = (min(xs) + max(xs)) / 2
        y_toe, y_heel = min(ys), max(ys)
        w = (max(xs) - min(xs)) / 2
        tmp = bmesh.new()
        bmesh.ops.create_cube(tmp, size=1.0)
        sx, sy, sz = w + 0.026, (y_heel - y_toe) / 2 + 0.028, 0.019
        cx, cy, cz = xc, (y_toe + y_heel) / 2 - 0.008, 0.019
        for v in tmp.verts:
            v.co.x = v.co.x * 2 * sx + cx
            v.co.y = v.co.y * 2 * sy + cy
            v.co.z = v.co.z * 2 * sz + cz
        bmesh.ops.bevel(tmp, geom=tmp.verts[:] + tmp.edges[:] + tmp.faces[:],
                        offset=0.010, segments=3, affect='EDGES', profile=0.55)
        t_me = bpy.data.meshes.new("t")
        tmp.to_mesh(t_me); tmp.free()
        bm.from_mesh(t_me)
        bpy.data.meshes.remove(t_me)
    bpy.data.meshes.remove(me)

    sole_me = bpy.data.meshes.new("RV_BootSoles")
    bm.to_mesh(sole_me); bm.free()
    soles = bpy.data.objects.new("RV_BootSoles", sole_me)
    bpy.context.scene.collection.objects.link(soles)
    for f in soles.data.polygons:
        f.use_smooth = True
    log(f"built boot soles: verts={len(sole_me.vertices)}")
    return upper


def clear_previous():
    for n in ("RV_Shirt", "RV_Pants", "RV_Vest", "RV_Belt", "RV_Boots",
              "RV_Buckle", "RV_Buttons", "RV_BootSoles"):
        o = bpy.data.objects.get(n)
        if o:
            bpy.data.objects.remove(o, do_unlink=True)


def build_all():
    clear_previous()
    made = {}

    # ------------------------------------------------- SHIRT (cream, rolled)
    SLEEVE_END = 1.34          # arm param: just past mid-forearm

    def shirt_keep(p):
        if is_hand(p):
            return False
        a = arm_t(p)
        on_arm = a is not None and a[1] < 0.155
        if on_arm and a[0] > 0.25:
            return a[0] < SLEEVE_END
        if is_head(p):
            return False
        # collar rides to the neck, but opens at the throat in front
        if p.z > 1.315:
            if p.y < -0.02 and abs(p.x) < 0.052:
                return False        # open collar / throat
            return p.z < J["neck"] + 0.010
        return p.z > 0.90

    def roll_cuff(bm):
        """Fatten the sleeve end into a rolled-up cuff."""
        for v in bm.verts:
            a = arm_t(v.co)
            if a and a[1] < 0.16 and a[0] > SLEEVE_END - 0.13:
                f = min(1.0, (a[0] - (SLEEVE_END - 0.13)) / 0.13)
                v.co += v.normal * (0.011 * f)

    made["shirt"] = build_shell(
        "RV_Shirt", shirt_keep, standoff=0.007, thickness=0.0035, relax=9,
        inflate=0.005, fold_scale=(26, 26, 34), fold_amp=0.0080,
        fold_mask=lambda p: 1.0 if p.z < 1.24 else 0.30, post=roll_cuff)

    # ------------------------------------------------- PANTS (dark, fitted)
    def pants_keep(p):
        if abs(p.x) > 0.33:      # fingers hang down into this z-band
            return False
        return J["ankle"] + 0.010 < p.z < 1.005

    made["pants"] = build_shell(
        "RV_Pants", pants_keep, standoff=0.009, thickness=0.0042, relax=8,
        inflate=0.006, fold_scale=(22, 22, 28), fold_amp=0.0082,
        fold_mask=lambda p: 1.0 if p.z < 0.55 else (0.55 if p.z < 0.82 else 0.25))

    # ------------------------------------------------- VEST (brown leather)
    V_APEX, V_TOP = 1.150, J["clavicle"]

    # Cut the neckline and armholes with booleans, but only AFTER solidify has
    # been applied: a boolean against an open shell silently no-ops (that is
    # what produced the arm "wings"), while a closed shell cuts cleanly.
    def vest_keep(p):
        if is_hand(p) or is_head(p):
            return False
        a = arm_t(p)
        if a is not None and a[1] < 0.115 and a[0] > 0.35:
            return False
        return 0.950 < p.z < V_TOP + 0.006

    vest = build_shell(
        "RV_Vest", vest_keep, standoff=0.026, thickness=0.0085, relax=20,
        inflate=0.016, fold_scale=(20, 20, 24), fold_amp=0.0038,
        fold_mask=lambda p: 0.8 if p.z < 1.09 else 0.25)

    bpy.context.view_layer.objects.active = vest
    vest.select_set(True)
    for mod in list(vest.modifiers):                 # make it a closed solid
        if mod.type in {'SOLIDIFY', 'SUBSURF'}:
            bpy.ops.object.modifier_apply(modifier=mod.name)
    boolean_cut(vest, make_v_neck_cutter(V_APEX, V_TOP + 0.09, 0.115))
    for sh in (SHOULDER_L, mirror(SHOULDER_L)):
        boolean_cut(vest, make_armhole_cutter(sh, radius=0.098))
    ss = vest.modifiers.new("Smooth", 'SUBSURF')
    ss.levels = 1; ss.render_levels = 2
    for f in vest.data.polygons:
        f.use_smooth = True
    made["vest"] = vest

    # buttons down the placket
    btns = []
    for i, z in enumerate((1.145, 1.093, 1.041, 0.989)):
        bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.0075, depth=0.004,
                                            location=(0.0, 0, z),
                                            rotation=(math.radians(90), 0, 0))
        b = bpy.context.object
        b.name = f"RV_Button_{i}"
        btns.append(b)
    if btns:
        bpy.ops.object.select_all(action='DESELECT')
        for b in btns:
            b.select_set(True)
        bpy.context.view_layer.objects.active = btns[0]
        bpy.ops.object.join()
        joined = bpy.context.object
        joined.name = "RV_Buttons"
        made["buttons"] = joined

    # ------------------------------------------------- BELT + buckle
    made["belt"] = build_shell("RV_Belt",
                               lambda p: abs(p.x) < 0.33 and 0.952 < p.z < 1.010,
                               standoff=0.026, thickness=0.011, subsurf=1,
                               relax=4, inflate=0.004)

    bpy.ops.mesh.primitive_cube_add(size=1)
    bk = bpy.context.object
    bk.name = "RV_Buckle"
    bk.scale = (0.040, 0.011, 0.032)
    bpy.ops.object.transform_apply(scale=True)
    belt = made["belt"]
    ymin = min((belt.matrix_world @ v.co).y for v in belt.data.vertices)
    bk.location = (0.0, ymin - 0.006, 0.981)
    bev = bk.modifiers.new("B", 'BEVEL')
    bev.width = 0.005
    bev.segments = 3
    made["buckle"] = bk

    # ------------------------------------------------- BOOTS (constructed)
    made["boots"] = build_boots()

    return made


m = build_all()
log("garments:", {k: v.name for k, v in m.items()})
