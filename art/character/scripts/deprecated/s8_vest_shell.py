"""Vest shell: assembled quad topology, shrinkwrapped, then briefly relaxed.

No sewing solver. The garment is built already joined:

  * one open band around the torso (front opening between 355 deg and 5 deg),
    whose top edge profile encodes the V-neck, the shoulder plateaus, the
    armhole scoops and the back neckline;
  * two shoulder straps that arch over each shoulder and are welded into the
    band's top edge, so front and back are continuously connected and the
    armhole is a real hole bounded by band + strap.

Angles are measured from the front (-Y), increasing toward the character's
left (+X). The 5 degree column pitch puts every feature on a column boundary.
"""
import bpy, bmesh, math
from mathutils import Vector
from mathutils.bvhtree import BVHTree

HEM_Z, SHOULDER_Z = 1.005, 1.335
V_APEX_Z, UNDERARM_Z, BACK_NECK_Z = 1.165, 1.195, 1.305
TH0, TH1, DTH = 5.0, 355.0, 5.0            # band span and column pitch
NV = 10                                     # rows, hem -> top edge
CLEAR = 0.013                               # clearance over the shirt
STRAP_L = 6                                 # arc segments over the shoulder
STRAP_LIFT = 0.055                          # arc height before shrinkwrap

# feature angles (left side; right side is the mirror)
L_ARM = (60.0, 120.0)      # armhole scoop
L_STRAP_F = (45.0, 60.0)   # front strap attachment
L_STRAP_B = (120.0, 135.0)
R_ARM = (240.0, 300.0)
R_STRAP_F = (300.0, 315.0)
R_STRAP_B = (225.0, 240.0)


def smoothstep(a, b, x):
    if b == a:
        return 0.0
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def top_z(th):
    """Top-edge height of the band at angle th."""
    if th <= 45.0:                                   # front V rising to shoulder
        return V_APEX_Z + (SHOULDER_Z - V_APEX_Z) * smoothstep(5.0, 45.0, th)
    if th <= 60.0:
        return SHOULDER_Z
    if th <= 90.0:                                   # armhole scoop down
        return SHOULDER_Z - (SHOULDER_Z - UNDERARM_Z) * smoothstep(60.0, 90.0, th)
    if th <= 120.0:                                  # and back up
        return UNDERARM_Z + (SHOULDER_Z - UNDERARM_Z) * smoothstep(90.0, 120.0, th)
    if th <= 135.0:
        return SHOULDER_Z
    if th <= 180.0:                                  # back neckline
        return SHOULDER_Z - (SHOULDER_Z - BACK_NECK_Z) * smoothstep(135.0, 180.0, th)
    return top_z(360.0 - th)                         # mirror the right half


def torso_centre(shirt, z):
    pts = [(shirt.matrix_world @ v.co) for v in shirt.data.vertices
           if abs((shirt.matrix_world @ v.co).z - z) < 0.030]
    y = sum(p.y for p in pts) / len(pts) if pts else -0.03
    return Vector((0.0, y, z))


def surface(bvh, centre, th, clear):
    t = math.radians(th)
    d = Vector((math.sin(t), -math.cos(t), 0.0))
    hit = bvh.ray_cast(centre, d, 1.2)
    return (hit[0] + d * clear) if hit[0] else centre + d * (0.17 + clear)


def build_shell(shirt):
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(shirt.evaluated_get(dg), depsgraph=dg)
    me.transform(shirt.matrix_world)
    bvh = BVHTree.FromPolygons([v.co.copy() for v in me.vertices],
                               [tuple(p.vertices) for p in me.polygons])
    bpy.data.meshes.remove(me)

    bm = bmesh.new()
    angles = []
    th = TH0
    while th <= TH1 + 1e-6:
        angles.append(round(th, 3))
        th += DTH
    cols = {}
    for th in angles:
        tz = top_z(th)
        col = []
        for j in range(NV + 1):
            z = HEM_Z + (tz - HEM_Z) * (j / NV)
            col.append(bm.verts.new(surface(bvh, torso_centre(shirt, z), th, CLEAR)))
        cols[th] = col
    bm.verts.ensure_lookup_table()
    for i in range(len(angles) - 1):
        a, b = angles[i], angles[i + 1]
        for j in range(NV):
            bm.faces.new((cols[a][j], cols[b][j], cols[b][j + 1], cols[a][j + 1]))

    # ---- shoulder straps, welded into the band's top edge ----------------
    def strap(front_span, back_span):
        f = [a for a in angles if front_span[0] - 1e-6 <= a <= front_span[1] + 1e-6]
        b = [a for a in angles if back_span[0] - 1e-6 <= a <= back_span[1] + 1e-6]
        b = b[::-1] if front_span[0] < back_span[0] else b
        n = min(len(f), len(b))
        f, b = f[:n], b[:n]
        rows = []
        for l in range(STRAP_L + 1):
            t = l / STRAP_L
            row = []
            for k in range(n):
                if l == 0:
                    row.append(cols[f[k]][NV])          # shared with the band
                elif l == STRAP_L:
                    row.append(cols[b[k]][NV])          # shared with the band
                else:
                    p0 = cols[f[k]][NV].co
                    p1 = cols[b[k]][NV].co
                    p = p0.lerp(p1, t)
                    p.z += STRAP_LIFT * math.sin(math.pi * t)   # arch over
                    row.append(bm.verts.new(p))
            rows.append(row)
        for l in range(STRAP_L):
            for k in range(n - 1):
                bm.faces.new((rows[l][k], rows[l][k + 1],
                              rows[l + 1][k + 1], rows[l + 1][k]))
        return n

    nl = strap(L_STRAP_F, L_STRAP_B)
    nr = strap(R_STRAP_B, R_STRAP_F)

    bm.normal_update()
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    mesh = bpy.data.meshes.new("RV_Vest")
    bm.to_mesh(mesh)
    bm.free()
    ob = bpy.data.objects.new("RV_Vest", mesh)
    bpy.context.scene.collection.objects.link(ob)
    for f in ob.data.polygons:
        f.use_smooth = True
    return ob, {"band_columns": len(angles), "strap_width_L": nl,
                "strap_width_R": nr, "verts": len(mesh.vertices),
                "faces": len(mesh.polygons)}


def fit(ob, shirt, offset=CLEAR):
    sw = ob.modifiers.new("Fit", 'SHRINKWRAP')
    sw.target = shirt
    sw.wrap_method = 'NEAREST_SURFACEPOINT'
    sw.offset = offset
    return sw


def pin_group(ob):
    """Neckline + shoulder strap region: strongly constrained during relax."""
    zs = [v.co.z for v in ob.data.vertices]
    hi = max(zs)
    idx = [v.index for v in ob.data.vertices if v.co.z > hi - 0.075]
    vg = ob.vertex_groups.get("PIN") or ob.vertex_groups.new(name="PIN")
    vg.add(idx, 1.0, 'REPLACE')
    return len(idx)


def relax(ob, frames=22, gravity=0.35):
    cl = ob.modifiers.new("Relax", 'CLOTH')
    s = cl.settings
    s.quality = 8
    s.mass = 0.5
    s.tension_stiffness = 30
    s.compression_stiffness = 30
    s.shear_stiffness = 20
    s.bending_stiffness = 10          # stiff: this is a short settle, not a drape
    s.use_sewing_springs = False      # no seam closure at all
    s.vertex_group_mass = "PIN"
    s.effector_weights.gravity = gravity
    c = cl.collision_settings
    c.collision_quality = 4
    c.distance_min = 0.004
    c.use_self_collision = True
    c.self_distance_min = 0.003
    scn = bpy.context.scene
    scn.frame_start = 1
    scn.frame_end = frames
    for f in range(1, frames + 1):
        scn.frame_set(f)
    return frames
