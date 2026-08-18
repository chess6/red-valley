"""Vest built as tailored pattern panels -- front-left, front-right, back.

No booleans, no coordinate-predicate vertex deletion, no body-derived topology.
Each panel is a structured quad grid parameterised by (u = around the torso,
v = hem -> top).  The neckline, shoulder strap, armhole scoop and hem are
*built into* the panel's top/bottom edge functions, so every boundary is a
deliberate, continuous edge loop.

Panels are seated by ray-casting the shirt surface (so they start conformed),
then refined with Shrinkwrap -> Solidify -> Subdivision.
"""
import bpy, bmesh, math
from mathutils import Vector
from mathutils.bvhtree import BVHTree

TORSO_TOP = 1.335      # shoulder seam height
V_APEX    = 1.162      # bottom of the front V
BACK_NECK = 1.302      # centre-back neckline
UNDERARM  = 1.188      # bottom of the armhole
HEM       = 1.002
SIDE_SEAM = 72.0       # degrees from centre-front to the side seam
FRONT_GAP = 1.5        # half-gap at centre front (button placket)
STANDOFF  = 0.009      # clearance over the shirt


def smoothstep(a, b, x):
    if b == a:
        return 0.0
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def build_bvh(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(obj.evaluated_get(dg), depsgraph=dg)
    me.transform(obj.matrix_world)
    verts = [v.co.copy() for v in me.vertices]
    polys = [tuple(p.vertices) for p in me.polygons]
    bvh = BVHTree.FromPolygons(verts, polys)
    bpy.data.meshes.remove(me)
    return bvh


def torso_centre(shirt, z):
    """Centre of the torso cross-section at height z (the body is not centred
    on y=0, so a fixed axis would skew every panel)."""
    pts = [(shirt.matrix_world @ v.co) for v in shirt.data.vertices
           if abs((shirt.matrix_world @ v.co).z - z) < 0.030]
    if not pts:
        return Vector((0.0, -0.02, z))
    y = sum(p.y for p in pts) / len(pts)
    return Vector((0.0, y, z))


def surface_point(bvh, centre, theta_deg, standoff):
    """Ray-cast outward from the torso axis to sit the panel on the shirt."""
    t = math.radians(theta_deg)
    d = Vector((math.sin(t), -math.cos(t), 0.0))
    hit = bvh.ray_cast(centre, d, 1.2)
    if hit[0] is None:
        return centre + d * (0.16 + standoff)
    return hit[0] + d * standoff


# ---------------------------------------------------------------- edge shapes
def front_top(u):
    """u: 0 at centre-front, 1 at the side seam."""
    if u < 0.34:                      # V-neck climbing to the shoulder
        return V_APEX + (TORSO_TOP - V_APEX) * smoothstep(0.0, 0.34, u)
    if u < 0.52:                      # shoulder strap
        return TORSO_TOP
    return TORSO_TOP - (TORSO_TOP - UNDERARM) * smoothstep(0.52, 1.0, u)


def front_bottom(u):
    return HEM - 0.012 * (1.0 - smoothstep(0.0, 0.55, u))   # slight front point


def back_top(u):
    """u: 0 at one side seam, 1 at the other, 0.5 = centre back."""
    s = min(u, 1.0 - u) * 2.0        # 0 at a side seam, 1 at centre back
    if s < 0.30:                      # armhole scoop
        return UNDERARM + (TORSO_TOP - UNDERARM) * smoothstep(0.0, 0.30, s)
    if s < 0.62:
        return TORSO_TOP
    return TORSO_TOP - (TORSO_TOP - BACK_NECK) * smoothstep(0.62, 1.0, s)


def back_bottom(u):
    return HEM


def make_panel(name, bvh, shirt, th0, th1, top_fn, bot_fn, nu, nv, fold=0.0):
    bm = bmesh.new()
    grid = []
    for i in range(nu + 1):
        u = i / nu
        theta = th0 + (th1 - th0) * u
        z_top, z_bot = top_fn(u), bot_fn(u)
        col = []
        for j in range(nv + 1):
            v = j / nv
            z = z_bot + (z_top - z_bot) * v
            c = torso_centre(shirt, z)
            p = surface_point(bvh, c, theta, STANDOFF)
            if fold:                       # restrained drape, strongest at the hem
                w = (1.0 - v) ** 2
                a = math.radians(abs(((theta + 180.0) % 360.0) - 180.0))
                p += (p - c).normalized() * (
                    math.sin(a * 6.0) * 0.0016 * w
                    + math.sin(v * math.pi * 3.0) * 0.0010)
            col.append(bm.verts.new(p))
        grid.append(col)
    bm.verts.ensure_lookup_table()
    for i in range(nu):
        for j in range(nv):
            bm.faces.new((grid[i][j], grid[i + 1][j],
                          grid[i + 1][j + 1], grid[i][j + 1]))
    bm.normal_update()
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    for f in ob.data.polygons:
        f.use_smooth = True
    return ob


def build_vest(shirt):
    for n in ("RV_Vest", "RV_Vest_Buttons"):
        o = bpy.data.objects.get(n)
        if o:
            bpy.data.objects.remove(o, do_unlink=True)
    bvh = build_bvh(shirt)

    fl = make_panel("VestFL", bvh, shirt,  FRONT_GAP,  SIDE_SEAM,
                    front_top, front_bottom, 16, 14, fold=1.0)
    fr = make_panel("VestFR", bvh, shirt, -FRONT_GAP, -SIDE_SEAM,
                    front_top, front_bottom, 16, 14, fold=1.0)
    bk = make_panel("VestBK", bvh, shirt,  SIDE_SEAM,  360.0 - SIDE_SEAM,
                    back_top, back_bottom, 30, 14, fold=1.0)

    # join the three panels into one garment (they meet at the side seams)
    bpy.ops.object.select_all(action='DESELECT')
    for o in (fl, fr, bk):
        o.select_set(True)
    bpy.context.view_layer.objects.active = fl
    bpy.ops.object.join()
    vest = bpy.context.object
    vest.name = "RV_Vest"

    # weld the side seams so the panels form one continuous shell
    bm = bmesh.new(); bm.from_mesh(vest.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=0.0035)
    bm.to_mesh(vest.data); bm.free(); vest.data.update()

    sw = vest.modifiers.new("Fit", 'SHRINKWRAP')
    sw.target = shirt
    sw.wrap_method = 'NEAREST_SURFACEPOINT'
    sw.offset = STANDOFF
    sol = vest.modifiers.new("Thickness", 'SOLIDIFY')
    sol.thickness = 0.0035
    sol.offset = 1.0
    sol.use_rim = True
    ss = vest.modifiers.new("Smooth", 'SUBSURF')
    ss.levels = 1
    ss.render_levels = 2
    return vest


def build_buttons():
    """Four buttons down the centre-front placket."""
    bm = bmesh.new()
    for z in (1.128, 1.086, 1.044, 1.008):
        tmp = bmesh.new()
        bmesh.ops.create_cone(tmp, cap_ends=True, cap_tris=False, segments=16,
                              radius1=0.0072, radius2=0.0072, depth=0.0035)
        for v in tmp.verts:
            v.co = Vector((v.co.x, v.co.z, v.co.y))      # lie flat, facing -Y
        me_t = bpy.data.meshes.new("t"); tmp.to_mesh(me_t); tmp.free()
        bm.from_mesh(me_t); bpy.data.meshes.remove(me_t)
        n = len(bm.verts)
        bm.verts.ensure_lookup_table()
        for v in bm.verts[n - 34:]:
            pass
    me = bpy.data.meshes.new("RV_Vest_Buttons")
    bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new("RV_Vest_Buttons", me)
    bpy.context.scene.collection.objects.link(ob)
    return ob
