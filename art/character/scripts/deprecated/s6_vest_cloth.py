"""Vest as flat sewing-pattern panels joined by cloth sewing springs.

Three FLAT panels are drafted to measured body girth (chest 1.00 m, waist
0.86 m), positioned in front of / behind the torso, then joined by wire
"sewing" edges at both shoulder seams and both side seams. Blender's cloth
solver contracts those springs, wrapping the panels around the body, with
collision against the shirt and self-collision enabled.

The 3D form therefore comes from simulation, not from a projected surface
grid, and the shoulder seams give the garment a real load path.
"""
import bpy, bmesh, math
from mathutils import Vector

HEM_Z      = 1.005          # hem height
H_SHOULDER = 0.330          # hem -> shoulder seam
H_VNECK    = 0.175          # hem -> bottom of the front V
H_UNDERARM = 0.195          # hem -> underarm (armhole bottom)
H_BACKNECK = 0.300          # hem -> centre-back neckline
W_FRONT    = 0.270          # centre-front -> side seam
W_BACK     = 0.540          # side seam -> side seam
NV         = 18             # rows, hem -> top (must match on both panels)
NU_F       = 24             # front columns
NU_B       = 48             # back columns
F_SH       = (15, 19)       # front shoulder-seam column span
B_SH_L     = (10, 14)       # back left shoulder span
B_SH_R     = (34, 38)       # back right shoulder span
# Panels stay flat; they are rigidly ARRANGED around the torso before sewing,
# exactly as pattern pieces are placed around an avatar. Starting them far
# apart made the seams travel ~0.36 m and crush the garment.
FRONT_ORIGIN = (0.010, -0.175)   # centre-front, hem level
FRONT_DIR    = (0.800,  0.600)   # chord across the front quadrant
FRONT_Y_TOP  = 0.075             # planes TILT: top edge leans back toward the
BACK_Y_BOT   = 0.130             # shoulder, bottom hangs away from the body,
BACK_Y_TOP   = -0.120            # so pinning needs almost no displacement
BACK_SPAN    = 0.450


def smoothstep(a, b, x):
    if b == a:
        return 0.0
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def front_top(i):
    """Panel-local height of the top edge at column i (flat pattern)."""
    if i <= F_SH[0]:                       # V-neck rising to the shoulder
        return H_VNECK + (H_SHOULDER - H_VNECK) * smoothstep(0, F_SH[0], i)
    if i <= F_SH[1]:                       # shoulder seam plateau
        return H_SHOULDER
    return H_SHOULDER - (H_SHOULDER - H_UNDERARM) * smoothstep(F_SH[1], NU_F, i)


def back_top(i):
    # fold the index about centre-back; recursing here spins forever at i == NU_B/2
    k = i if i <= NU_B / 2 else NU_B - i
    if k <= B_SH_L[0]:
        return H_UNDERARM + (H_SHOULDER - H_UNDERARM) * smoothstep(0, B_SH_L[0], k)
    if k <= B_SH_L[1]:
        return H_SHOULDER
    return H_SHOULDER - (H_SHOULDER - H_BACKNECK) * smoothstep(B_SH_L[1], NU_B / 2, k)


def build_panels():
    """Returns (bmesh, index tables) with three flat panels in one mesh."""
    bm = bmesh.new()
    tables = {}

    def grid(name, nu, top_fn, place):
        cols = []
        for i in range(nu + 1):
            top = top_fn(i)
            col = []
            for j in range(NV + 1):
                t = j / NV
                x, y = place(i, t)
                col.append(bm.verts.new(Vector((x, y, HEM_Z + top * t))))
            cols.append(col)
        bm.verts.ensure_lookup_table()
        for i in range(nu):
            for j in range(NV):
                bm.faces.new((cols[i][j], cols[i + 1][j],
                              cols[i + 1][j + 1], cols[i][j + 1]))
        tables[name] = cols
        return cols

    def fl(i, t):
        s_ = (i / NU_F) * W_FRONT
        return (FRONT_ORIGIN[0] + FRONT_DIR[0] * s_,
                FRONT_ORIGIN[1] + FRONT_DIR[1] * s_ + FRONT_Y_TOP * t)
    def fr(i, t):
        x, y = fl(i, t)
        return (-x, y)
    def bk(i, t):
        return ((BACK_SPAN / 2) - (i / NU_B) * BACK_SPAN,
                BACK_Y_BOT + (BACK_Y_TOP - BACK_Y_BOT) * t)
    grid("FL", NU_F, front_top, fl)
    grid("FR", NU_F, front_top, fr)
    grid("BK", NU_B, back_top, bk)
    return bm, tables


def add_sewing(bm, T):
    """Wire edges the cloth solver contracts. No faces -> pure sewing springs."""
    n = 0

    def sew(a, b):
        nonlocal n
        if a is not b and not bm.edges.get((a, b)):
            bm.edges.new((a, b))
            n += 1

    # side seams: front side column <-> back outermost column, row by row
    for j in range(NV + 1):
        sew(T["FL"][NU_F][j], T["BK"][0][j])
        sew(T["FR"][NU_F][j], T["BK"][NU_B][j])
    # shoulder seams: top row spans, back reversed so the seam does not twist
    fl = list(range(F_SH[0], F_SH[1] + 1))
    bl = list(range(B_SH_L[0], B_SH_L[1] + 1))[::-1]
    br = list(range(B_SH_R[0], B_SH_R[1] + 1))
    for a, b in zip(fl, bl):
        sew(T["FL"][a][NV], T["BK"][b][NV])
    for a, b in zip(fl, br):
        sew(T["FR"][a][NV], T["BK"][b][NV])
    return n


def seat_and_pin_shoulders(ob, T, shirt):
    """Place each shoulder-seam vertex pair onto the real shoulder and pin it.

    A waistcoat is carried by its shoulder seams. Without that anchor the
    sewing springs simply drag both panels onto the chest and crumple them,
    which is exactly what the first two simulations did.
    """
    from mathutils.bvhtree import BVHTree
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(shirt.evaluated_get(dg), depsgraph=dg)
    me.transform(shirt.matrix_world)
    bvh = BVHTree.FromPolygons([v.co.copy() for v in me.vertices],
                               [tuple(p.vertices) for p in me.polygons])
    bpy.data.meshes.remove(me)

    verts = ob.data.vertices
    pinned = []
    n = F_SH[1] - F_SH[0]
    for sign, f_tab, b_span in ((1, "FL", B_SH_L), (-1, "FR", B_SH_R)):
        for k in range(n + 1):
            a = k / n
            x = sign * (0.055 + a * 0.090)
            y = -0.020 + a * 0.010
            hit = bvh.ray_cast(Vector((x, y, 1.62)), Vector((0, 0, -1)), 0.7)
            if hit[0] is None:
                continue
            target = hit[0] + hit[1] * 0.009
            MAXMOVE = 0.045   # large pin displacements detonate the solver
            fi = T[f_tab][F_SH[0] + k][NV]
            bi_idx = (B_SH_L[1] - k) if sign > 0 else (B_SH_R[0] + k)
            bi = T["BK"][bi_idx][NV]
            for vi in (fi, bi):
                d = target - verts[vi].co
                if d.length > MAXMOVE:
                    d = d.normalized() * MAXMOVE
                verts[vi].co = verts[vi].co + d
                pinned.append(vi)
    vg = ob.vertex_groups.get("PIN") or ob.vertex_groups.new(name="PIN")
    vg.add(pinned, 1.0, 'REPLACE')
    return len(pinned)


def build(collide_with=("RV_Shirt", "RV_Body")):
    old = bpy.data.objects.get("RV_Vest")
    if old:
        bpy.data.objects.remove(old, do_unlink=True)
    bm, T = build_panels()
    n_sew = add_sewing(bm, T)
    me = bpy.data.meshes.new("RV_Vest")
    bm.verts.index_update()
    # freeze the tables to plain indices: BMVerts die with the bmesh
    T = {k: [[v.index for v in col] for col in cols] for k, cols in T.items()}
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("RV_Vest", me)
    bpy.context.scene.collection.objects.link(ob)
    for f in ob.data.polygons:
        f.use_smooth = True

    # collision on the surfaces the vest must lie over
    for nm in collide_with:
        o = bpy.data.objects.get(nm)
        if not o:
            continue
        if not any(m.type == 'COLLISION' for m in o.modifiers):
            o.modifiers.new("Collision", 'COLLISION')
        cs = o.collision
        cs.thickness_outer = 0.004
        cs.thickness_inner = 0.010
        cs.damping = 0.4

    cl = ob.modifiers.new("Cloth", 'CLOTH')
    s = cl.settings
    s.quality = 14
    s.mass = 0.80
    s.tension_stiffness = 18
    s.compression_stiffness = 18
    s.shear_stiffness = 10
    s.bending_stiffness = 2.5          # canvas/leather holds its shape
    s.tension_damping = 8
    s.bending_damping = 2
    s.use_sewing_springs = True
    s.sewing_force_max = 1.2         # finite: 0 means UNLIMITED and crushes the panels
    s.vertex_group_mass = 'PIN'      # shoulder seam carries the garment
    s.shrink_min = 0.0
    c = cl.collision_settings
    c.collision_quality = 5
    c.distance_min = 0.005
    c.use_self_collision = True
    c.self_distance_min = 0.004
    c.self_friction = 5
    c.friction = 20                  # grip the shirt, do not slide off
    return ob, T, {"sewing_edges": n_sew, "verts": len(me.vertices),
                   "faces": len(me.polygons)}


def simulate(ob, close_frames=45, settle_frames=85):
    """Phase 1 closes the seams with gravity off, so the garment cannot slide
    off the shoulders before it is a closed tube. Phase 2 lets it settle."""
    scn = bpy.context.scene
    cl = ob.modifiers["Cloth"]
    total = close_frames + settle_frames
    scn.frame_start = 1
    scn.frame_end = total
    cl.settings.effector_weights.gravity = 0.0
    for f in range(1, close_frames + 1):
        scn.frame_set(f)
    cl.settings.effector_weights.gravity = 1.0
    for f in range(close_frames + 1, total + 1):
        scn.frame_set(f)
    return total


def freeze(ob):
    """Apply the simulated shape, then add thickness + smoothing."""
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.modifier_apply(modifier="Cloth")
    # sewing edges become loose wires once simulated -- remove them
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    loose = [e for e in bm.edges if not e.link_faces]
    bmesh.ops.delete(bm, geom=loose, context='EDGES')
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=0.0016)
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()
    sol = ob.modifiers.new("Thickness", 'SOLIDIFY')
    sol.thickness = 0.0035
    sol.offset = 1.0
    sol.use_rim = True
    ss = ob.modifiers.new("Smooth", 'SUBSURF')
    ss.levels = 1
    ss.render_levels = 2
    return {"verts": len(ob.data.vertices), "faces": len(ob.data.polygons)}
